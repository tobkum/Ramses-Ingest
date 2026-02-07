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
import threading
from dataclasses import dataclass, asdict
from pathlib import Path

# Cache Settings
CACHE_PATH = os.path.join(os.path.expanduser("~"), ".ramses_ingest_cache.json")
_METADATA_CACHE: dict[str, dict] = {}
_CACHE_ACCESS_TIMES: dict[str, float] = {}  # Track last access time for LRU
_CACHE_LOCK = threading.Lock()  # Thread-safe cache access
_CACHE_DIRTY = False  # Batch writes instead of writing on every probe
_MAX_CACHE_SIZE = 5000

def _load_cache():
    global _METADATA_CACHE, _CACHE_ACCESS_TIMES
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                _METADATA_CACHE = data.get("cache", {})
                _CACHE_ACCESS_TIMES = data.get("access_times", {})
        except Exception:
            _METADATA_CACHE = {}
            _CACHE_ACCESS_TIMES = {}

def _save_cache():
    global _METADATA_CACHE, _CACHE_ACCESS_TIMES, _CACHE_DIRTY
    try:
        # Prune cache using LRU if it exceeds limit
        if len(_METADATA_CACHE) > _MAX_CACHE_SIZE:
            import time
            # Sort by access time (oldest first) and remove oldest entries
            sorted_keys = sorted(_CACHE_ACCESS_TIMES.items(), key=lambda x: x[1])
            num_to_remove = len(_METADATA_CACHE) - _MAX_CACHE_SIZE

            for key, _ in sorted_keys[:num_to_remove]:
                _METADATA_CACHE.pop(key, None)
                _CACHE_ACCESS_TIMES.pop(key, None)

        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "cache": _METADATA_CACHE,
                "access_times": _CACHE_ACCESS_TIMES
            }, f)
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
    duration_seconds: float = 0.0
    frame_count: int = 0
    start_timecode: str = ""

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0


def probe_file(file_path: str | Path) -> MediaInfo:
    """Run ffprobe on *file_path* and return a ``MediaInfo``.

    Checks persistent cache first (Key = Path + MTime).
    """
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

    # 2. Run ffprobe
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

    info = MediaInfo(
        width=int(s.get("width", 0)),
        height=int(s.get("height", 0)),
        fps=round(fps, 3),
        codec=s.get("codec_name", ""),
        pix_fmt=s.get("pix_fmt", ""),
        color_space=s.get("color_space", ""),
        color_transfer=s.get("color_transfer", ""),
        color_primaries=s.get("color_primaries", ""),
        duration_seconds=float(s.get("duration", 0.0)),
        frame_count=int(s.get("nb_frames", 0)),
        start_timecode=tc,
    )

    # 3. Update Cache (thread-safe)
    if info.is_valid and cache_key:
        import time
        with _CACHE_LOCK:
            global _CACHE_DIRTY
            _METADATA_CACHE[cache_key] = asdict(info)
            _CACHE_ACCESS_TIMES[cache_key] = time.time()
            _CACHE_DIRTY = True
            # Note: Cache is flushed at end of processing via flush_cache()

    return info
