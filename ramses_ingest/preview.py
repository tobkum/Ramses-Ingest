# -*- coding: utf-8 -*-
"""Thumbnail and video proxy generation via ffmpeg.

Responsibilities:
    - Extract a representative frame from a clip (middle frame).
    - Resize and save as JPG thumbnail for the Ramses Client.
    - Optionally transcode a lightweight MP4 proxy for scrubbing.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ramses_ingest.scanner import Clip

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
) -> bool:
    """Extract a single frame from *clip* and save as JPEG at *output_path*.

    Args:
        clip: The source clip.
        output_path: Absolute path for the output JPG (including filename).
        frame_index: Which frame to extract (0-based). Defaults to middle frame.

    Returns:
        True on success.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if clip.is_sequence:
        return _thumbnail_from_sequence(clip, output_path, frame_index)
    else:
        return _thumbnail_from_movie(clip, output_path, frame_index)


def generate_proxy(
    clip: Clip,
    output_path: str,
) -> bool:
    """Transcode *clip* to a lightweight H.264 MP4 proxy.

    Args:
        clip: The source clip.
        output_path: Absolute path for the output MP4.

    Returns:
        True on success.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if clip.is_sequence:
        padding = clip.padding
        input_pattern = os.path.join(
            str(clip.directory),
            f"{clip.base_name}.%0{padding}d.{clip.extension}",
        )
        cmd = [
            "ffmpeg", "-y",
            "-start_number", str(clip.first_frame),
            "-i", input_pattern,
            "-vf", f"scale={PROXY_WIDTH}:-2",
            "-c:v", "libx264",
            "-crf", str(PROXY_CRF),
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", clip.first_file,
            "-vf", f"scale={PROXY_WIDTH}:-2",
            "-c:v", "libx264",
            "-crf", str(PROXY_CRF),
            "-pix_fmt", "yuv420p",
            output_path,
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _thumbnail_from_sequence(
    clip: Clip,
    output_path: str,
    frame_index: int | None,
) -> bool:
    if frame_index is None:
        frame_index = len(clip.frames) // 2
    frame_index = max(0, min(frame_index, len(clip.frames) - 1))
    target_frame = clip.frames[frame_index]

    padding = clip.padding
    src_file = os.path.join(
        str(clip.directory),
        f"{clip.base_name}.{str(target_frame).zfill(padding)}.{clip.extension}",
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", src_file,
        "-vf", f"scale={THUMB_WIDTH}:-1",
        "-frames:v", "1",
        "-q:v", str(THUMB_QUALITY),
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _thumbnail_from_movie(
    clip: Clip,
    output_path: str,
    frame_index: int | None,
) -> bool:
    # Seek to ~40% of the file to avoid leader/slate
    seek_seconds = "0"
    if frame_index is not None:
        seek_seconds = str(frame_index)

    cmd = [
        "ffmpeg", "-y",
        "-ss", seek_seconds,
        "-i", clip.first_file,
        "-vf", f"scale={THUMB_WIDTH}:-1",
        "-frames:v", "1",
        "-q:v", str(THUMB_QUALITY),
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
