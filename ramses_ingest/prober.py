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
_CACHE_LOCK = threading.Lock()  # Thread-safe cache access

def _load_cache():
    global _METADATA_CACHE
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                _METADATA_CACHE = json.load(f)
        except Exception:
            _METADATA_CACHE = {}

def _save_cache():
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_METADATA_CACHE, f)
    except Exception:
        pass

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
    try:
        mtime = os.path.getmtime(file_path)
        cache_key = f"{file_path}|{mtime}"
        with _CACHE_LOCK:
            if cache_key in _METADATA_CACHE:
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
    if info.is_valid:
        with _CACHE_LOCK:
            _METADATA_CACHE[cache_key] = asdict(info)
            _save_cache()

    return info
