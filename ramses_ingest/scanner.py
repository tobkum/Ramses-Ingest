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

import pyseq

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

    # Get all potential sequences/files from pyseq
    # pyseq.get_sequences returns a list of pyseq.Sequence objects
    try:
        # We walk manually to control recursion and allow filtering if needed,
        # but pyseq.get_sequences can also walk.
        # To match previous behavior (recursive), we can walk ourselves or let pyseq do it.
        # pyseq.get_sequences(path) is not recursive by default?
        # Checking docs/behavior: usually it scans the level.
        # Assuming we want to maintain recursive scan:
        
        # Helper to process a single directory
        def _process_dir(dir_path: Path):
            # pyseq.get_sequences expects a string path
            # Use frame_pattern to require 2+ digits (matches our RE_FRAME_PADDING)
            try:
                seqs = pyseq.get_sequences(str(dir_path), frame_pattern=r'\d{2,}')
            except OSError:
                return

            for s in seqs:
                # pyseq Sequence attributes:
                # s.name (filename of first item?) No, usually condensed.
                # s.head(), s.tail()
                # s.custom_format('%h') -> head
                
                # Determine if it's a sequence or single file
                # Pyseq treats single files as Sequence(len=1) with frame detected or None.
                
                is_seq = len(s) > 1
                frames = []
                padding = 4
                separator = "."  # Default separator

                # Check for single-frame sequences (e.g. plate.1001.exr alone)
                # If len=1, pyseq might not have parsed the frame.
                if len(s) == 1:
                    item_name = s[0].name
                    item_path = str(s[0])

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
                            ext = ext
                        else:
                            # Movie file matching padding pattern (shot_001.mov) -> Movie
                            is_seq = False
                            base = m.group("base") + m.group("sep") + m.group("frame")
                            ext = ext
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
                    is_seq = True
                    frames = [f.frame for f in s]

                    # Fix: Ensure frames are sorted (pyseq usually does, but good to be safe)
                    frames.sort()

                    # Extract metadata from the first item
                    # Pyseq head() includes separator often
                    head = s.head()
                    tail = s.tail()

                    # Base name: trip head separator if present
                    # s.head() -> "plate."
                    base = head.rstrip("._")

                    # Extension: s.tail() -> ".exr"
                    ext = tail.strip(".").lower()  # Must lowercase for MEDIA_EXTENSIONS comparison

                    # Padding: deduce from first item
                    # We can use regex on the first file to be precise
                    first_name = s[0].name
                    m = RE_FRAME_PADDING.match(first_name)
                    if m:
                        padding = len(m.group("frame"))
                        separator = m.group("sep")  # Capture separator (. or _)
                    else:
                        padding = 4 # Fallback
                
                # Filter by allowed extensions
                if ext not in MEDIA_EXTENSIONS:
                    continue

                # Construct full path to first file (pyseq Item only stores filename)
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

        # Recursive walk
        for root_dir, dirs, _ in os.walk(root):
            _process_dir(Path(root_dir))
            
    except PermissionError:
        print(f"Warning: Permission denied accessing {root}")
    except OSError as e:
        print(f"Warning: Error accessing {root}: {e}")

    return clips


