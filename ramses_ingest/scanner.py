# -*- coding: utf-8 -*-
"""File discovery and image-sequence detection.

Responsibilities:
    - Walk a delivery folder and collect all media files.
    - Group numbered files into sequences (e.g. plate.0001.exr … plate.0096.exr).
    - Represent each detected clip as a ``Clip`` dataclass ready for matching.
"""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pyseq

logger = logging.getLogger(__name__)

# Matches frame numbers at the END of the filename (before extension)
# Examples: name.0001.exr, name_0001.exr, name-0001.exr, project_v01_shot_0030.exr (matches 0030, not 01)
# Uses GREEDY .+ to explicitly match from the end (VFX convention: frames always at end)
# Minimum 2 digits for frame numbers to align with pyseq frame_pattern
RE_FRAME_PADDING = re.compile(r"^(?P<base>.+)(?P<sep>[\._-])(?P<frame>\d{2,})\.(?P<ext>[a-zA-Z0-9]+)$")

# Common media extensions (lowercase)
IMAGE_EXTENSIONS = {
    "exr", "dpx", "tif", "tiff", "png", "tga", "jpg", "jpeg", "hdr"
}
MOVIE_EXTENSIONS = {
    "mov", "mp4", "mxf", "avi", "mkv"
}
MEDIA_EXTENSIONS = frozenset(IMAGE_EXTENSIONS | MOVIE_EXTENSIONS)


@dataclass
class Clip:
    """A single detected clip — either a movie file or an image sequence."""

    base_name: str
    """Filename stem without frame number and extension (e.g. ``SEQ010_SH010``)."""

    extension: str
    """Lowercase file extension without dot (e.g. ``exr``)."""

    directory: Path
    """Absolute path to the folder containing the files."""

    is_sequence: bool = False
    """True if this clip is an image sequence, False if a single movie file."""

    frames: list[int] = field(default_factory=list)
    """Sorted list of frame numbers (empty for movie files)."""

    first_file: str = ""
    """Absolute path to the first (or only) file — useful for probing."""

    _padding: int = 4
    """Detected zero-padding width from original filename (e.g. '0001' = 4)."""

    _separator: str = "."
    """Frame number separator character (. or _) detected from original filename."""

    @property
    def frame_count(self) -> int:
        """Number of files/frames in this clip. Returns 1 for movie files."""
        if self.is_sequence and self.frames:
            return len(self.frames)
        return 1

    @property
    def first_frame(self) -> int:
        return self.frames[0] if self.frames else 0

    @property
    def last_frame(self) -> int:
        return self.frames[-1] if self.frames else 0

    @property
    def padding(self) -> int:
        """Detected zero-padding width from the first frame number."""
        return self._padding

    @property
    def separator(self) -> str:
        """Frame number separator character from original filename."""
        return self._separator

    @property
    def missing_frames(self) -> list[int]:
        """Frame numbers that are missing from a contiguous range."""
        if len(self.frames) < 2:
            return []
        full_range = set(range(self.frames[0], self.frames[-1] + 1))
        return sorted(full_range - set(self.frames))


def group_files(file_paths: list[str | Path]) -> list[Clip]:
    """Consolidate a list of file paths into a list of Clips.

    The 'Smart Way':
    1. Filter by extension first (Movies are always standalone).
    2. Group remaining files by (Directory, BaseName, Padding, Extension).
    3. Return a unified list of movie and sequence Clips.
    """
    from collections import defaultdict

    movie_clips: list[Clip] = []
    image_files: list[tuple[str, str, int, str, str, Path, int]] = [] # (base, sep, frame, ext, filename, dir, padding)

    # 1. Filter First
    for p in file_paths:
        p = Path(p)
        name = p.name
        ext = p.suffix.lstrip(".").lower()
        if ext not in MEDIA_EXTENSIONS:
            continue

        if ext in MOVIE_EXTENSIONS:
            # Movies are NEVER sequences
            movie_clips.append(Clip(
                base_name=p.stem,
                extension=ext,
                directory=p.parent,
                is_sequence=False,
                first_file=str(p)
            ))
        else:
            # Potential sequence member
            m = RE_FRAME_PADDING.match(name)
            if m:
                image_files.append((
                    m.group("base"),
                    m.group("sep"),
                    int(m.group("frame")),
                    ext,
                    str(p),
                    p.parent,
                    len(m.group("frame")) # PADDING is now part of the identification
                ))
            else:
                # Standalone image (no padding detected)
                movie_clips.append(Clip(
                    base_name=p.stem,
                    extension=ext,
                    directory=p.parent,
                    is_sequence=False,
                    first_file=str(p)
                ))

    # 2. Group Images (Padding Aware)
    # Key includes: Directory, BaseName, Separator, Padding, and Extension
    buckets = defaultdict(list)
    for base, sep, frame, ext, full_path, directory, padding in image_files:
        key = (str(directory), base, sep, padding, ext)
        buckets[key].append((frame, full_path))

    sequence_clips: list[Clip] = []
    for (dir_path, base, sep, padding, ext), frames in buckets.items():
        frames.sort()
        sequence_clips.append(Clip(
            base_name=base,
            extension=ext,
            directory=Path(dir_path),
            is_sequence=True,
            frames=[f[0] for f in frames],
            first_file=frames[0][1],
            _padding=padding,
            _separator=sep
        ))

    return movie_clips + sequence_clips


def scan_directory(root: str | Path) -> list[Clip]:
    """Scan *root* for media files and return detected clips.

    Recursively collects all files and delegates grouping to group_files.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    all_files = []
    try:
        for root_dir, _, filenames in os.walk(root):
            for f in filenames:
                all_files.append(os.path.join(root_dir, f))
    except (PermissionError, OSError) as e:
        logger.warning(f"Error accessing {root}: {e}")

    return group_files(all_files)

