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
    _write_ramses_metadata, _calculate_md5, IngestPlan, IngestResult,
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
        copied, checksum, bytes_moved, first_file = copy_frames(clip, self.dst_dir, "PROJ", "SH010", "PLATE")
        self.assertEqual(copied, 4)
        self.assertGreater(len(checksum), 0)

        expected_files = [
            f"PROJ_S_SH010_PLATE.{i:04d}.exr" for i in range(1, 5)
        ]
        actual = sorted([f for f in os.listdir(self.dst_dir) if not f.startswith(".")])
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
        copied, checksum, bytes_moved, first_file = copy_frames(clip, self.dst_dir, "PROJ", "SH010", "PLATE")
        self.assertEqual(copied, 1)
        self.assertIn("PROJ_S_SH010_PLATE.mov", os.listdir(self.dst_dir))

    def test_fast_verify_catches_size_mismatch(self):
        """Test that Fast Verify still catches size mismatches on un-hashed frames."""
        clip = _make_clip("fast", self.src_dir, frame_count=10)
        
        # We need to mock shutil.copy2 to simulate a partial/corrupt copy
        # but ONLY for one specific frame (e.g. frame 5 which is skipped in MD5)
        import shutil
        original_copy2 = shutil.copy2
        
        def mock_copy_corrupt(src, dst):
            original_copy2(src, dst)
            if "0005" in dst:
                # Corrupt the destination file size
                with open(dst, "ab") as f:
                    f.write(b"corruption")

        with patch("shutil.copy2", side_effect=mock_copy_corrupt):
            with self.assertRaises(OSError) as cm:
                copy_frames(clip, self.dst_dir, "PROJ", "SH010", "PLATE", fast_verify=True)
            self.assertIn("Size mismatch", str(cm.exception))


class TestResolvePaths(unittest.TestCase):
    def test_resolve_paths_fills_directories(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)

        # Create a 001_WIP to force version 002
        # Standard Ramses path: 05-SHOTS/PROJ_S_SH010/PROJ_S_SH010_PLATE/...
        # API format: [VERSION]_[STATE] (e.g., 001_WIP)
        v1_path = os.path.join(root, "05-SHOTS", "PROJ_S_SH010", "PROJ_S_SH010_PLATE", "_published", "001_WIP")
        os.makedirs(v1_path, exist_ok=True)
        Path(os.path.join(v1_path, ".ramses_complete")).touch()

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
                          shot_id="SH010", project_id="PROJ")

        resolve_paths([plan], root)

        self.assertIn("PROJ_S_SH010", plan.target_publish_dir)
        self.assertIn("PROJ_S_SH010_PLATE", plan.target_publish_dir)
        self.assertIn("002_WIP", plan.target_publish_dir)
        self.assertIn("_preview", plan.target_preview_dir)
        self.assertIn("05-SHOTS", plan.target_publish_dir)
        # Verify sequence folder is NOT there
        self.assertNotIn("SEQ010", plan.target_publish_dir)

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

    def test_execute_with_ocio(self):
        """Verify that OCIO parameters are stored in thumbnail job for batch processing."""
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

        result = execute_plan(
            plan,
            generate_thumbnail=True,
            generate_proxy=True,
            ocio_config="config.ocio",
            ocio_in="ACEScg",
            ocio_out="sRGB"
        )

        self.assertTrue(result.success)

        # Verify thumbnail job was stored for batch processing with OCIO params
        self.assertIsNotNone(result._thumbnail_job)
        self.assertEqual(result._thumbnail_job['clip'], clip)
        self.assertEqual(result._thumbnail_job['ocio_config'], "config.ocio")
        self.assertEqual(result._thumbnail_job['ocio_in'], "ACEScg")
        self.assertFalse(result._thumbnail_job['is_resource'])  # Hero asset, not auxiliary

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
        # +1 for metadata json, +1 for .ramses_complete marker
        self.assertEqual(len(os.listdir(pub_dir)), frame_count + 2) 

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


