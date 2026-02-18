# -*- coding: utf-8 -*-
"""Media metadata extraction via PyAV/ffprobe with persistent caching.

Responsibilities:
    - Probe a single file to extract resolution, fps, duration, codec, colorspace.
    - Return a ``MediaInfo`` dataclass ready for pipeline use.
    - Cache technical metadata to disk based on file mtime for performance.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import logging
import time
import atexit
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import OpenImageIO as oiio
except ImportError:
    oiio = None
    logger.warning("OpenImageIO not available. EXR/DPX metadata extraction (especially PixelAspectRatio) will be limited.")

# Image formats where OIIO reads PAR from the file header (ffprobe/PyAV can't)
_OIIO_PAR_EXTENSIONS = {".exr", ".dpx", ".tif", ".tiff", ".hdr"}

# Subprocess creation flags to hide console windows on Windows
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# FFmpeg/ISO color-space integer-to-string mappings (shared by PyAV and cache deserialization)
_COLORSPACE_MAP = {0: "RGB", 1: "BT709", 2: "Unspecified", 4: "FCC", 5: "BT470BG", 6: "SMPTE170M", 7: "SMPTE240M", 8: "YCGCO", 9: "BT2020NC", 10: "BT2020C"}
_TRANSFER_MAP = {1: "BT709", 2: "Unspecified", 4: "Gamma22", 5: "Gamma28", 8: "Linear", 11: "XVYCC", 13: "SRGB", 14: "BT2020_10", 16: "SMPTE2084", 18: "HLG"}
_PRIMARIES_MAP = {1: "BT709", 2: "Unspecified", 4: "BT470M", 5: "BT470BG", 6: "SMPTE170M", 9: "BT2020", 11: "DCI-P3", 12: "Display-P3"}

_COLOR_MAPS = {
    "colorspace": _COLORSPACE_MAP,
    "transfer": _TRANSFER_MAP,
    "primaries": _PRIMARIES_MAP,
}


def _resolve_color_int(val: int, attr_name: str) -> str:
    """Map an integer color value to its human-readable name."""
    for key, mapping in _COLOR_MAPS.items():
        if key in attr_name.lower():
            return mapping.get(val, str(val))
    return str(val)

# Try to import PyAV for 10x faster video probing
try:
    import av
    _HAS_AV = True
except ImportError:
    _HAS_AV = False
    logger.warning("PyAV not available, using slower ffprobe subprocesses. Install with: pip install av")

# Cache Settings
CACHE_PATH_MSGPACK = os.path.join(os.path.expanduser("~"), ".ramses_ingest_cache.msgpack")
CACHE_PATH_JSON = os.path.join(os.path.expanduser("~"), ".ramses_ingest_cache.json")  # Legacy
_METADATA_CACHE: dict[str, dict] = {}
_CACHE_ACCESS_TIMES: dict[str, float] = {}  # Track last access time for LRU
_CACHE_LOCK = threading.Lock()  # Thread-safe cache access
_CACHE_DIRTY = False  # Batch writes instead of writing on every probe (must be accessed with _CACHE_LOCK)
_MAX_CACHE_SIZE = 5000

# Try to import msgpack for 10x faster cache (fallback to JSON if unavailable)
try:
    import msgpack
    _USE_MSGPACK = True
except ImportError:
    _USE_MSGPACK = False
    logger.warning("msgpack not available, using slower JSON cache. Install with: pip install msgpack")

def _load_cache():
    """Load cache from disk, auto-migrating from JSON to msgpack if needed."""
    global _METADATA_CACHE, _CACHE_ACCESS_TIMES, _CACHE_DIRTY

    # Initialize to safe defaults to prevent crashes on load failure
    _METADATA_CACHE = {}
    _CACHE_ACCESS_TIMES = {}

    # Try msgpack first (10x faster)
    if _USE_MSGPACK and os.path.exists(CACHE_PATH_MSGPACK):
        try:
            with open(CACHE_PATH_MSGPACK, "rb") as f:
                data = msgpack.unpack(f, raw=False)
                if isinstance(data, dict):
                    _METADATA_CACHE = data.get("cache", {})
                    _CACHE_ACCESS_TIMES = data.get("access_times", {})
            return
        except Exception as e:
            logger.warning(f"Failed to load msgpack cache: {e}, trying JSON fallback")
            # Reset to empty on msgpack failure
            _METADATA_CACHE = {}
            _CACHE_ACCESS_TIMES = {}

    # Fallback to JSON (legacy or if msgpack failed)
    if os.path.exists(CACHE_PATH_JSON):
        try:
            with open(CACHE_PATH_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _METADATA_CACHE = data.get("cache", {})
                    _CACHE_ACCESS_TIMES = data.get("access_times", {})

            # Auto-migrate to msgpack if available
            if _USE_MSGPACK and _METADATA_CACHE:
                logger.info(f"Migrating cache from JSON to msgpack ({len(_METADATA_CACHE)} entries)")
                with _CACHE_LOCK:
                    _CACHE_DIRTY = True
                    _save_cache()  # This will save in msgpack format
                # Clean up old JSON file after successful migration
                try:
                    os.remove(CACHE_PATH_JSON)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to load JSON cache: {e}")
            # Already initialized to empty above

def _prune_lru_cache():
    """Prune cache using LRU if it exceeds limit.

    Must be called with _CACHE_LOCK held.
    """
    global _METADATA_CACHE, _CACHE_ACCESS_TIMES
    current_size = len(_METADATA_CACHE)
    if current_size > _MAX_CACHE_SIZE:
        # Sort by access time (oldest first) and remove oldest entries
        sorted_keys = sorted(_CACHE_ACCESS_TIMES.items(), key=lambda x: x[1])
        num_to_remove = current_size - _MAX_CACHE_SIZE

        for key, _ in sorted_keys[:num_to_remove]:
            _METADATA_CACHE.pop(key, None)
            _CACHE_ACCESS_TIMES.pop(key, None)

def _save_cache():
    """Save cache to disk in msgpack format (or JSON fallback).

    Must be called with _CACHE_LOCK held.
    """
    global _METADATA_CACHE, _CACHE_ACCESS_TIMES, _CACHE_DIRTY
    try:
        # Prune cache using LRU if it exceeds limit
        _prune_lru_cache()

        cache_data = {
            "cache": _METADATA_CACHE,
            "access_times": _CACHE_ACCESS_TIMES
        }

        if _USE_MSGPACK:
            # Use msgpack (10x faster)
            cache_path = CACHE_PATH_MSGPACK
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as f:
                msgpack.pack(cache_data, f)
        else:
            # Fallback to JSON
            cache_path = CACHE_PATH_JSON
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f)

        _CACHE_DIRTY = False
    except Exception:
        pass

def flush_cache():
    """Flush dirty cache to disk. Call this at the end of processing."""
    global _CACHE_DIRTY
    with _CACHE_LOCK:
        if _CACHE_DIRTY:
            _save_cache()

# Initialize cache on module load
_load_cache()

# Register atexit handler to ensure cache is saved even on crash/SIGINT
atexit.register(flush_cache)

# Startup Check: Warn if ffprobe is missing
def check_ffprobe() -> bool:
    """Check if ffprobe is available in the system PATH.

    Returns:
        True if ffprobe is found and executable, False otherwise.
    """
    try:
        subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            creationflags=_SUBPROCESS_FLAGS
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.warning("'ffprobe' not found in PATH. Subprocess-based extraction will fail.")
        return False

# Run check on import (logging only)
check_ffprobe()

def has_av() -> bool:
    """Check if PyAV is available for high-performance probing."""
    return _HAS_AV


@dataclass
class MediaInfo:
    """Technical metadata for a media file."""

    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    pix_fmt: str = ""
    color_space: str = ""
    color_transfer: str = ""
    color_primaries: str = "" # Added Primaries
    pixel_aspect_ratio: float = 1.0
    duration_seconds: float = 0.0
    frame_count: int = 0
    start_timecode: str = ""

    def __post_init__(self):
        """Fix cached or raw integer values after initialization."""
        self.color_space = self._fix_color_val(self.color_space, "colorspace")
        self.color_transfer = self._fix_color_val(self.color_transfer, "transfer")
        self.color_primaries = self._fix_color_val(self.color_primaries, "primaries")

    @staticmethod
    def _fix_color_val(val, attr_name):
        if not isinstance(val, int):
            try:
                val = int(val)
            except (ValueError, TypeError):
                # If it's already a string (e.g. from ffprobe), ensure it's uppercase for the GUI
                return str(val or "").upper()
        return _resolve_color_int(val, attr_name).upper()

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0


def _probe_image_oiio(file_path: str) -> MediaInfo:
    """Probe an image file via OpenImageIO, extracting all relevant metadata.

    Used for EXR, DPX, TIFF, HDR — formats where OIIO reads header attributes
    (like PixelAspectRatio) that ffprobe cannot access.
    """
    if oiio is None:
        return MediaInfo()

    try:
        inp = oiio.ImageInput.open(file_path)
        if not inp:
            oiio.geterror()  # Clear pending error to prevent stderr noise at exit
            return MediaInfo()

        spec = inp.spec()
        par = spec.get_float_attribute("PixelAspectRatio", 1.0)
        if par <= 0:
            par = 1.0

        # Map OIIO format to a human-readable codec/format name
        fmt = inp.format_name() or ""

        # Color space: OIIO stores this in the "oiio:ColorSpace" attribute
        color_space = spec.get_string_attribute("oiio:ColorSpace", "")

        info = MediaInfo(
            width=spec.width,
            height=spec.height,
            fps=0.0,  # Single frame — FPS comes from the sequence context
            codec=fmt,
            pix_fmt=str(spec.format),
            color_space=color_space,
            pixel_aspect_ratio=par,
        )
        inp.close()
        return info
    except Exception:
        pass
    return MediaInfo()


def _probe_video_av(file_path: str) -> MediaInfo:
    """Probe a video file via PyAV (FFmpeg C-bindings).

    This is 10-20x faster than ffprobe subprocesses because it avoids
    process startup overhead and JSON serialization.
    """
    if not _HAS_AV:
        return MediaInfo()

    try:
        # We use 'with' to ensure container is closed even if parsing fails
        with av.open(file_path) as container:
            if not container.streams.video:
                return MediaInfo()

            stream = container.streams.video[0]
            
            # FPS: PyAV uses Fraction, convert to float
            fps = 0.0
            if stream.average_rate:
                fps = float(stream.average_rate)
            elif stream.base_rate:
                fps = float(stream.base_rate)

            # Duration and Frame Count
            duration = float(container.duration / av.time_base) if container.duration else 0.0
            nb_frames = stream.frames or 0
            # Fallback for missing nb_frames (common in some containers)
            if nb_frames <= 0 and duration > 0 and fps > 0:
                nb_frames = int(round(duration * fps))

            # Timecode: Check container metadata first, then stream
            tc = container.metadata.get("timecode", "")
            if not tc:
                tc = stream.metadata.get("timecode", "")

            # Pixel Aspect Ratio
            par = 1.0
            if stream.sample_aspect_ratio:
                par = float(stream.sample_aspect_ratio)

            # Extract color science metadata from codec context if available
            ctx = stream.codec_context
            
            # Safely stringify Enums or Integers if present
            def _safestr(val, attr_name=""):
                if val is None: return ""
                if hasattr(val, "name"):
                    return str(val.name)
                if isinstance(val, int):
                    return _resolve_color_int(val, attr_name)
                s = str(val)
                if "." in s: return s.split(".")[-1]
                return s

            return MediaInfo(
                width=stream.width or 0,
                height=stream.height or 0,
                fps=fps,
                codec=ctx.name or "",
                pix_fmt=stream.pix_fmt or "",
                color_space=_safestr(getattr(ctx, "colorspace", ""), "colorspace"),
                color_transfer=_safestr(getattr(ctx, "color_trc", ""), "transfer"),
                color_primaries=_safestr(getattr(ctx, "color_primaries", ""), "primaries"),
                pixel_aspect_ratio=par,
                duration_seconds=duration,
                frame_count=nb_frames,
                start_timecode=tc,
            )
    except Exception as e:
        logger.debug(f"PyAV probe failed for {file_path}: {e}")
        return MediaInfo()


def _probe_video_ffprobe(file_path: str) -> MediaInfo:
    """Fallback: Probe a video file via ffprobe subprocess."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        "-show_format",
        file_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=_SUBPROCESS_FLAGS,
            timeout=15,
        )
    except FileNotFoundError:
        raise FileNotFoundError(
            "ffprobe not found. Install FFmpeg and ensure it is on PATH."
        )
    except subprocess.TimeoutExpired:
        return MediaInfo()

    if result.returncode != 0:
        return MediaInfo()

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return MediaInfo()

    streams = data.get("streams", [])
    if not streams:
        return MediaInfo()

    s = streams[0]
    fmt = data.get("format", {})

    # Parse framerate from r_frame_rate (e.g. "24/1", "24000/1001")
    fps = 0.0
    r_fps = s.get("r_frame_rate", "0/1")
    try:
        num, den = r_fps.split("/")
        if int(den) != 0:
            fps = int(num) / int(den)
    except (ValueError, ZeroDivisionError):
        pass

    # Try to find timecode in stream tags, then format tags
    tc = s.get("tags", {}).get("timecode", "")
    if not tc:
        tc = fmt.get("tags", {}).get("timecode", "")

    # Frame count fallback (nb_frames is often missing in movies)
    nb_frames = int(s.get("nb_frames", 0))
    if nb_frames <= 0:
        dur = float(s.get("duration", 0.0))
        if dur > 0 and fps > 0:
            nb_frames = int(round(dur * fps))

    # Parse Pixel Aspect Ratio
    par = 1.0
    sar_str = s.get("sample_aspect_ratio", "")
    if sar_str and ":" in sar_str:
        try:
            sar_num, sar_den = sar_str.split(":")
            if int(sar_den) != 0:
                par = int(sar_num) / int(sar_den)
        except (ValueError, ZeroDivisionError):
            pass

    return MediaInfo(
        width=int(s.get("width", 0)),
        height=int(s.get("height", 0)),
        fps=fps,
        codec=s.get("codec_name", ""),
        pix_fmt=s.get("pix_fmt", ""),
        color_space=s.get("color_space", ""),
        color_transfer=s.get("color_transfer", ""),
        color_primaries=s.get("color_primaries", ""),
        pixel_aspect_ratio=par,
        duration_seconds=float(s.get("duration", 0.0)),
        frame_count=nb_frames,
        start_timecode=tc,
    )


