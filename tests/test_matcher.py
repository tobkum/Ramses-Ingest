# -*- coding: utf-8 -*-
"""Tests for ramses_ingest.matcher."""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.scanner import Clip
from ramses_ingest.matcher import (
    match_clip,
    match_clips,
    NamingRule,
    MatchResult,
)


def _make_clip(base_name: str, directory: str = "delivery") -> Clip:
    return Clip(
        base_name=base_name,
        extension="exr",
        directory=Path(directory),
        is_sequence=True,
        frames=list(range(1, 97)),
        first_file=f"{directory}/{base_name}.0001.exr",
    )


class TestBuiltinRules(unittest.TestCase):
    def test_seq_shot_pattern(self):
        clip = _make_clip("SEQ010_SH020")
        result = match_clip(clip)
        self.assertTrue(result.matched)
        self.assertEqual(result.sequence_id, "SEQ010")
        self.assertEqual(result.shot_id, "SH020")

    def test_numeric_only(self):
        clip = _make_clip("010_0020")
        result = match_clip(clip)
        self.assertTrue(result.matched)
        self.assertEqual(result.sequence_id, "010")
        self.assertEqual(result.shot_id, "0020")

    def test_with_suffix(self):
        """Extra info after shot ID should still match."""
        clip = _make_clip("SEQ010_SH020_PLATE_v01")
        result = match_clip(clip)
        self.assertTrue(result.matched)
        self.assertEqual(result.sequence_id, "SEQ010")
        self.assertEqual(result.shot_id, "SH020")

    def test_dir_fallback(self):
        """If filename has only a shot-like pattern, use parent dir as sequence."""
        clip = _make_clip("SH030", directory="SEQ010")
        result = match_clip(clip)
        self.assertTrue(result.matched)
        self.assertEqual(result.shot_id, "SH030")
        # The dir-based rule should pick up the directory name
        self.assertEqual(result.sequence_id, "SEQ010")

    def test_no_match(self):
        clip = _make_clip("random_name_no_numbers")
        result = match_clip(clip)
        self.assertFalse(result.matched)


class TestCustomRules(unittest.TestCase):
    def test_custom_pattern_with_prefix(self):
        rule = NamingRule(
            pattern=r"EP\d+_(?P<sequence>\d+)_(?P<shot>\d+)",
            sequence_prefix="SEQ",
            shot_prefix="SH",
        )
        clip = _make_clip("EP01_010_0010")
        result = match_clip(clip, rules=[rule])
        self.assertTrue(result.matched)
        self.assertEqual(result.sequence_id, "SEQ010")
        self.assertEqual(result.shot_id, "SH0010")

    def test_dir_as_sequence(self):
        rule = NamingRule(
            pattern=r"(?P<shot>[A-Za-z]*\d+)",
            use_parent_dir_as_sequence=True,
        )
        clip = _make_clip("SH010_PLATE", directory="RollA")
        result = match_clip(clip, rules=[rule])
        self.assertTrue(result.matched)
        self.assertEqual(result.sequence_id, "RollA")
        self.assertEqual(result.shot_id, "SH010")


class TestBulkMatch(unittest.TestCase):
    def test_match_clips(self):
        clips = [
            _make_clip("SEQ010_SH010"),
            _make_clip("SEQ010_SH020"),
            _make_clip("garbage"),
        ]
        results = match_clips(clips)
        self.assertEqual(len(results), 3)
        self.assertTrue(results[0].matched)
        self.assertTrue(results[1].matched)
        self.assertFalse(results[2].matched)


if __name__ == "__main__":
    unittest.main()
