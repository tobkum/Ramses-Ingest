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
# Examples: name.0001.exr, name_0001.exr, project_v01_shot_0030.exr (matches 0030, not 01)
# Uses GREEDY .+ to explicitly match from the end (VFX convention: frames always at end)
# Minimum 2 digits for frame numbers to align with pyseq frame_pattern
RE_FRAME_PADDING = re.compile(r"^(?P<base>.+)(?P<sep>[\._])(?P<frame>\d{2,})\.(?P<ext>[a-zA-Z0-9]+)$")

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


def scan_directory(root: str | Path) -> list[Clip]:
    """Scan *root* for media files and return detected clips using pyseq.

    Uses ``pyseq`` for sequence detection, with a fallback for single-frame
    sequences that pyseq might treat as standalone items.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    clips: list[Clip] = []

    # Helper to process a single directory
    def _process_dir(dir_path: Path):
        # pyseq.get_sequences expects a string path
        # Use frame_pattern to require 2+ digits (matches our RE_FRAME_PADDING)
        try:
            seqs = pyseq.get_sequences(str(dir_path), frame_pattern=r'\d{2,}')
        except OSError:
            return

        for s in seqs:
            # Determine if it's a sequence or single file
            is_seq = len(s) > 1
            frames = []
            padding = 4
            separator = "."  # Default separator

            # Check for single-frame sequences (e.g. plate.1001.exr alone)
            if len(s) == 1:
                item_name = s[0].name
                # Check our regex to see if it *should* be a sequence
                m = RE_FRAME_PADDING.match(item_name)
                if m:
                    ext = m.group("ext").lower()
                    separator = m.group("sep")  # Capture separator (. or _)
                    # Exclude movies from being sequences
                    if ext not in MOVIE_EXTENSIONS:
                        is_seq = True
                        frame_str = m.group("frame")
                        frames = [int(frame_str)]
                        padding = len(frame_str)
                        base = m.group("base")
                    else:
                        # Movie file matching padding pattern (shot_001.mov) -> Movie
                        is_seq = False
                        base = m.group("base") + m.group("sep") + m.group("frame")
                else:
                    # No pattern match -> Movie or simple image
                    is_seq = False
                    if "." in item_name:
                        base, ext_raw = item_name.rsplit(".", 1)
                        ext = ext_raw.lower()
                    else:
                        base = item_name
                        ext = ""

            else:
                # Multi-frame sequence detected by pyseq
                # BUT: Could be movie files with frame numbers (e.g., shot_100.mov, shot_110.mov)
                # Extract metadata first to check extension
                head = s.head()
                tail = s.tail()
                ext = tail.strip(".").lower()

                # Check if this is actually movie files (not a sequence)
                if ext in MOVIE_EXTENSIONS:
                    # pyseq incorrectly grouped movie files - unpack them as individual clips
                    for item in s:
                        item_name = item.name
                        if "." in item_name:
                            base, ext_raw = item_name.rsplit(".", 1)
                            ext = ext_raw.lower()
                        else:
                            continue  # Skip malformed filenames

                        full_path = os.path.join(str(dir_path), item_name)
                        clip = Clip(
                            base_name=base,
                            extension=ext,
                            directory=dir_path,
                            is_sequence=False,
                            frames=[],
                            first_file=full_path,
                            _padding=4,
                            _separator="."
                        )
                        clips.append(clip)
                    continue  # Skip normal sequence processing

                # Valid image sequence
                is_seq = True
                base = head.rstrip("._")
                frames = [f.frame for f in s]
                frames.sort()

                # Padding: deduce from first item
                first_name = s[0].name
                m = RE_FRAME_PADDING.match(first_name)
                if m:
                    padding = len(m.group("frame"))
                    separator = m.group("sep")
                else:
                    padding = 4 # Fallback
            
            # Filter by allowed extensions
            if ext not in MEDIA_EXTENSIONS:
                continue

            # Construct full path to first file
            full_path = os.path.join(str(dir_path), s[0].name)

            # Create Clip
            clip = Clip(
                base_name=base,
                extension=ext,
                directory=dir_path,
                is_sequence=is_seq,
                frames=frames if is_seq else [],
                first_file=full_path,
                _padding=padding,
                _separator=separator
            )
            clips.append(clip)

    try:
        # Recursive walk
        for root_dir, dirs, _ in os.walk(root):
            _process_dir(Path(root_dir))

    except PermissionError:
        logger.warning(f"Permission denied accessing {root}")
    except OSError as e:
        logger.warning(f"Error accessing {root}: {e}")

    return clips

