# -*- coding: utf-8 -*-
"""Media metadata extraction via ffprobe with persistent caching.

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

import OpenImageIO as oiio

# Image formats where OIIO reads PAR from the file header (ffprobe can't)
_OIIO_PAR_EXTENSIONS = {".exr", ".dpx", ".tif", ".tiff", ".hdr"}

# Subprocess creation flags to hide console windows on Windows
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

logger = logging.getLogger(__name__)

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
        logger.warning("'ffprobe' not found in PATH. Media metadata extraction will fail.")
        return False

# Run check on import (logging only)
check_ffprobe()


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

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0


def _probe_image_oiio(file_path: str) -> MediaInfo:
    """Probe an image file via OpenImageIO, extracting all relevant metadata.

    Used for EXR, DPX, TIFF, HDR — formats where OIIO reads header attributes
    (like PixelAspectRatio) that ffprobe cannot access.
    """
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


def probe_file(file_path: str | Path) -> MediaInfo:
    """Probe *file_path* for media metadata and return a ``MediaInfo``.

    Uses OIIO for image formats (EXR, DPX, TIFF, HDR) and ffprobe for video.
    Checks persistent cache first (Key = Path + MTime).
    """
    global _CACHE_DIRTY
    file_path = str(file_path)
    if not os.path.isfile(file_path):
        return MediaInfo()

    # 1. Check Cache (thread-safe)
    cache_key = None
    try:
        import time
        mtime = os.path.getmtime(file_path)
        cache_key = f"{file_path}|{mtime}"
        with _CACHE_LOCK:
            if cache_key in _METADATA_CACHE:
                # Update access time for LRU
                _CACHE_ACCESS_TIMES[cache_key] = time.time()
                return MediaInfo(**_METADATA_CACHE[cache_key])
    except Exception:
        pass

    # 2. For image formats, use OIIO (reads EXR/DPX headers natively, including PAR)
    file_ext = Path(file_path).suffix.lower()
    if file_ext in _OIIO_PAR_EXTENSIONS:
        info = _probe_image_oiio(file_path)
        if info.is_valid and cache_key:
            import time
            with _CACHE_LOCK:
                _METADATA_CACHE[cache_key] = asdict(info)
                _CACHE_ACCESS_TIMES[cache_key] = time.time()
                _CACHE_DIRTY = True
        return info

    # 3. For video/other formats, run ffprobe
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

    # Parse Pixel Aspect Ratio from ffprobe's sample_aspect_ratio (video formats only;
    # image formats are handled by the OIIO path above and never reach here)
    par = 1.0
    sar_str = s.get("sample_aspect_ratio", "")
    if sar_str and ":" in sar_str:
        try:
            sar_num, sar_den = sar_str.split(":")
            if int(sar_den) != 0:
                par = int(sar_num) / int(sar_den)
        except (ValueError, ZeroDivisionError):
            pass

    info = MediaInfo(
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

    # 3. Update Cache (thread-safe)
    if info.is_valid and cache_key:
        import time
        with _CACHE_LOCK:
            _METADATA_CACHE[cache_key] = asdict(info)
            _CACHE_ACCESS_TIMES[cache_key] = time.time()
            _CACHE_DIRTY = True

            # Prune cache proactively to prevent unbounded growth during long GUI sessions
            _prune_lru_cache()
            # Note: Cache is flushed at end of processing via flush_cache()

    return info