class TestPublisherConcurrency(unittest.TestCase):
    """Test concurrency and thread-safety features."""

    def setUp(self):
        """Create temp directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.publish_root = os.path.join(self.temp_dir, "_published")

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sequential_version_numbering(self):
        """_get_next_version should increment when version directories exist."""
        from ramses_ingest.publisher import _get_next_version

        # No directory yet → version 1
        v1 = _get_next_version(self.publish_root)
        self.assertEqual(v1, 1)

        # Create version 1 with completion marker
        os.makedirs(self.publish_root, exist_ok=True)
        v1_dir = os.path.join(self.publish_root, "001")
        os.makedirs(v1_dir, exist_ok=True)
        Path(os.path.join(v1_dir, ".ramses_complete")).touch()

        # Now should return version 2
        v2 = _get_next_version(self.publish_root)
        self.assertEqual(v2, 2)

        # Create version 2
        v2_dir = os.path.join(self.publish_root, "002")
        os.makedirs(v2_dir, exist_ok=True)
        Path(os.path.join(v2_dir, ".ramses_complete")).touch()

        # Now should return version 3
        v3 = _get_next_version(self.publish_root)
        self.assertEqual(v3, 3)

    def test_concurrent_metadata_writes(self):
        """Multiple threads writing to same _ramses_data.json should not corrupt file."""
        import threading
        import json

        folder = os.path.join(self.temp_dir, "version")
        os.makedirs(folder)

        def write_metadata(filename, version):
            for _ in range(5):  # Multiple writes per thread
                _write_ramses_metadata(folder, filename, version)

        # Launch multiple threads writing different entries
        threads = [
            threading.Thread(target=write_metadata, args=(f"file_{i}.exr", i))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify metadata file is valid JSON and has all entries
        meta_path = os.path.join(folder, "_ramses_data.json")
        self.assertTrue(os.path.isfile(meta_path))

        with open(meta_path, "r") as f:
            data = json.load(f)

        # Should have all 10 entries
        self.assertEqual(len(data), 10)
        for i in range(10):
            self.assertIn(f"file_{i}.exr", data)

    def test_parallel_frame_copy_with_failure(self):
        """ThreadPoolExecutor with some frames failing should propagate error."""
        src_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(src_dir)

        # Create some frames but not all
        frames = list(range(1, 11))
        for f in frames[:5]:  # Only create first 5 frames
            path = os.path.join(src_dir, f"test.{f:04d}.exr")
            Path(path).touch()

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(src_dir),
            is_sequence=True,
            frames=frames,  # Claims to have 10 frames
            first_file=os.path.join(src_dir, "test.0001.exr"),
        )

        dest_dir = os.path.join(self.temp_dir, "dest")

        # Should raise FileNotFoundError for missing frames
        with self.assertRaises(FileNotFoundError):
            copy_frames(clip, dest_dir, "PROJ", "SH010", "PLATE")

    def test_atomic_metadata_write_interruption(self):
        """Verify temp file cleanup on failure during atomic write."""
        folder = os.path.join(self.temp_dir, "version")
        os.makedirs(folder)

        # Cause rename to fail
        with patch('os.replace', side_effect=OSError("Simulated rename failure")):
            with self.assertRaises(OSError):
                _write_ramses_metadata(folder, "test.exr", 1)

        # Verify no temp files left behind
        temp_files = [f for f in os.listdir(folder) if f.startswith(".ramses_data_")]
        self.assertEqual(len(temp_files), 0)

    def test_version_cache_optimization(self):
        """resolve_paths should cache version lookups within same batch."""
        from ramses_ingest.publisher import resolve_paths

        # Create multiple plans for same shot
        plans = []
        for i in range(5):
            clip = Clip(
                base_name=f"test_{i}",
                extension="exr",
                directory=Path("/tmp"),
                is_sequence=True,
                frames=[1],
                first_file=f"/tmp/test_{i}.0001.exr",
            )
            match = MatchResult(clip=clip, matched=True, shot_id="SH010", sequence_id="SEQ010")
            plan = IngestPlan(
                match=match,
                media_info=MediaInfo(),
                project_id="PROJ",
                shot_id="SH010",
                step_id="PLATE",
            )
            plans.append(plan)

        # Mock _get_next_version to track calls
        call_count = []
        original_get_version = __import__('ramses_ingest.publisher', fromlist=['_get_next_version'])._get_next_version

        def mock_get_version(path, **kwargs):
            call_count.append(path)
            return original_get_version(path, **kwargs)

        with patch('ramses_ingest.publisher._get_next_version', side_effect=mock_get_version):
            resolve_paths(plans, self.temp_dir)

        # Should only call _get_next_version once for the same publish_root
        # (5 plans for same shot/step = same publish_root)
        self.assertEqual(len(call_count), 1)

        # All plans should have same version
        versions = [p.version for p in plans]
        self.assertEqual(len(set(versions)), 1)

    def test_copy_frames_max_workers_parameter(self):
        """Test that max_workers parameter limits concurrency."""
        src_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(src_dir)

        frames = list(range(1, 21))  # 20 frames
        for f in frames:
            path = os.path.join(src_dir, f"test.{f:04d}.exr")
            Path(path).touch()

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(src_dir),
            is_sequence=True,
            frames=frames,
            first_file=os.path.join(src_dir, "test.0001.exr"),
        )

        dest_dir = os.path.join(self.temp_dir, "dest")

        # Copy with limited workers
        copied, checksum, bytes_copied, first_file = copy_frames(
            clip, dest_dir, "PROJ", "SH010", "PLATE", max_workers=2
        )

        self.assertEqual(copied, 20)
        self.assertEqual(len(os.listdir(dest_dir)), 20)

    def test_rollback_on_copy_failure(self):
        """execute_plan should rollback on copy failure."""
        src_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(src_dir)

        # Create clip with one frame
        frame_path = os.path.join(src_dir, "test.0001.exr")
        Path(frame_path).touch()

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(src_dir),
            is_sequence=True,
            frames=[1],
            first_file=frame_path,
        )

        match = MatchResult(clip=clip, matched=True, shot_id="SH010", sequence_id="SEQ010")
        pub_dir = os.path.join(self.temp_dir, "published", "v001")
        plan = IngestPlan(
            match=match,
            media_info=MediaInfo(),
            project_id="PROJ",
            shot_id="SH010",
            step_id="PLATE",
            target_publish_dir=pub_dir,
        )

        # Cause copy to fail
        with patch('shutil.copy2', side_effect=OSError("Simulated copy failure")):
            result = execute_plan(plan, generate_thumbnail=False, generate_proxy=False)

        # Should fail
        self.assertFalse(result.success)
        self.assertIn("Rolled back", result.error)

        # Publish directory should be cleaned up
        self.assertFalse(os.path.exists(pub_dir))

    def test_rollback_failure_logged(self):
        """Rollback failure should be logged in error message."""
        src_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(src_dir)

        frame_path = os.path.join(src_dir, "test.0001.exr")
        Path(frame_path).touch()

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(src_dir),
            is_sequence=True,
            frames=[1],
            first_file=frame_path,
        )

        match = MatchResult(clip=clip, matched=True, shot_id="SH010", sequence_id="SEQ010")
        pub_dir = os.path.join(self.temp_dir, "published", "v001")
        plan = IngestPlan(
            match=match,
            media_info=MediaInfo(),
            project_id="PROJ",
            shot_id="SH010",
            step_id="PLATE",
            target_publish_dir=pub_dir,
        )

        # Cause both copy and rollback to fail
        with patch('shutil.copy2', side_effect=OSError("Copy failed")):
            with patch('shutil.rmtree', side_effect=OSError("Rollback failed")):
                result = execute_plan(plan, generate_thumbnail=False, generate_proxy=False)

        self.assertFalse(result.success)
        self.assertIn("rollback failed", result.error.lower())

    def test_dry_run_parallel_verification(self):
        """Dry run should calculate checksums in parallel without copying."""
        src_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(src_dir)

        frames = list(range(1, 11))
        for f in frames:
            path = os.path.join(src_dir, f"test.{f:04d}.exr")
            with open(path, "wb") as fp:
                fp.write(b"test content" * 100)

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(src_dir),
            is_sequence=True,
            frames=frames,
            first_file=os.path.join(src_dir, "test.0001.exr"),
        )

        dest_dir = os.path.join(self.temp_dir, "dest")

        # Dry run
        copied, checksum, bytes_copied, first_file = copy_frames(
            clip, dest_dir, "PROJ", "SH010", "PLATE", dry_run=True
        )

        self.assertEqual(copied, 10)
        self.assertNotEqual(checksum, "")
        self.assertGreater(bytes_copied, 0)
        # Destination should not be created
        self.assertFalse(os.path.exists(dest_dir))

    def test_fast_verify_samples_specific_frames(self):
        """Fast verify should only MD5 first, middle, and last frames."""
        src_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(src_dir)

        frames = list(range(1, 11))  # 10 frames
        for f in frames:
            path = os.path.join(src_dir, f"test.{f:04d}.exr")
            with open(path, "wb") as fp:
                fp.write(b"X" * 1000)

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(src_dir),
            is_sequence=True,
            frames=frames,
            first_file=os.path.join(src_dir, "test.0001.exr"),
        )

        dest_dir = os.path.join(self.temp_dir, "dest")

        # Track MD5 calls
        original_md5 = _calculate_md5
        md5_calls = []

        def track_md5(path):
            md5_calls.append(path)
            return original_md5(path)

        with patch('ramses_ingest.publisher._calculate_md5', side_effect=track_md5):
            copy_frames(clip, dest_dir, "PROJ", "SH010", "PLATE", fast_verify=True)

        # Should call MD5 for: first (0001), middle (0005), last (0010)
        # Each frame calls MD5 twice (source + dest), but we're counting source calls
        source_md5_calls = [c for c in md5_calls if src_dir in c]
        # First, middle, last = 3 frames * 2 (src+dst) = 6 calls
        self.assertLessEqual(len(source_md5_calls), 6)


if __name__ == "__main__":
    unittest.main()
