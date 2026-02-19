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
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pyseq

logger = logging.getLogger(__name__)

# Matches frame numbers at the END of the filename (before extension).
# Examples: name.0001.exr, name_0001.exr, name-0001.exr, name0001.exr
#
# Uses a LAZY base (.+?) so the regex engine stops as soon as the trailing
# digits can be claimed as the frame number.  The separator is OPTIONAL
# ([\._-]?) to handle deliveries without a separator (e.g. shot0001.exr).
# When no separator is present, sep captures an empty string, which is stored
# on Clip._separator and used verbatim when reconstructing source paths.
RE_FRAME_PADDING = re.compile(r"^(?P<base>.+?)(?P<sep>[\._-]?)(?P<frame>\d+)\.(?P<ext>[a-zA-Z0-9]+)$")

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
    2. Group remaining files by (Directory, BaseName, Separator, Extension).
    3. Return a unified list of movie and sequence Clips.
    """
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

    # 2. Group Images
    # Key intentionally omits per-frame digit count so that frames crossing a
    # padding boundary (e.g. shot.0099.exr / shot.0100.exr / shot.101.exr) are
    # kept in the same sequence rather than split into separate clips.
    buckets = defaultdict(list)
    for base, sep, frame, ext, full_path, directory, padding in image_files:
        key = (str(directory), base, sep, ext)
        buckets[key].append((frame, full_path, padding))

    sequence_clips: list[Clip] = []
    for (dir_path, base, sep, ext), frames in buckets.items():
        frames.sort()
        # Representative padding comes from the first (lowest-numbered) frame.
        first_padding = frames[0][2]
        sequence_clips.append(Clip(
            base_name=base,
            extension=ext,
            directory=Path(dir_path),
            is_sequence=True,
            frames=[f[0] for f in frames],
            first_file=frames[0][1],
            _padding=first_padding,
            _separator=sep
        ))

    return movie_clips + sequence_clips


def scan_directory(root: str | Path) -> list[Clip]:
    """Scan *root* for media files and return detected clips.

    Recursively collects all files and delegates grouping to group_files.
    Explicitly prevents symlink recursion.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    all_files = []
    try:
        # followlinks=False prevents infinite recursion via symlinks
        for root_dir, _, filenames in os.walk(root, followlinks=False):
            for f in filenames:
                all_files.append(os.path.join(root_dir, f))
    except (PermissionError, OSError) as e:
        logger.warning(f"Error accessing {root}: {e}")

    return group_files(all_files)

