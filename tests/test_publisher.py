# -*- coding: utf-8 -*-
"""Tests for ramses_ingest.publisher."""

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.scanner import Clip
from ramses_ingest.matcher import MatchResult
from ramses_ingest.prober import MediaInfo
from ramses_ingest.publisher import (
    build_plans, copy_frames, execute_plan, resolve_paths,
    _write_ramses_metadata, IngestPlan, IngestResult,
)


def _make_clip(base_name: str, tmpdir: str, frame_count: int = 4) -> Clip:
    frames = list(range(1, frame_count + 1))
    # Create actual files so copy_frames can work
    for f in frames:
        path = os.path.join(tmpdir, f"{base_name}.{f:04d}.exr")
        Path(path).touch()
    return Clip(
        base_name=base_name,
        extension="exr",
        directory=Path(tmpdir),
        is_sequence=True,
        frames=frames,
        first_file=os.path.join(tmpdir, f"{base_name}.0001.exr"),
    )


class TestBuildPlans(unittest.TestCase):
    def test_new_shot_and_sequence(self):
        clip = Clip(
            base_name="SEQ010_SH010",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1, 2, 3],
            first_file="/tmp/SEQ010_SH010.0001.exr",
        )
        match = MatchResult(clip=clip, sequence_id="SEQ010", shot_id="SH010", matched=True)
        info = MediaInfo(width=1920, height=1080, fps=24.0)

        plans = build_plans(
            [match],
            {clip.first_file: info},
            project_id="PROJ",
            existing_sequences=[],
            existing_shots=[],
        )

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertTrue(plan.can_execute)
        self.assertTrue(plan.is_new_sequence)
        self.assertTrue(plan.is_new_shot)

    def test_existing_shot(self):
        clip = Clip(
            base_name="SEQ010_SH010",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1, 2, 3],
            first_file="/tmp/SEQ010_SH010.0001.exr",
        )
        match = MatchResult(clip=clip, sequence_id="SEQ010", shot_id="SH010", matched=True)
        info = MediaInfo(width=1920, height=1080, fps=24.0)

        plans = build_plans(
            [match],
            {clip.first_file: info},
            project_id="PROJ",
            existing_sequences=["SEQ010"],
            existing_shots=["SH010"],
        )

        plan = plans[0]
        self.assertFalse(plan.is_new_sequence)
        self.assertFalse(plan.is_new_shot)

    def test_unmatched_clip(self):
        clip = Clip(
            base_name="garbage",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1],
            first_file="/tmp/garbage.0001.exr",
        )
        match = MatchResult(clip=clip, matched=False)

        plans = build_plans([match], {}, project_id="PROJ")
        self.assertEqual(len(plans), 1)
        self.assertFalse(plans[0].can_execute)

    def test_dedup_within_batch(self):
        """Two clips creating the same sequence should not both report is_new_sequence."""
        clips = []
        matches = []
        for shot in ["SH010", "SH020"]:
            clip = Clip(
                base_name=f"SEQ010_{shot}",
                extension="exr",
                directory=Path("/tmp"),
                is_sequence=True,
                frames=[1],
                first_file=f"/tmp/SEQ010_{shot}.0001.exr",
            )
            matches.append(MatchResult(
                clip=clip, sequence_id="SEQ010", shot_id=shot, matched=True
            ))

        plans = build_plans(matches, {}, project_id="PROJ")
        new_seq_count = sum(1 for p in plans if p.is_new_sequence)
        self.assertEqual(new_seq_count, 1, "Only the first clip should flag the sequence as new")


class TestCopyFrames(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.dst_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.dst_dir, ignore_errors=True)

    def test_copy_sequence(self):
        clip = _make_clip("plate", self.src_dir, frame_count=4)
        copied = copy_frames(clip, self.dst_dir, "PROJ", "SH010", "PLATE")
        self.assertEqual(copied, 4)

        expected_files = [
            f"PROJ_S_SH010_PLATE.{i:04d}.exr" for i in range(1, 5)
        ]
        actual = sorted(os.listdir(self.dst_dir))
        self.assertEqual(actual, expected_files)

    def test_copy_movie(self):
        movie_path = os.path.join(self.src_dir, "shot.mov")
        Path(movie_path).touch()
        clip = Clip(
            base_name="shot",
            extension="mov",
            directory=Path(self.src_dir),
            is_sequence=False,
            frames=[],
            first_file=movie_path,
        )
        copied = copy_frames(clip, self.dst_dir, "PROJ", "SH010", "PLATE")
        self.assertEqual(copied, 1)
        self.assertIn("PROJ_S_SH010_PLATE.mov", os.listdir(self.dst_dir))


