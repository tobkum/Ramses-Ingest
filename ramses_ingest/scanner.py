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
from dataclasses import dataclass, field
from pathlib import Path


# Matches a frame number between two dots: name.0001.exr
RE_FRAME_PADDING = re.compile(r"^(?P<base>.+?)\.(?P<frame>\d{2,})\.(?P<ext>[a-zA-Z0-9]+)$")

# Common media extensions (lowercase)
MEDIA_EXTENSIONS = frozenset({
    # Image sequences
    "exr", "dpx", "tif", "tiff", "png", "tga", "jpg", "jpeg", "hdr",
    # Movie containers
    "mov", "mp4", "mxf", "avi", "mkv",
})


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

    @property
    def frame_count(self) -> int:
        return len(self.frames) if self.is_sequence else 0

    @property
    def first_frame(self) -> int:
        return self.frames[0] if self.frames else 0

    @property
    def last_frame(self) -> int:
        return self.frames[-1] if self.frames else 0

    @property
    def padding(self) -> int:
        """Detected zero-padding width from the first frame number."""
        if not self.frames:
            return 4
        return max(len(str(self.frames[0])), 4)

    @property
    def missing_frames(self) -> list[int]:
        """Frame numbers that are missing from a contiguous range."""
        if len(self.frames) < 2:
            return []
        full_range = set(range(self.frames[0], self.frames[-1] + 1))
        return sorted(full_range - set(self.frames))


def scan_directory(root: str | Path) -> list[Clip]:
    """Scan *root* for media files and return detected clips.

    Walks the directory tree, groups image-sequence frames by their
    base name + extension, and returns each unique clip as a ``Clip``.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    # Collect sequence candidates: (dir, base, ext) -> [frame_numbers]
    seq_buckets: dict[tuple[str, str, str], list[int]] = {}
    # Standalone movie files
    movies: list[Clip] = []

    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            if ext not in MEDIA_EXTENSIONS:
                continue

            full_path = os.path.join(dirpath, fname)
            m = RE_FRAME_PADDING.match(fname)

            if m:
                # Image sequence frame
                base = m.group("base")
                frame = int(m.group("frame"))
                key = (dirpath, base, ext)
                seq_buckets.setdefault(key, []).append((frame, full_path))
            else:
                # Single movie or standalone image
                stem = fname.rsplit(".", 1)[0] if "." in fname else fname
                movies.append(Clip(
                    base_name=stem,
                    extension=ext,
                    directory=Path(dirpath),
                    is_sequence=False,
                    frames=[],
                    first_file=full_path,
                ))

    # Convert sequence buckets to Clip objects
    clips: list[Clip] = []
    for (dirpath, base, ext), frame_tuples in seq_buckets.items():
        frame_tuples.sort(key=lambda t: t[0])
        frames = [f for f, _ in frame_tuples]
        first_file = frame_tuples[0][1]
        clips.append(Clip(
            base_name=base,
            extension=ext,
            directory=Path(dirpath),
            is_sequence=True,
            frames=frames,
            first_file=first_file,
        ))

    # Movies after sequences (sequences are the primary use case)
    clips.extend(movies)
    clips.sort(key=lambda c: (str(c.directory), c.base_name))
    return clips
