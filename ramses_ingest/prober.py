# -*- coding: utf-8 -*-
"""Media metadata extraction via ffprobe.

Responsibilities:
    - Probe a single file to extract resolution, fps, duration, codec, colorspace.
    - Return a ``MediaInfo`` dataclass ready for pipeline use.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


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
    duration_seconds: float = 0.0
    frame_count: int = 0
    start_timecode: str = ""

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0


def probe_file(file_path: str | Path) -> MediaInfo:
    """Run ffprobe on *file_path* and return a ``MediaInfo``.

    Raises ``FileNotFoundError`` if ffprobe is not on PATH.
    Returns an empty ``MediaInfo`` (is_valid=False) if probing fails.
    """
    file_path = str(file_path)
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

    return MediaInfo(
        width=int(s.get("width", 0)),
        height=int(s.get("height", 0)),
        fps=round(fps, 3),
        codec=s.get("codec_name", ""),
        pix_fmt=s.get("pix_fmt", ""),
        color_space=s.get("color_space", ""),
        color_transfer=s.get("color_transfer", ""),
        duration_seconds=float(s.get("duration", 0.0)),
        frame_count=int(s.get("nb_frames", 0)),
        start_timecode=tc,
    )