class TestResolvePaths(unittest.TestCase):
    def test_resolve_paths_fills_directories(self):
        clip = Clip(
            base_name="SEQ010_SH010",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1, 2, 3],
            first_file="/tmp/SEQ010_SH010.0001.exr",
        )
        match = MatchResult(clip=clip, sequence_id="SEQ010", shot_id="SH010", matched=True)
        info = MediaInfo(width=1920, height=1080, fps=24.0)
        plan = IngestPlan(match=match, media_info=info, sequence_id="SEQ010",
                          shot_id="SH010", project_id="PROJ", version=2)

        resolve_paths([plan], "/projects/PROJ")

        self.assertIn("SH010", plan.target_publish_dir)
        self.assertIn("PLATE", plan.target_publish_dir)
        self.assertIn("v002", plan.target_publish_dir)
        self.assertIn("_preview", plan.target_preview_dir)

    def test_resolve_paths_skips_unexecutable(self):
        clip = Clip(base_name="x", extension="exr", directory=Path("/tmp"),
                    first_file="/tmp/x.0001.exr")
        match = MatchResult(clip=clip, matched=False)
        plan = IngestPlan(match=match, media_info=MediaInfo(), error="unmatched")
        resolve_paths([plan], "/projects/PROJ")
        self.assertEqual(plan.target_publish_dir, "")


class TestWriteMetadata(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_json_with_timecode(self):
        _write_ramses_metadata(
            self.tmpdir, "test_file.exr", version=1, 
            comment="test", timecode="01:00:00:00"
        )
        import json
        meta_path = os.path.join(self.tmpdir, "_ramses_data.json")
        self.assertTrue(os.path.isfile(meta_path))
        with open(meta_path) as f:
            data = json.load(f)
        self.assertIn("test_file.exr", data)
        self.assertEqual(data["test_file.exr"]["timecode"], "01:00:00:00")


class TestExecutePlan(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.dst_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.dst_dir, ignore_errors=True)

    @patch("ramses_ingest.preview.generate_thumbnail")
    @patch("ramses_ingest.preview.generate_proxy")
    def test_execute_with_ocio(self, mock_proxy, mock_thumb):
        clip = _make_clip("plate", self.src_dir, frame_count=1)
        match = MatchResult(clip=clip, sequence_id="SEQ010", shot_id="SH010", matched=True)
        info = MediaInfo(width=1920, height=1080, fps=24.0, start_timecode="10:00:00:00")

        pub_dir = os.path.join(self.dst_dir, "published", "v001")
        prev_dir = os.path.join(self.dst_dir, "preview")

        plan = IngestPlan(
            match=match, media_info=info,
            sequence_id="SEQ010", shot_id="SH010",
            project_id="PROJ", step_id="PLATE",
            target_publish_dir=pub_dir, target_preview_dir=prev_dir,
        )

        mock_thumb.return_value = True
        mock_proxy.return_value = True

        result = execute_plan(
            plan, 
            generate_thumbnail=True, 
            generate_proxy=True,
            ocio_config="config.ocio",
            ocio_in="ACEScg",
            ocio_out="sRGB"
        )
        
        self.assertTrue(result.success)
        # Verify OCIO args were passed to preview generators
        mock_thumb.assert_called_with(
            clip, unittest.mock.ANY, 
            ocio_config="config.ocio", 
            ocio_in="ACEScg", 
            ocio_out="sRGB"
        )

    def test_execute_copies_frames_parallel(self):
        # Use more frames to exercise the ThreadPoolExecutor
        frame_count = 20
        clip = _make_clip("plate", self.src_dir, frame_count=frame_count)
        match = MatchResult(clip=clip, sequence_id="SEQ010", shot_id="SH010", matched=True)
        info = MediaInfo(width=1920, height=1080, fps=24.0)

        pub_dir = os.path.join(self.dst_dir, "published", "v001")
        plan = IngestPlan(
            match=match, media_info=info,
            sequence_id="SEQ010", shot_id="SH010",
            project_id="PROJ", step_id="PLATE",
            target_publish_dir=pub_dir,
        )

        result = execute_plan(plan, generate_thumbnail=False, generate_proxy=False)
        self.assertTrue(result.success)
        self.assertEqual(result.frames_copied, frame_count)
        self.assertEqual(len(os.listdir(pub_dir)), frame_count + 1) # +1 for metadata json

    def test_execute_fails_without_publish_dir(self):
        clip = Clip(base_name="x", extension="exr", directory=Path(self.src_dir),
                    is_sequence=True, frames=[1], first_file=os.path.join(self.src_dir, "x.0001.exr"))
        Path(clip.first_file).touch()
        match = MatchResult(clip=clip, sequence_id="SEQ", shot_id="SH", matched=True)
        plan = IngestPlan(match=match, media_info=MediaInfo(),
                          sequence_id="SEQ", shot_id="SH", project_id="PROJ",
                          target_publish_dir="")
        result = execute_plan(plan, generate_thumbnail=False, generate_proxy=False)
        self.assertFalse(result.success)
        self.assertIn("No target publish directory", result.error)

    def test_execute_skips_unexecutable(self):
        clip = Clip(base_name="x", extension="exr", directory=Path("/tmp"),
                    first_file="/tmp/x.0001.exr")
        match = MatchResult(clip=clip, matched=False)
        plan = IngestPlan(match=match, media_info=MediaInfo(), error="unmatched")
        result = execute_plan(plan, generate_thumbnail=False, generate_proxy=False)
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
