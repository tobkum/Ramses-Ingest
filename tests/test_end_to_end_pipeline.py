# -*- coding: utf-8 -*-
"""Comprehensive end-to-end integration tests for Ramses-Ingest pipeline.

Tests the complete workflow:
1. Scan directory for media
2. Match clips to shots
3. Probe media info
4. Build plans
5. Resolve paths
6. Execute plans (copy + metadata)
7. Verify outputs
8. Test rollback scenarios
9. Test duplicate detection
"""

import os
import sys
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.scanner import scan_directory, Clip
from ramses_ingest.matcher import match_clips, NamingRule
from ramses_ingest.prober import probe_file, MediaInfo
from ramses_ingest.publisher import (
    build_plans,
    resolve_paths,
    execute_plan,
    check_for_duplicates,
)
from ramses_ingest.validator import (
    validate_batch_colorspace,
    check_for_duplicate_version,
)


class TestEndToEndPipeline(unittest.TestCase):
    """Complete pipeline integration tests."""

    def setUp(self):
        """Create temp directories and test media."""
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.project_root = os.path.join(self.temp_dir, "project")
        os.makedirs(self.source_dir)
        os.makedirs(self.project_root)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_sequence(self, name, frame_count=10):
        """Create test image sequence."""
        frames = []
        for i in range(1, frame_count + 1):
            frame_path = os.path.join(self.source_dir, f"{name}.{i:04d}.exr")
            with open(frame_path, "wb") as f:
                f.write(b"EXR_MOCK_DATA" * 100)
            frames.append(frame_path)
        return frames

    def _create_movie(self, name):
        """Create test movie file."""
        movie_path = os.path.join(self.source_dir, f"{name}.mov")
        with open(movie_path, "wb") as f:
            f.write(b"MOV_MOCK_DATA" * 1000)
        return movie_path

    def _mock_ffprobe_response(self, width=1920, height=1080, fps=24.0):
        """Generate mock ffprobe JSON response."""
        return json.dumps({
            "streams": [{
                "width": width,
                "height": height,
                "r_frame_rate": f"{int(fps)}/1",
                "codec_name": "prores",
                "pix_fmt": "yuv422p10le",
                "color_primaries": "bt709",
                "color_transfer": "bt709",
                "color_space": "bt709",
                "duration": "10.0",
                "nb_frames": str(int(10 * fps)),
                "tags": {"timecode": "01:00:00:00"}
            }],
            "format": {"tags": {}}
        })

    def test_full_pipeline_happy_path(self):
        """Test complete pipeline from scan to publish."""
        # Step 1: Create source media
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=5)
        self._create_sequence("SEQ010_SH020_PLATE", frame_count=5)

        # Step 2: Scan directory
        clips = scan_directory(self.source_dir)
        self.assertEqual(len(clips), 2)

        # Step 3: Match clips to shots
        rules = [
            NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)"),
        ]
        matches = match_clips(clips, rules)
        self.assertEqual(len(matches), 2)
        self.assertTrue(all(m.matched for m in matches))

        # Step 4: Probe media info (mock ffprobe)
        media_infos = {}
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=self._mock_ffprobe_response()
            )
            for match in matches:
                media_infos[match.clip.first_file] = probe_file(match.clip.first_file)

        # Step 5: Build plans
        plans = build_plans(
            matches,
            media_infos,
            project_id="TEST",
            existing_sequences=[],
            existing_shots=[],
        )
        self.assertEqual(len(plans), 2)

        # Step 6: Resolve paths
        resolve_paths(plans, self.project_root)
        for plan in plans:
            self.assertNotEqual(plan.target_publish_dir, "")
            # API format: [VERSION]_[STATE] (e.g., 001_WIP)
            self.assertIn("001_WIP", plan.target_publish_dir)

        # Step 7: Execute plans
        results = []
        for plan in plans:
            result = execute_plan(
                plan,
                generate_thumbnail=False,
                generate_proxy=False,
                skip_ramses_registration=True,
            )
            results.append(result)

        # Step 8: Verify all succeeded
        self.assertTrue(all(r.success for r in results))

        # Step 9: Verify files were created
        for result in results:
            self.assertTrue(os.path.isdir(result.published_path))
            # Should have metadata
            meta_path = os.path.join(result.published_path, "_ramses_data.json")
            self.assertTrue(os.path.isfile(meta_path))
            # Should have completion marker
            marker_path = os.path.join(result.published_path, ".ramses_complete")
            self.assertTrue(os.path.isfile(marker_path))

    def test_pipeline_with_unmatched_clips(self):
        """Unmatched clips should be skipped."""
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=3)
        self._create_sequence("garbage_file", frame_count=3)

        clips = scan_directory(self.source_dir)
        self.assertEqual(len(clips), 2)

        rules = [
            NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)"),
        ]
        matches = match_clips(clips, rules)

        # One matched, one unmatched
        matched_count = sum(1 for m in matches if m.matched)
        self.assertEqual(matched_count, 1)

        # Build plans
        plans = build_plans(matches, {}, project_id="TEST")

        # Only one can execute
        executable = [p for p in plans if p.can_execute]
        self.assertEqual(len(executable), 1)

    def test_pipeline_with_colorspace_validation(self):
        """Mixed colorspaces should be flagged."""
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=3)
        self._create_sequence("SEQ010_SH020_PLATE", frame_count=3)

        clips = scan_directory(self.source_dir)
        rules = [
            NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)"),
        ]
        matches = match_clips(clips, rules)

        # Mock different colorspaces
        media_infos = {}
        with patch("subprocess.run") as mock_run:
            # First clip: bt709
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=self._mock_ffprobe_response()
            )
            media_infos[matches[0].clip.first_file] = probe_file(matches[0].clip.first_file)

            # Second clip: bt2020 (different!)
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({
                    "streams": [{
                        "width": 1920,
                        "height": 1080,
                        "color_primaries": "bt2020",
                        "color_transfer": "smpte2084",
                        "color_space": "bt2020",
                    }],
                    "format": {"tags": {}}
                })
            )
            media_infos[matches[1].clip.first_file] = probe_file(matches[1].clip.first_file)

        plans = build_plans(matches, media_infos, project_id="TEST")

        # Validate colorspace
        issues = validate_batch_colorspace(plans)

        # Should have critical issue for mismatched primaries
        self.assertGreater(len(issues), 0)
        self.assertTrue(any(i.severity == "critical" for i in issues.values()))

    def test_pipeline_duplicate_detection(self):
        """Re-ingesting same clip should be detected as duplicate."""
        # First ingest
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=3)

        clips = scan_directory(self.source_dir)
        rules = [NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)")]
        matches = match_clips(clips, rules)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=self._mock_ffprobe_response()
            )
            media_infos = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches}

        plans = build_plans(matches, media_infos, project_id="TEST")
        resolve_paths(plans, self.project_root)

        # Execute first ingest
        for plan in plans:
            execute_plan(plan, generate_thumbnail=False, skip_ramses_registration=True)

        # Second ingest (same clip)
        clips2 = scan_directory(self.source_dir)
        matches2 = match_clips(clips2, rules)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=self._mock_ffprobe_response())
            media_infos2 = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches2}

        plans2 = build_plans(matches2, media_infos2, project_id="TEST")
        resolve_paths(plans2, self.project_root)

        # Check for duplicates
        check_for_duplicates(plans2)

        # Should be detected as duplicate
        self.assertTrue(plans2[0].is_duplicate)
        self.assertEqual(plans2[0].duplicate_version, 1)
        self.assertFalse(plans2[0].can_execute)

    def test_pipeline_rollback_on_failure(self):
        """Failed ingest should rollback cleanly."""
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=3)

        clips = scan_directory(self.source_dir)
        rules = [NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)")]
        matches = match_clips(clips, rules)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=self._mock_ffprobe_response())
            media_infos = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches}

        plans = build_plans(matches, media_infos, project_id="TEST")
        resolve_paths(plans, self.project_root)

        # Cause failure during copy
        with patch('shutil.copy2', side_effect=OSError("Simulated failure")):
            result = execute_plan(
                plans[0],
                generate_thumbnail=False,
                skip_ramses_registration=True,
            )

        # Should fail
        self.assertFalse(result.success)
        self.assertIn("Rolled back", result.error)

        # Publish directory should be cleaned up
        self.assertFalse(os.path.exists(plans[0].target_publish_dir))

    def test_pipeline_multiple_resources(self):
        """HERO and auxiliary resources should be handled correctly."""
        # Create HERO and DEPTH clips
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=3)
        self._create_sequence("SEQ010_SH010_PLATE_DEPTH", frame_count=3)

        clips = scan_directory(self.source_dir)
        rules = [
            NamingRule(
                # Use [^_]+ for step to prevent matching underscores (allows resource capture)
                pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>[^_]+)(?:_(?P<resource>\w+))?"
            ),
        ]
        matches = match_clips(clips, rules)

        self.assertEqual(len(matches), 2)
        # One should have no resource (HERO), one should have DEPTH
        resources = [m.resource for m in matches if m.matched]
        self.assertIn("", resources)  # HERO
        self.assertIn("DEPTH", resources)

    def test_pipeline_version_numbering(self):
        """Multiple ingests should increment version numbers."""
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=3)

        clips = scan_directory(self.source_dir)
        rules = [NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)")]
        matches = match_clips(clips, rules)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=self._mock_ffprobe_response())
            media_infos = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches}

        # First ingest
        plans1 = build_plans(matches, media_infos, project_id="TEST")
        resolve_paths(plans1, self.project_root)
        self.assertEqual(plans1[0].version, 1)

        result1 = execute_plan(plans1[0], generate_thumbnail=False, skip_ramses_registration=True)
        self.assertTrue(result1.success)

        # Second ingest (different content to avoid duplicate detection)
        # Modify source files
        for clip in clips:
            for frame in clip.frames:
                frame_path = os.path.join(str(clip.directory), f"{clip.base_name}.{frame:04d}.{clip.extension}")
                with open(frame_path, "wb") as f:
                    f.write(b"MODIFIED_CONTENT" * 100)

        clips2 = scan_directory(self.source_dir)
        matches2 = match_clips(clips2, rules)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=self._mock_ffprobe_response())
            media_infos2 = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches2}

        plans2 = build_plans(matches2, media_infos2, project_id="TEST")
        resolve_paths(plans2, self.project_root)

        # Should be version 2
        self.assertEqual(plans2[0].version, 2)

    def test_pipeline_with_movie_files(self):
        """Movies should be handled differently from sequences."""
        self._create_movie("SEQ010_SH010_PLATE")

        clips = scan_directory(self.source_dir)
        self.assertEqual(len(clips), 1)
        self.assertFalse(clips[0].is_sequence)

        rules = [NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)")]
        matches = match_clips(clips, rules)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=self._mock_ffprobe_response())
            media_infos = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches}

        plans = build_plans(matches, media_infos, project_id="TEST")
        resolve_paths(plans, self.project_root)

        result = execute_plan(plans[0], generate_thumbnail=False, skip_ramses_registration=True)
        self.assertTrue(result.success)

        # Should have single movie file
        files = [f for f in os.listdir(result.published_path) if f.endswith(".mov")]
        self.assertEqual(len(files), 1)

    def test_pipeline_path_collision_detection(self):
        """Multiple clips resolving to same path should be flagged."""
        from ramses_ingest.publisher import check_for_path_collisions

        # Create two clips that would resolve to same shot
        self._create_sequence("SEQ010_SH010_v01", frame_count=3)
        self._create_sequence("SEQ010_SH010_v02", frame_count=3)

        clips = scan_directory(self.source_dir)
        # Match pattern that ignores version in clip name
        rules = [NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)")]
        matches = match_clips(clips, rules)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=self._mock_ffprobe_response())
            media_infos = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches}

        plans = build_plans(matches, media_infos, project_id="TEST")
        resolve_paths(plans, self.project_root)

        # Check for collisions
        check_for_path_collisions(plans)

        # Both plans should have collision error
        collision_count = sum(1 for p in plans if "COLLISION" in p.error)
        self.assertEqual(collision_count, 2)

    def test_pipeline_dry_run_mode(self):
        """Dry run should not create any files."""
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=3)

        clips = scan_directory(self.source_dir)
        rules = [NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)")]
        matches = match_clips(clips, rules)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=self._mock_ffprobe_response())
            media_infos = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches}

        plans = build_plans(matches, media_infos, project_id="TEST")
        resolve_paths(plans, self.project_root)

        # Execute in dry run mode
        result = execute_plan(
            plans[0],
            generate_thumbnail=False,
            skip_ramses_registration=True,
            dry_run=True,
        )

        # Should succeed but not create files
        self.assertTrue(result.success)
        self.assertFalse(os.path.exists(result.published_path))

    def test_pipeline_with_gaps_in_sequence(self):
        """Sequences with missing frames should be detected."""
        # Create sequence with gap
        for i in [1, 2, 3, 5, 6, 7]:  # Missing frame 4
            frame_path = os.path.join(self.source_dir, f"SEQ010_SH010_PLATE.{i:04d}.exr")
            with open(frame_path, "wb") as f:
                f.write(b"TEST")

        clips = scan_directory(self.source_dir)
        self.assertEqual(len(clips), 1)

        clip = clips[0]
        self.assertEqual(clip.frame_count, 6)
        self.assertEqual(len(clip.missing_frames), 1)
        self.assertIn(4, clip.missing_frames)

    def test_pipeline_fast_verify_mode(self):
        """Fast verify should complete successfully."""
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=20)

        clips = scan_directory(self.source_dir)
        rules = [NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)")]
        matches = match_clips(clips, rules)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=self._mock_ffprobe_response())
            media_infos = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches}

        plans = build_plans(matches, media_infos, project_id="TEST")
        resolve_paths(plans, self.project_root)

        # Execute with fast verify
        result = execute_plan(
            plans[0],
            generate_thumbnail=False,
            skip_ramses_registration=True,
            fast_verify=True,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.frames_copied, 20)

    def test_pipeline_metadata_preservation(self):
        """Timecode and other metadata should be preserved."""
        self._create_sequence("SEQ010_SH010_PLATE", frame_count=3)

        clips = scan_directory(self.source_dir)
        rules = [NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)_(?P<step>\w+)")]
        matches = match_clips(clips, rules)

        # Mock ffprobe with specific timecode
        custom_timecode = "02:30:15:10"
        with patch("subprocess.run") as mock_run:
            response = json.dumps({
                "streams": [{
                    "width": 1920,
                    "height": 1080,
                    "tags": {"timecode": custom_timecode}
                }],
                "format": {"tags": {}}
            })
            mock_run.return_value = MagicMock(returncode=0, stdout=response)
            media_infos = {m.clip.first_file: probe_file(m.clip.first_file) for m in matches}

        plans = build_plans(matches, media_infos, project_id="TEST")
        resolve_paths(plans, self.project_root)

        result = execute_plan(plans[0], generate_thumbnail=False, skip_ramses_registration=True)

        # Read metadata
        meta_path = os.path.join(result.published_path, "_ramses_data.json")
        with open(meta_path, "r") as f:
            data = json.load(f)

        # Find first file entry
        first_entry = list(data.values())[0]
        self.assertEqual(first_entry["timecode"], custom_timecode)


