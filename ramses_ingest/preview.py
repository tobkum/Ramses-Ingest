# -*- coding: utf-8 -*-
"""Thumbnail and video proxy generation via ffmpeg.

Responsibilities:
    - Extract a representative frame from a clip (middle frame).
    - Resize and save as JPG thumbnail for the Ramses Client.
    - Optionally transcode a lightweight MP4 proxy for scrubbing.
    - Always output thumbnails and proxies in sRGB for web compatibility.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from ramses_ingest.scanner import Clip

logger = logging.getLogger(__name__)

# Subprocess creation flags to hide console windows on Windows
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _escape_ffmpeg_filter_path(path: str) -> str:
    """Escape a file path for use as an FFmpeg filter *option value*.

    A colon inside a filter option value is parsed at two levels (the
    filtergraph splits filters/options, then the option value is parsed), so
    every colon — including a Windows drive letter's — must be escaped with a
    **doubled** backslash (``C\\\\:/...``). A single backslash, or leaving the
    drive colon bare, makes FFmpeg 8.1's parser split the drive letter off as a
    separate option ("Undefined constant" / "No option name"). Verified
    empirically against ffmpeg 8.1. Callers must reference the result with an
    explicit ``file=`` key (e.g. ``lut3d=file=<escaped>``). Spaces need no
    escaping once the colons are handled.

    Args:
        path: File path (Windows or Unix)

    Returns:
        Escaped path for use after ``key=`` in an FFmpeg filter string

    Examples:
        C:\\OCIO\\config.ocio → C\\\\:/OCIO/config.ocio
        \\\\server\\share\\config.ocio → //server/share/config.ocio
        /mnt/ocio:v2/config.ocio → /mnt/ocio\\\\:v2/config.ocio
    """
    # Preserve UNC paths: \\server\share → //server/share
    if path.startswith("\\\\"):
        path = "//" + path[2:].replace("\\", "/")
    else:
        # Convert backslashes to forward slashes for FFmpeg
        path = path.replace("\\", "/")

    # Doubled backslash so the colon survives both parsing levels.
    return path.replace(":", "\\\\:")


def _escape_ffmpeg_filter_label(label: str) -> str:
    """Escape a colorspace label for use inside an FFmpeg filter option value.

    Colons and semicolons are special in FFmpeg filter syntax and must be escaped.
    """
    return label.replace("\\", "\\\\").replace(":", "\\:").replace(";", "\\;")

# OCIO display/view used by the ffmpeg `ocio` filter (FFmpeg >= 8.1 built
# with OpenColorIO). These are the ACES *Studio* config names — the CG config
# carries no camera colorspaces at all.
OCIO_DISPLAY = "sRGB - Display"
OCIO_VIEW = "ACES 1.0 - SDR Video"

# Builtin ACES Studio config, compiled into the PyOpenColorIO wheel — nothing
# to vendor or download. Pinned (not "-latest") so preview colors never shift
# under our feet when OCIO updates its bundled configs.
PINNED_OCIO_CONFIG = "ocio://studio-config-v2.1.0_aces-v1.3_ocio-v2.3"

# Colorspaces offered in the Options dropdown and the per-clip override.
# Every entry either matches a colorspace in the pinned ACES Studio config
# by name, or resolves through _LEGACY_COLORSPACE_ALIASES below — enforced
# by a test that bakes each one. Exceptions needing a manual LUT are listed
# in MANUAL_LUT_ONLY_COLORSPACES.
STANDARD_COLORSPACES = [
    # Generic / delivery
    "sRGB",
    "Linear",
    "Rec.709",
    "Rec.2020",
    "Gamma 2.2",
    "Gamma 2.4",
    # ACES
    "ACEScg",
    "ACES2065-1",
    "ACES - ACEScct",
    "ACES - ACEScc",
    # ARRI
    "ARRI LogC4",
    "ARRI LogC3 (EI800)",
    "LogC",
    # Sony
    "S-Log3 S-Gamut3.Cine",
    "S-Log3 S-Gamut3",
    "S-Log3 Venice S-Gamut3.Cine",
    "S-Log3 Venice S-Gamut3",
    "S-Log3",
    # Panasonic
    "V-Log V-Gamut",
    "V-Log",
    # Canon
    "CanonLog2 CinemaGamut D55",
    "CanonLog3 CinemaGamut D55",
    # RED
    "Log3G10 REDWideGamutRGB",
    # Blackmagic
    "BMDFilm WideGamut Gen5",
    "DaVinci Intermediate WideGamut",
    # Film scans — no ACES-config equivalent, requires a manual LUT
    "Cineon",
]

# Entries with no transform in the ACES configs: selectable (recorded in the
# sidecar/report), but previews stay untransformed unless a manual .cube
# exists in the luts folder.
MANUAL_LUT_ONLY_COLORSPACES = {"Cineon"}

# Our historical dropdown names -> ACES 1.3 Studio config colorspace names.
# ("Cineon" has no equivalent in the ACES configs — needs a manual LUT.)
_LEGACY_COLORSPACE_ALIASES = {
    "sRGB": "sRGB - Texture",
    "Linear": "Linear Rec.709 (sRGB)",
    "Rec.709": "Camera Rec.709",
    "Rec.2020": "Linear Rec.2020",
    "LogC": "ARRI LogC3 (EI800)",
    "S-Log3": "S-Log3 S-Gamut3.Cine",
    "V-Log": "V-Log V-Gamut",
    "Gamma 2.2": "Gamma 2.2 Rec.709 - Texture",
    "Gamma 2.4": "Gamma 2.4 Rec.709 - Texture",
    "ACES - ACEScct": "ACEScct",
    "ACES - ACEScc": "ACEScc",
}

_BAKE_CUBE_SIZE = 33  # preview quality; log/texture inputs need no shaper

_warned_no_pyocio = False

# Windows-invalid filename characters, replaced when mapping a colorspace
# name to a LUT filename ("ARRI LogC4" -> "ARRI LogC4.cube").
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def _luts_dir() -> str:
    """User LUT folder: %APPDATA%/ramses_ingest/luts (next to rules.yaml)."""
    from ramses_ingest.config import USER_RULES_PATH
    return os.path.join(os.path.dirname(USER_RULES_PATH), "luts")


def _bake_lut_from_ocio(ocio_in: str, out_path: str, ocio_config: str | None = None) -> bool:
    """Bakes a display-render .cube for *ocio_in* via PyOpenColorIO.

    Equivalent to ``ociobakelut``: input colorspace -> the config's default
    display/view (the tone-mapped "dailies look"). Tries the show config
    first (``$OCIO``), then the pinned builtin ACES Studio config, resolving
    our legacy dropdown names through ``_LEGACY_COLORSPACE_ALIASES``.

    Limitation: the .cube format has no shaper, so its input domain is
    [0,1] — camera-log and texture sources (the footage case) are bounded
    and bake exactly; *scene-linear* sources clip values above 1.0 to the
    tone-mapped white. Fine for previews; supply a manual LUT for exact
    linear handling.
    """
    global _warned_no_pyocio
    try:
        import PyOpenColorIO as ocio
    except ImportError:
        if not _warned_no_pyocio:
            logger.warning(
                "PyOpenColorIO not installed — previews stay untransformed "
                "unless a manual LUT exists (pip install opencolorio)."
            )
            _warned_no_pyocio = True
        return False

    for cfg_source in (ocio_config, PINNED_OCIO_CONFIG):
        if not cfg_source:
            continue
        try:
            cfg = ocio.Config.CreateFromFile(cfg_source)
        except Exception as exc:
            logger.warning("Could not load OCIO config %s: %s", cfg_source, exc)
            continue

        cs = cfg.getColorSpace(ocio_in)
        if not cs and ocio_in in _LEGACY_COLORSPACE_ALIASES:
            cs = cfg.getColorSpace(_LEGACY_COLORSPACE_ALIASES[ocio_in])
        if not cs:
            continue

        try:
            baker = ocio.Baker()
            baker.setConfig(cfg)
            baker.setFormat("iridas_cube")
            baker.setInputSpace(cs.getName())
            display = cfg.getDefaultDisplay()
            baker.setDisplayView(display, cfg.getDefaultView(display))
            baker.setCubeSize(_BAKE_CUBE_SIZE)
            data = baker.bake()
        except Exception as exc:
            logger.warning("LUT bake failed for %r in %s: %s", ocio_in, cfg_source, exc)
            continue

        out_dir = os.path.dirname(out_path)
        tmp_path = None
        try:
            os.makedirs(out_dir, exist_ok=True)
            # Unique temp name per writer: concurrent bakers must not clobber a
            # shared ".tmp" (that raced to WinError 32 on the replace).
            fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=out_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            try:
                os.replace(tmp_path, out_path)
                tmp_path = None
            except OSError:
                # A concurrent baker of the identical LUT may already hold the
                # destination open (Windows sharing violation). Its output is
                # byte-identical, so an existing non-empty file is success.
                if not (os.path.isfile(out_path) and os.path.getsize(out_path) > 0):
                    raise
            logger.info("Baked preview LUT for %r from %s", ocio_in, cfg_source)
            return True
        except OSError as exc:
            logger.warning("Could not write baked LUT %s: %s", out_path, exc)
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    logger.warning(
        "Colorspace %r not found in the OCIO config(s) — previews stay "
        "untransformed. Add a manual LUT or use a config name.", ocio_in
    )
    return False


# Per-output-path bake locks. The thumbnail phase runs 8 in-process threads,
# and a batch usually shares one source colorspace, so all threads would race
# to bake the identical LUT to the same path. Serialize per path (with a
# double-check inside the lock) so exactly one thread bakes and the rest reuse.
_bake_locks_guard = threading.Lock()
_bake_locks: dict[str, threading.Lock] = {}


def _ensure_baked_lut(ocio_in: str, out_path: str, ocio_config: str | None) -> bool:
    """Bake *out_path* once, even under concurrent callers. Idempotent."""
    if os.path.isfile(out_path):
        return True
    with _bake_locks_guard:
        lock = _bake_locks.setdefault(out_path, threading.Lock())
    with lock:
        # Another thread may have baked it while we waited for the lock.
        if os.path.isfile(out_path):
            return True
        return _bake_lut_from_ocio(ocio_in, out_path, ocio_config)


def _color_transform_filter(ocio_config: str | None, ocio_in: str) -> str | None:
    """The ffmpeg filter converting *ocio_in* footage to sRGB for previews.

    Priority:
    1. A manual ``.cube`` LUT named after the source colorspace in the user
       LUT folder (``luts/ARRI LogC4.cube``) — the studio/show override.
    2. A LUT **auto-baked via PyOpenColorIO** from the show config ($OCIO)
       or the pinned builtin ACES Studio config, cached under
       ``luts/_auto/``. Applied via ``lut3d`` — works with EVERY ffmpeg.
    3. The ffmpeg ``ocio`` filter with an ACES display/view transform —
       requires FFmpeg >= 8.1 built with OpenColorIO (most stock Windows
       builds are NOT; check ``ffmpeg -filters | findstr ocio``).

    Returns None when nothing is available (previews stay untransformed).
    """
    if ocio_in:
        safe_name = _INVALID_FILENAME_CHARS.sub("_", ocio_in)

        # 1. Manual override LUT
        lut_path = os.path.join(_luts_dir(), safe_name + ".cube")
        if os.path.isfile(lut_path):
            return f"lut3d=file={_escape_ffmpeg_filter_path(lut_path)}"

        # 2. Auto-baked LUT, cached per (colorspace, config) pair so a show
        #    config change never serves stale colors
        cfg_key = hashlib.md5((ocio_config or PINNED_OCIO_CONFIG).encode("utf-8")).hexdigest()[:8]
        auto_path = os.path.join(_luts_dir(), "_auto", f"{safe_name}__{cfg_key}.cube")
        if not os.path.isfile(auto_path):
            _ensure_baked_lut(ocio_in, auto_path, ocio_config)
        if os.path.isfile(auto_path):
            return f"lut3d=file={_escape_ffmpeg_filter_path(auto_path)}"

    # 3. OCIO-enabled ffmpeg builds only
    if ocio_config and os.path.isfile(ocio_config):
        clean_path = _escape_ffmpeg_filter_path(ocio_config)
        return (
            f"ocio=config={clean_path}"
            f":input={_escape_ffmpeg_filter_label(ocio_in)}"
            f":display={_escape_ffmpeg_filter_label(OCIO_DISPLAY)}"
            f":view={_escape_ffmpeg_filter_label(OCIO_VIEW)}"
        )

    return None


# Thumbnail settings
THUMB_WIDTH = 960
THUMB_QUALITY = 2  # ffmpeg -q:v (2 = high quality JPEG)

# Proxy settings
PROXY_WIDTH = 960
PROXY_CRF = 23


def generate_thumbnail(
    clip: Clip,
    output_path: str,
    frame_index: int | None = None,
    ocio_config: str | None = None,
    ocio_in: str = "sRGB",
) -> bool:
    """Extract a single frame from *clip* and save as JPEG at *output_path*.

    Args:
        clip: The source clip.
        output_path: Absolute path for the output JPG (including filename).
        frame_index: Which frame to extract (0-based). Defaults to middle frame.
        ocio_config: Path to an OCIO config file.
        ocio_in: Source colorspace (e.g. ACEScg, Linear, sRGB).

    Returns:
        True on success.
    """
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    if clip.is_sequence:
        return _thumbnail_from_sequence(clip, output_path, frame_index, ocio_config, ocio_in)
    else:
        return _thumbnail_from_movie(clip, output_path, frame_index, ocio_config, ocio_in)


def generate_proxy(
    clip: Clip,
    output_path: str,
    ocio_config: str | None = None,
    ocio_in: str = "sRGB",
) -> bool:
    """Transcode *clip* to a lightweight H.264 MP4 proxy in sRGB."""
    # Validate clip properties before ffmpeg call
    if not clip.first_file or not os.path.isfile(clip.first_file):
        return False
    if clip.is_sequence and not clip.frames:
        return False

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    vf_chain = [f"scale={PROXY_WIDTH}:-2"]
    color_filter = _color_transform_filter(ocio_config, ocio_in)
    if color_filter:
        vf_chain.append(color_filter)

    vf_str = ",".join(vf_chain)

    if clip.is_sequence:
        padding = clip.padding
        input_pattern = os.path.join(
            str(clip.directory),
            f"{clip.base_name}{clip.separator}%0{padding}d.{clip.extension}",
        )
        cmd = [
            "ffmpeg", "-y",
            "-start_number", str(clip.first_frame),
            "-i", input_pattern,
            "-vf", vf_str,
            "-c:v", "libx264",
            "-crf", str(PROXY_CRF),
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", clip.first_file,
            "-vf", vf_str,
            "-c:v", "libx264",
            "-crf", str(PROXY_CRF),
            "-pix_fmt", "yuv420p",
            output_path,
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_SUBPROCESS_FLAGS, timeout=600)
        if result.returncode != 0:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "ffmpeg proxy generation failed (rc=%d): %s",
                result.returncode,
                result.stderr[-2000:] if result.stderr else "(no stderr)",
            )
            return False
        return True
    except FileNotFoundError:
        import logging as _logging
        _logging.getLogger(__name__).error("ffmpeg not found. Install ffmpeg and ensure it is on PATH.")
        return False
    except subprocess.TimeoutExpired:
        import logging as _logging
        _logging.getLogger(__name__).warning("ffmpeg proxy generation timed out for: %s", clip.first_file)
        return False


def _thumbnail_from_sequence(
    clip: Clip,
    output_path: str,
    frame_index: int | None,
    ocio_config: str | None = None,
    ocio_in: str = "sRGB",
) -> bool:
    if frame_index is None:
        frame_index = len(clip.frames) // 2
    frame_index = max(0, min(frame_index, len(clip.frames) - 1))
    target_frame = clip.frames[frame_index]

    padding = clip.padding
    src_file = os.path.join(
        str(clip.directory),
        f"{clip.base_name}{clip.separator}{str(target_frame).zfill(padding)}.{clip.extension}",
    )

    vf_chain = [f"scale={THUMB_WIDTH}:-1"]
    color_filter = _color_transform_filter(ocio_config, ocio_in)
    if color_filter:
        vf_chain.append(color_filter)
    vf_str = ",".join(vf_chain)

    cmd = [
        "ffmpeg", "-y",
        "-i", src_file,
        "-vf", vf_str,
        "-frames:v", "1",
        "-q:v", str(THUMB_QUALITY),
        output_path,
    ]

    try:
        # 90s timeout for 8K footage, network storage, and heavy codecs (H.265, ProRes RAW)
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_SUBPROCESS_FLAGS, timeout=90)
        if result.returncode != 0:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "ffmpeg thumbnail (sequence) failed (rc=%d): %s",
                result.returncode,
                result.stderr[-2000:] if result.stderr else "(no stderr)",
            )
            return False
        return True
    except FileNotFoundError:
        import logging as _logging
        _logging.getLogger(__name__).error("ffmpeg not found. Install ffmpeg and ensure it is on PATH.")
        return False
    except subprocess.TimeoutExpired:
        import logging as _logging
        _logging.getLogger(__name__).warning("ffmpeg thumbnail timed out for sequence: %s", clip.first_file)
        return False


def _thumbnail_from_movie(
    clip: Clip,
    output_path: str,
    frame_index: int | None,
    ocio_config: str | None = None,
    ocio_in: str = "sRGB",
) -> bool:
    # Seek to ~40% of the file to avoid leader/slate (VFX best practice)
    if frame_index is None:
        # Calculate 40% offset from file duration to skip slates/leaders
        from ramses_ingest.prober import probe_file
        try:
            info = probe_file(clip.first_file)
            if info.duration_seconds > 0:
                seek_seconds = str(info.duration_seconds * 0.4)
            else:
                seek_seconds = "0"
        except Exception:
            seek_seconds = "0"
    else:
        seek_seconds = str(frame_index)

    vf_chain = [f"scale={THUMB_WIDTH}:-1"]
    color_filter = _color_transform_filter(ocio_config, ocio_in)
    if color_filter:
        vf_chain.append(color_filter)
    vf_str = ",".join(vf_chain)

    cmd = [
        "ffmpeg", "-y",
        "-ss", seek_seconds,
        "-i", clip.first_file,
        "-vf", vf_str,
        "-frames:v", "1",
        "-q:v", str(THUMB_QUALITY),
        output_path,
    ]

    try:
        # 90s timeout for 8K footage, network storage, and heavy codecs (H.265, ProRes RAW)
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=_SUBPROCESS_FLAGS, timeout=90)
        if result.returncode != 0:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "ffmpeg thumbnail (movie) failed (rc=%d): %s",
                result.returncode,
                result.stderr[-2000:] if result.stderr else "(no stderr)",
            )
            return False
        return True
    except FileNotFoundError:
        import logging as _logging
        _logging.getLogger(__name__).error("ffmpeg not found. Install ffmpeg and ensure it is on PATH.")
        return False
    except subprocess.TimeoutExpired:
        import logging as _logging
        _logging.getLogger(__name__).warning("ffmpeg thumbnail timed out for movie: %s", clip.first_file)
        return False