def probe_file(file_path: str | Path) -> MediaInfo:
    """Probe *file_path* for media metadata and return a ``MediaInfo``.

    Prioritizes:
    1. Persistent Cache
    2. OIIO (for Image Sequences)
    3. PyAV (for Video Containers) - FAST
    4. ffprobe (Fallback) - SLOW
    """
    global _CACHE_DIRTY
    file_path = str(file_path)
    if not os.path.isfile(file_path):
        return MediaInfo()

    # 1. Check Cache (thread-safe)
    cache_key = None
    try:
        mtime = os.path.getmtime(file_path)
        cache_key = f"{file_path}|{mtime}"
        with _CACHE_LOCK:
            if cache_key in _METADATA_CACHE:
                _CACHE_ACCESS_TIMES[cache_key] = time.time()
                return MediaInfo(**_METADATA_CACHE[cache_key])
    except Exception:
        pass

    # 2. For image formats, use OIIO (reads EXR/DPX headers natively, including PAR)
    file_ext = Path(file_path).suffix.lower()
    if file_ext in _OIIO_PAR_EXTENSIONS:
        info = _probe_image_oiio(file_path)
    # 3. For video containers, prioritize PyAV (Native C-Bindings)
    elif _HAS_AV:
        info = _probe_video_av(file_path)
        # Fallback to ffprobe if PyAV failed to produce valid result
        if not info.is_valid:
            info = _probe_video_ffprobe(file_path)
    # 4. Ultimate fallback to ffprobe subprocess
    else:
        info = _probe_video_ffprobe(file_path)

    # Update Cache (thread-safe)
    if info.is_valid and cache_key:
        with _CACHE_LOCK:
            _METADATA_CACHE[cache_key] = asdict(info)
            _CACHE_ACCESS_TIMES[cache_key] = time.time()
            _CACHE_DIRTY = True
            _prune_lru_cache()

    return info