class TestPipelineErrorHandling(unittest.TestCase):
    """Test pipeline error handling and edge cases."""

    def setUp(self):
        """Create temp directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(self.source_dir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_source_directory(self):
        """Empty directory should return no clips."""
        clips = scan_directory(self.source_dir)
        self.assertEqual(len(clips), 0)

    def test_invalid_naming_pattern(self):
        """Clips not matching any rule should be unmatched."""
        # Create file with non-standard naming
        path = os.path.join(self.source_dir, "random_file_123.exr")
        Path(path).touch()

        clips = scan_directory(self.source_dir)
        rules = [NamingRule(pattern=r"(?P<sequence>SEQ\d+)_(?P<shot>SH\d+)")]
        matches = match_clips(clips, rules)

        self.assertFalse(matches[0].matched)

    def test_ffprobe_failure(self):
        """FFprobe failure should return invalid MediaInfo."""
        path = os.path.join(self.source_dir, "test.mov")
        Path(path).touch()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            info = probe_file(path)

        self.assertFalse(info.is_valid)

    def test_path_traversal_attack(self):
        """Path traversal in IDs should be rejected."""
        from ramses_ingest.publisher import resolve_paths, IngestPlan
        from ramses_ingest.matcher import MatchResult

        clip = Clip(base_name="test", extension="exr", directory=Path("/tmp"))
        match = MatchResult(clip=clip, matched=True, shot_id="../../etc/passwd", sequence_id="SEQ")
        plan = IngestPlan(
            match=match,
            media_info=MediaInfo(),
            project_id="PROJ",
            shot_id="../../etc/passwd",
        )

        resolve_paths([plan], self.temp_dir)

        # Should have error
        self.assertNotEqual(plan.error, "")
        self.assertIn("path separators", plan.error.lower())


if __name__ == "__main__":
    unittest.main()
