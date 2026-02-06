# -*- coding: utf-8 -*-
"""Tests for ramses_ingest.scanner."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.scanner import scan_directory, Clip, RE_FRAME_PADDING


class TestFramePaddingRegex(unittest.TestCase):
    def test_standard_padding(self):
        m = RE_FRAME_PADDING.match("plate.0001.exr")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("base"), "plate")
        self.assertEqual(m.group("frame"), "0001")
        self.assertEqual(m.group("ext"), "exr")

    def test_long_name(self):
        m = RE_FRAME_PADDING.match("SEQ010_SH020_PLATE.001234.dpx")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("base"), "SEQ010_SH020_PLATE")
        self.assertEqual(m.group("frame"), "001234")

    def test_movie_no_match(self):
        m = RE_FRAME_PADDING.match("shot.mov")
        self.assertIsNone(m)

    def test_single_digit_no_match(self):
        """Single digit frame numbers should not match (too ambiguous)."""
        m = RE_FRAME_PADDING.match("plate.1.exr")
        self.assertIsNone(m)


class TestScanDirectory(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _touch(self, relpath):
        full = os.path.join(self.tmpdir, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        Path(full).touch()

    def test_detects_image_sequence(self):
        for i in range(1, 25):
            self._touch(f"plate.{i:04d}.exr")

        clips = scan_directory(self.tmpdir)
        self.assertEqual(len(clips), 1)
        clip = clips[0]
        self.assertTrue(clip.is_sequence)
        self.assertEqual(clip.base_name, "plate")
        self.assertEqual(clip.extension, "exr")
        self.assertEqual(clip.frame_count, 24)
        self.assertEqual(clip.first_frame, 1)
        self.assertEqual(clip.last_frame, 24)

    def test_detects_movie_file(self):
        self._touch("shot_010.mov")

        clips = scan_directory(self.tmpdir)
        self.assertEqual(len(clips), 1)
        clip = clips[0]
        self.assertFalse(clip.is_sequence)
        self.assertEqual(clip.base_name, "shot_010")
        self.assertEqual(clip.extension, "mov")

    def test_separate_sequences(self):
        for i in range(1, 5):
            self._touch(f"plate_A.{i:04d}.exr")
            self._touch(f"plate_B.{i:04d}.exr")

        clips = scan_directory(self.tmpdir)
        seqs = [c for c in clips if c.is_sequence]
        self.assertEqual(len(seqs), 2)
        names = {c.base_name for c in seqs}
        self.assertEqual(names, {"plate_A", "plate_B"})

    def test_ignores_non_media(self):
        self._touch("readme.txt")
        self._touch("scene.blend")

        clips = scan_directory(self.tmpdir)
        self.assertEqual(len(clips), 0)

    def test_subdirectory_walk(self):
        for i in range(1, 3):
            self._touch(f"subdir/plate.{i:04d}.exr")

        clips = scan_directory(self.tmpdir)
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0].base_name, "plate")

    def test_missing_frames(self):
        for i in [1, 2, 4, 5]:
            self._touch(f"plate.{i:04d}.exr")

        clips = scan_directory(self.tmpdir)
        self.assertEqual(clips[0].missing_frames, [3])

    def test_nonexistent_directory(self):
        with self.assertRaises(FileNotFoundError):
            scan_directory("/nonexistent/path")


if __name__ == "__main__":
    unittest.main()
