# -*- coding: utf-8 -*-
"""Thumbnail and video proxy generation via ffmpeg.

Responsibilities:
    - Extract a representative frame from a clip (middle frame).
    - Resize and save as JPG thumbnail for the Ramses Client.
    - Optionally transcode a lightweight MP4 proxy for scrubbing.
    - Always output thumbnails and proxies in sRGB for web compatibility.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from ramses_ingest.scanner import Clip


def _escape_ffmpeg_filter_path(path: str) -> str:
    """Escape file path for use in FFmpeg filter strings.
    
    FFmpeg filter syntax requires escaping colons, but Windows drive letters
    (C:, D:, etc.) must be preserved. This also handles UNC paths on network shares.
    
    Args:
        path: File path (Windows or Unix)
        
    Returns:
        Properly escaped path for FFmpeg filter string
        
    Examples:
        C:\\OCIO\\config.ocio → C:/OCIO/config.ocio
        \\\\server\\share\\config.ocio → //server/share/config.ocio  
        /mnt/ocio:v2/config.ocio → /mnt/ocio\\:v2/config.ocio
    """
    # Convert backslashes to forward slashes for FFmpeg
    clean = path.replace("\\", "/")
    
    # Escape ALL colons except Windows drive letters (single letter followed by colon at start)
    # Pattern: Match colons not preceded by start-of-string + single letter
    clean = re.sub(r'(?<!^[A-Za-z]):', r'\\:', clean)
    
    return clean

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
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

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

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    vf_chain = [f"scale={PROXY_WIDTH}:-2"]
    if ocio_config and os.path.isfile(ocio_config):
        clean_path = _escape_ffmpeg_filter_path(ocio_config)
        vf_chain.append(f"ocio=config={clean_path}:in_label={ocio_in}:out_label=sRGB")

    vf_str = ",".join(vf_chain)

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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
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
        f"{clip.base_name}.{str(target_frame).zfill(padding)}.{clip.extension}",
    )

    vf_chain = [f"scale={THUMB_WIDTH}:-1"]
    if ocio_config and os.path.isfile(ocio_config):
        clean_path = _escape_ffmpeg_filter_path(ocio_config)
        vf_chain.append(f"ocio=config={clean_path}:in_label={ocio_in}:out_label=sRGB")
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
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
    if ocio_config and os.path.isfile(ocio_config):
        clean_path = _escape_ffmpeg_filter_path(ocio_config)
        vf_chain.append(f"ocio=config={clean_path}:in_label={ocio_in}:out_label=sRGB")
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False