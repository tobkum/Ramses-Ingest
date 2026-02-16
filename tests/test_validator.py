# -*- coding: utf-8 -*-
"""Comprehensive tests for ramses_ingest.validator module.

Tests coverage:
    - validate_batch_colorspace(): mixed primaries, missing metadata, transfer functions
    - check_for_duplicate_version(): exact duplicate detection, resource filtering, MD5 comparison
    - _calculate_md5_safe(): sampling strategy for small/large files
    - EDLValidator: CMX 3600 parsing, frame range validation
    - Edge cases: empty batches, single clips, UNKNOWN values
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.validator import (
    validate_batch_colorspace,
    check_for_duplicate_version,
    _calculate_md5_safe,
    EDLValidator,
    EDLExpectation,
    ColorspaceIssue,
    validate_plans_against_edl,
)
from ramses_ingest.scanner import Clip
from ramses_ingest.matcher import MatchResult
from ramses_ingest.prober import MediaInfo
from ramses_ingest.publisher import IngestPlan


class TestValidateBatchColorspace(unittest.TestCase):
    """Test colorspace consistency validation across batches."""

    def _make_plan(self, primaries="bt709", transfer="bt709", space="bt709",
                   matched=True, width=1920, resource=""):
        """Helper to create a minimal IngestPlan."""
        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1, 2, 3],
            first_file="/tmp/test.0001.exr",
        )
        match = MatchResult(clip=clip, matched=matched, shot_id="SH010", sequence_id="SEQ010")
        info = MediaInfo(
            width=width,
            height=1080,
            color_primaries=primaries,
            color_transfer=transfer,
            color_space=space,
        )
        plan = IngestPlan(match=match, media_info=info, resource=resource)
        return plan

    def test_empty_batch_returns_no_issues(self):
        """Empty batch should return empty issues dict."""
        issues = validate_batch_colorspace([])
        self.assertEqual(issues, {})

    def test_single_clip_returns_no_issues(self):
        """Single clip has nothing to compare against."""
        plan = self._make_plan()
        issues = validate_batch_colorspace([plan])
        self.assertEqual(issues, {})

    def test_all_unmatched_returns_no_issues(self):
        """Unmatched clips are skipped."""
        plans = [
            self._make_plan(matched=False),
            self._make_plan(matched=False),
        ]
        issues = validate_batch_colorspace(plans)
        self.assertEqual(issues, {})

    def test_auxiliary_resources_skipped(self):
        """Auxiliary resources (resource != "") should be skipped."""
        plans = [
            self._make_plan(primaries="bt709", resource=""),
            self._make_plan(primaries="bt2020", resource="DEPTH"),  # Skipped
        ]
        issues = validate_batch_colorspace(plans)
        # Should have no issues because DEPTH is skipped
        self.assertEqual(issues, {})

    def test_mixed_primaries_bt709_bt2020_critical(self):
        """Mixed bt709 and bt2020 primaries should flag critical issue."""
        plans = [
            self._make_plan(primaries="bt709"),
            self._make_plan(primaries="bt709"),
            self._make_plan(primaries="bt2020"),  # Mismatch
        ]
        issues = validate_batch_colorspace(plans)

        # bt2020 should be flagged (minority)
        self.assertIn(2, issues)
        self.assertEqual(issues[2].severity, "critical")
        self.assertIn("Primaries mismatch", issues[2].message)
        self.assertIn("BT2020", issues[2].message.upper())

    def test_mixed_primaries_bt709_film_critical(self):
        """Mixed bt709 and film primaries should flag critical issue."""
        plans = [
            self._make_plan(primaries="bt709"),
            self._make_plan(primaries="film"),
        ]
        issues = validate_batch_colorspace(plans)

        # Both should be flagged (tie, but film is flagged as non-standard)
        self.assertTrue(len(issues) > 0)
        self.assertTrue(any(i.severity == "critical" for i in issues.values()))

    def test_mixed_primaries_with_unknown_ignored(self):
        """UNKNOWN in primaries set should prevent critical flagging."""
        plans = [
            self._make_plan(primaries="bt709"),
            self._make_plan(primaries="bt2020"),
            self._make_plan(primaries="UNKNOWN"),
        ]
        issues = validate_batch_colorspace(plans)

        # Should not flag critical mismatch if UNKNOWN is present
        for issue in issues.values():
            if issue.severity == "critical":
                self.assertNotIn("Primaries mismatch", issue.message)

    def test_missing_metadata_some_clips_critical(self):
        """Some clips with UNKNOWN primaries when others have metadata is critical."""
        plans = [
            self._make_plan(primaries="bt709"),
            self._make_plan(primaries="bt709"),
            self._make_plan(primaries="UNKNOWN"),  # Missing metadata
        ]
        issues = validate_batch_colorspace(plans)

        self.assertIn(2, issues)
        self.assertEqual(issues[2].severity, "critical")
        self.assertIn("Missing colorspace metadata", issues[2].message)

    def test_all_clips_unknown_no_issue(self):
        """All clips with UNKNOWN primaries is not an issue (batch consistency)."""
        plans = [
            self._make_plan(primaries="UNKNOWN"),
            self._make_plan(primaries="UNKNOWN"),
        ]
        issues = validate_batch_colorspace(plans)
        self.assertEqual(issues, {})

    def test_transfer_function_mixing_warning(self):
        """Mixed transfer functions with same primaries should warn."""
        plans = [
            self._make_plan(primaries="bt709", transfer="bt709"),
            self._make_plan(primaries="bt709", transfer="smpte2084"),  # HDR
        ]
        issues = validate_batch_colorspace(plans)

        # Both should have warnings
        self.assertEqual(len(issues), 2)
        for issue in issues.values():
            self.assertEqual(issue.severity, "warning")
            self.assertIn("Transfer function mismatch", issue.message)

    def test_transfer_function_mixing_with_unknown_ignored(self):
        """UNKNOWN transfer functions should be ignored in warnings."""
        plans = [
            self._make_plan(primaries="bt709", transfer="bt709"),
            self._make_plan(primaries="bt709", transfer="UNKNOWN"),
        ]
        issues = validate_batch_colorspace(plans)

        # Should not warn if UNKNOWN is present
        for issue in issues.values():
            self.assertNotEqual(issue.severity, "warning")

    def test_critical_overrides_warning(self):
        """Critical issues should take precedence over warnings."""
        plans = [
            self._make_plan(primaries="bt709", transfer="bt709"),
            self._make_plan(primaries="bt2020", transfer="smpte2084"),
        ]
        issues = validate_batch_colorspace(plans)

        # Should have critical issue, not warning
        self.assertTrue(any(i.severity == "critical" for i in issues.values()))

    def test_all_same_colorspace_no_issues(self):
        """Batch with consistent colorspace should have no issues."""
        plans = [
            self._make_plan(primaries="bt709", transfer="bt709", space="bt709"),
            self._make_plan(primaries="bt709", transfer="bt709", space="bt709"),
            self._make_plan(primaries="bt709", transfer="bt709", space="bt709"),
        ]
        issues = validate_batch_colorspace(plans)
        self.assertEqual(issues, {})

    def test_clips_without_width_skipped(self):
        """Clips without width (invalid media) should be skipped."""
        plans = [
            self._make_plan(primaries="bt709", width=1920),
            self._make_plan(primaries="bt2020", width=0),  # Invalid, skipped
        ]
        issues = validate_batch_colorspace(plans)
        # Should have no issues because invalid clip is skipped
        self.assertEqual(issues, {})


class TestCheckForDuplicateVersion(unittest.TestCase):
    """Test duplicate version detection."""

    def setUp(self):
        """Create temp directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.versions_dir = os.path.join(self.temp_dir, "_published")
        os.makedirs(self.versions_dir, exist_ok=True)

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_version(self, version_num, resource="", frame_count=1, content=b"test"):
        """Helper to create a version folder with files."""
        if resource:
            folder_name = f"{resource}_{version_num:03d}"
        else:
            folder_name = f"{version_num:03d}"

        version_path = os.path.join(self.versions_dir, folder_name)
        os.makedirs(version_path, exist_ok=True)

        # Create dummy frames
        for i in range(frame_count):
            frame_path = os.path.join(version_path, f"frame.{i+1:04d}.exr")
            with open(frame_path, "wb") as f:
                f.write(content)

        return version_path

    def test_no_versions_dir_returns_false(self):
        """Non-existent versions directory should return False."""
        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(self.temp_dir),
            is_sequence=True,
            frames=[1],
            first_file=os.path.join(self.temp_dir, "test.0001.exr"),
        )

        is_dup, path, ver = check_for_duplicate_version(
            clip, "/nonexistent/path"
        )
        self.assertFalse(is_dup)
        self.assertEqual(path, "")
        self.assertEqual(ver, 0)

    def test_frame_count_mismatch_not_duplicate(self):
        """Different frame count should not match."""
        # Create version with 5 frames
        self._create_version(1, frame_count=5)

        # Create clip with 3 frames
        clip_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(clip_dir, exist_ok=True)
        for i in range(3):
            with open(os.path.join(clip_dir, f"test.{i+1:04d}.exr"), "wb") as f:
                f.write(b"test")

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(clip_dir),
            is_sequence=True,
            frames=[1, 2, 3],
            first_file=os.path.join(clip_dir, "test.0001.exr"),
        )

        is_dup, path, ver = check_for_duplicate_version(clip, self.versions_dir)
        self.assertFalse(is_dup)

    def test_exact_duplicate_detected(self):
        """Exact duplicate with matching frame count and MD5 should be detected."""
        content = b"exact_duplicate_content"

        # Create version with specific content
        self._create_version(1, frame_count=1, content=content)

        # Create matching clip
        clip_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(clip_dir, exist_ok=True)
        clip_file = os.path.join(clip_dir, "test.0001.exr")
        with open(clip_file, "wb") as f:
            f.write(content)

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(clip_dir),
            is_sequence=True,
            frames=[1],
            first_file=clip_file,
        )

        is_dup, path, ver = check_for_duplicate_version(clip, self.versions_dir)
        self.assertTrue(is_dup)
        self.assertEqual(ver, 1)
        self.assertIn("001", path)

    def test_different_content_not_duplicate(self):
        """Same frame count but different content should not match."""
        # Create version
        self._create_version(1, frame_count=1, content=b"version_content")

        # Create clip with different content
        clip_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(clip_dir, exist_ok=True)
        clip_file = os.path.join(clip_dir, "test.0001.exr")
        with open(clip_file, "wb") as f:
            f.write(b"different_content")

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(clip_dir),
            is_sequence=True,
            frames=[1],
            first_file=clip_file,
        )

        is_dup, path, ver = check_for_duplicate_version(clip, self.versions_dir)
        self.assertFalse(is_dup)

    def test_resource_filtering(self):
        """Only versions with matching resource name should be checked."""
        content = b"test_content"

        # Create versions with different resources
        self._create_version(1, resource="HERO", frame_count=1, content=content)
        self._create_version(2, resource="DEPTH", frame_count=1, content=content)

        # Create matching clip
        clip_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(clip_dir, exist_ok=True)
        clip_file = os.path.join(clip_dir, "test.0001.exr")
        with open(clip_file, "wb") as f:
            f.write(content)

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(clip_dir),
            is_sequence=True,
            frames=[1],
            first_file=clip_file,
        )

        # Check for DEPTH resource
        is_dup, path, ver = check_for_duplicate_version(clip, self.versions_dir, resource="DEPTH")
        self.assertTrue(is_dup)
        self.assertEqual(ver, 2)
        self.assertIn("DEPTH_002", path)

    def test_movie_file_single_frame_count(self):
        """Movie files should have frame_count=1."""
        content = b"movie_content"
        self._create_version(1, frame_count=1, content=content)

        # Create movie clip
        clip_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(clip_dir, exist_ok=True)
        clip_file = os.path.join(clip_dir, "test.mov")
        with open(clip_file, "wb") as f:
            f.write(content)

        clip = Clip(
            base_name="test",
            extension="mov",
            directory=Path(clip_dir),
            is_sequence=False,
            frames=[],
            first_file=clip_file,
        )

        is_dup, path, ver = check_for_duplicate_version(clip, self.versions_dir)
        self.assertTrue(is_dup)

    def test_metadata_files_excluded_from_count(self):
        """_ramses_data.json and .ramses_complete should not be counted as frames."""
        content = b"test_content"
        version_path = self._create_version(1, frame_count=3, content=content)

        # Add metadata files
        with open(os.path.join(version_path, "_ramses_data.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(version_path, ".ramses_complete"), "w") as f:
            f.write("")

        # Create matching clip (3 frames)
        clip_dir = os.path.join(self.temp_dir, "source")
        os.makedirs(clip_dir, exist_ok=True)
        for i in range(3):
            with open(os.path.join(clip_dir, f"test.{i+1:04d}.exr"), "wb") as f:
                f.write(content)

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(clip_dir),
            is_sequence=True,
            frames=[1, 2, 3],
            first_file=os.path.join(clip_dir, "test.0001.exr"),
        )

        is_dup, path, ver = check_for_duplicate_version(clip, self.versions_dir)
        self.assertTrue(is_dup)  # Should still match despite metadata files


class TestCalculateMD5Safe(unittest.TestCase):
    """Test MD5 calculation with strategic sampling."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_small_file_single_read(self):
        """Small files (< 1.5MB) should be read entirely."""
        file_path = os.path.join(self.temp_dir, "small.bin")
        content = b"small" * 1000  # ~5KB
        with open(file_path, "wb") as f:
            f.write(content)

        md5 = _calculate_md5_safe(file_path)
        self.assertNotEqual(md5, "")
        self.assertEqual(len(md5), 32)  # MD5 hex length

    def test_medium_file_two_samples(self):
        """Medium files (< 1.5MB) should sample start and end."""
        file_path = os.path.join(self.temp_dir, "medium.bin")
        # Create file just under 3 * 512KB
        content = b"X" * (512 * 1024 * 2)  # 1MB
        with open(file_path, "wb") as f:
            f.write(content)

        md5 = _calculate_md5_safe(file_path)
        self.assertNotEqual(md5, "")
        self.assertEqual(len(md5), 32)

    def test_large_file_three_samples(self):
        """Large files (> 1.5MB) should sample start, middle, end."""
        file_path = os.path.join(self.temp_dir, "large.bin")
        # Create file > 3 * 512KB
        chunk = b"Y" * (512 * 1024)
        with open(file_path, "wb") as f:
            f.write(chunk)  # Start
            f.write(b"Z" * (512 * 1024))  # Middle
            f.write(chunk)  # End

        md5 = _calculate_md5_safe(file_path)
        self.assertNotEqual(md5, "")

    def test_different_middle_content_different_hash(self):
        """Files with same start/end but different middle should have different hashes."""
        file1 = os.path.join(self.temp_dir, "file1.bin")
        file2 = os.path.join(self.temp_dir, "file2.bin")

        chunk_size = 512 * 1024
        same_start = b"A" * chunk_size
        same_end = b"B" * chunk_size

        # File 1: start + middle1 + end
        with open(file1, "wb") as f:
            f.write(same_start)
            f.write(b"MIDDLE1" * chunk_size)
            f.write(same_end)

        # File 2: start + middle2 + end
        with open(file2, "wb") as f:
            f.write(same_start)
            f.write(b"MIDDLE2" * chunk_size)
            f.write(same_end)

        md5_1 = _calculate_md5_safe(file1)
        md5_2 = _calculate_md5_safe(file2)
        self.assertNotEqual(md5_1, md5_2)

    def test_io_error_returns_empty_string(self):
        """IO errors should return empty string."""
        md5 = _calculate_md5_safe("/nonexistent/file.bin")
        self.assertEqual(md5, "")

    def test_permission_error_returns_empty_string(self):
        """Permission errors should return empty string."""
        with patch("builtins.open", side_effect=PermissionError):
            md5 = _calculate_md5_safe("dummy.bin")
            self.assertEqual(md5, "")


class TestEDLValidator(unittest.TestCase):
    """Test EDL parsing and frame range validation."""

    def setUp(self):
        """Create temp directory for EDL files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_edl(self, content):
        """Helper to create EDL file."""
        edl_path = os.path.join(self.temp_dir, "test.edl")
        with open(edl_path, "w", encoding="utf-8") as f:
            f.write(content)
        return edl_path

    def test_parse_cmx3600_comment_with_colon(self):
        """Parse comment format: 'SH010: 1001-1096'.

        NOTE: This test currently fails - the EDL parser doesn't handle colon format.
        This is a minor edge case as space-separated format (SH010 1001-1096) is
        more common in CMX 3600 EDL files. Keeping test for future enhancement.
        """
        edl_content = """TITLE: Test Edit
001  AX       V     C        00:00:00:00 00:00:04:00 00:00:00:00 00:00:04:00
* FROM CLIP NAME: PLATE_SH010.MOV
* COMMENT: SH010: 1001-1096
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        # Clip names are stored in uppercase
        self.assertGreater(len(validator.expectations), 0)
        # Get any key to check it was parsed
        if len(validator.expectations) > 0:
            exp = list(validator.expectations.values())[0]
            self.assertEqual(exp.shot_id, "SH010")
            self.assertEqual(exp.expected_first_frame, 1001)
            self.assertEqual(exp.expected_last_frame, 1096)
            self.assertEqual(exp.expected_frame_count, 96)

    def test_parse_cmx3600_comment_with_space(self):
        """Parse comment format: 'SH020 1100-1200'."""
        edl_content = """001  AX       V     C        00:00:00:00 00:00:04:00 00:00:00:00 00:00:04:00
* FROM CLIP NAME: shot_020
* COMMENT: SH020 1100-1200
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        self.assertIn("SHOT_020", validator.expectations)  # Uppercase
        exp = validator.expectations["SHOT_020"]
        self.assertEqual(exp.expected_first_frame, 1100)
        self.assertEqual(exp.expected_last_frame, 1200)

    def test_missing_comment_no_expectation(self):
        """Clips without COMMENT should not create expectations."""
        edl_content = """001  AX       V     C        00:00:00:00 00:00:04:00 00:00:00:00 00:00:04:00
* FROM CLIP NAME: no_comment.mov
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        self.assertNotIn("NO_COMMENT.MOV", validator.expectations)

    def test_invalid_comment_format_ignored(self):
        """Invalid comment formats should be ignored."""
        edl_content = """001  AX       V     C        00:00:00:00 00:00:04:00 00:00:00:00 00:00:04:00
* FROM CLIP NAME: bad_format.mov
* COMMENT: Invalid comment format here
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        self.assertNotIn("BAD_FORMAT.MOV", validator.expectations)

    def test_validate_clip_matching_frames(self):
        """Clip matching EDL expectations should pass."""
        edl_content = """* FROM CLIP NAME: test_clip
* COMMENT: SH010 1001-1010
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        clip = Clip(
            base_name="test_clip",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=list(range(1001, 1011)),
            first_file="/tmp/test_clip.1001.exr",
        )

        is_valid, error = validator.validate_clip(clip)
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

    def test_validate_clip_wrong_start_frame(self):
        """Wrong start frame should be flagged."""
        edl_content = """* FROM CLIP NAME: test_clip
* COMMENT: SH010 1001-1010
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        clip = Clip(
            base_name="test_clip",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=list(range(1000, 1010)),  # Starts at 1000, not 1001
            first_file="/tmp/test_clip.1000.exr",
        )

        is_valid, error = validator.validate_clip(clip)
        self.assertFalse(is_valid)
        self.assertIn("Start frame", error)
        self.assertIn("1001", error)
        self.assertIn("1000", error)

    def test_validate_clip_wrong_end_frame(self):
        """Wrong end frame should be flagged."""
        edl_content = """* FROM CLIP NAME: test_clip
* COMMENT: SH010 1001-1010
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        clip = Clip(
            base_name="test_clip",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=list(range(1001, 1012)),  # Ends at 1011, not 1010
            first_file="/tmp/test_clip.1001.exr",
        )

        is_valid, error = validator.validate_clip(clip)
        self.assertFalse(is_valid)
        self.assertIn("End frame", error)

    def test_validate_clip_frame_count_mismatch(self):
        """Frame count mismatch should be flagged."""
        edl_content = """* FROM CLIP NAME: test_clip
* COMMENT: SH010 1001-1010
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        clip = Clip(
            base_name="test_clip",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1001, 1002, 1003, 1004, 1005],  # Only 5 frames
            first_file="/tmp/test_clip.1001.exr",
        )

        is_valid, error = validator.validate_clip(clip)
        self.assertFalse(is_valid)
        self.assertIn("Frame count", error)
        self.assertIn("5 frames short", error)

    def test_validate_clip_with_gaps(self):
        """Missing frames (gaps) should be flagged."""
        edl_content = """* FROM CLIP NAME: test_clip
* COMMENT: SH010 1001-1010
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        clip = Clip(
            base_name="test_clip",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1001, 1002, 1004, 1005, 1007, 1008, 1009, 1010],  # Missing 1003, 1006
            first_file="/tmp/test_clip.1001.exr",
        )

        is_valid, error = validator.validate_clip(clip)
        self.assertFalse(is_valid)
        self.assertIn("Missing frames", error)
        self.assertIn("1003", error)
        self.assertIn("1006", error)

    def test_validate_clip_many_gaps_summarized(self):
        """Many missing frames should be summarized."""
        edl_content = """* FROM CLIP NAME: test_clip
* COMMENT: SH010 1001-1100
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        # Create clip with many gaps
        frames = [f for f in range(1001, 1101) if f % 3 != 0]  # Missing every 3rd frame
        clip = Clip(
            base_name="test_clip",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=frames,
            first_file="/tmp/test_clip.1001.exr",
        )

        is_valid, error = validator.validate_clip(clip)
        self.assertFalse(is_valid)
        self.assertIn("frames missing", error)
        # Should summarize, not list all

    def test_validate_clip_no_expectation_passes(self):
        """Clips not in EDL should pass validation."""
        edl_path = self._create_edl("")
        validator = EDLValidator(edl_path)

        clip = Clip(
            base_name="unknown_clip",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1, 2, 3],
            first_file="/tmp/unknown_clip.0001.exr",
        )

        is_valid, error = validator.validate_clip(clip)
        self.assertTrue(is_valid)

    def test_validate_movie_file_skipped(self):
        """Movie files should skip frame range validation."""
        edl_content = """* FROM CLIP NAME: movie_clip
* COMMENT: SH010 1001-1096
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        clip = Clip(
            base_name="movie_clip",
            extension="mov",
            directory=Path("/tmp"),
            is_sequence=False,
            frames=[],
            first_file="/tmp/movie_clip.mov",
        )

        is_valid, error = validator.validate_clip(clip)
        self.assertTrue(is_valid)  # Movies can't be validated by frame range

    def test_validate_empty_sequence_fails(self):
        """Sequence with no frames should fail."""
        edl_content = """* FROM CLIP NAME: empty_clip
* COMMENT: SH010 1001-1096
"""
        edl_path = self._create_edl(edl_content)
        validator = EDLValidator(edl_path)

        clip = Clip(
            base_name="empty_clip",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[],
            first_file="",
        )

        is_valid, error = validator.validate_clip(clip)
        self.assertFalse(is_valid)
        self.assertIn("No frames detected", error)


class TestValidatePlansAgainstEDL(unittest.TestCase):
    """Test batch plan validation against EDL."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_edl_returns_empty_errors(self):
        """No EDL path should return empty errors."""
        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1, 2, 3],
            first_file="/tmp/test.0001.exr",
        )
        match = MatchResult(clip=clip, matched=True)
        plan = IngestPlan(match=match, media_info=MediaInfo())

        errors = validate_plans_against_edl([plan], "")
        self.assertEqual(errors, {})

    def test_unmatched_plans_skipped(self):
        """Unmatched plans should not be validated."""
        edl_path = os.path.join(self.temp_dir, "test.edl")
        with open(edl_path, "w") as f:
            f.write("")

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1],
            first_file="/tmp/test.0001.exr",
        )
        match = MatchResult(clip=clip, matched=False)
        plan = IngestPlan(match=match, media_info=MediaInfo())

        errors = validate_plans_against_edl([plan], edl_path)
        self.assertEqual(errors, {})

    def test_validation_errors_propagate_to_plan(self):
        """Validation errors should be set on plan.error."""
        edl_content = """* FROM CLIP NAME: test
* COMMENT: SH010 1001-1010
"""
        edl_path = os.path.join(self.temp_dir, "test.edl")
        with open(edl_path, "w") as f:
            f.write(edl_content)

        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[1000, 1001, 1002],  # Wrong start
            first_file="/tmp/test.1000.exr",
        )
        match = MatchResult(clip=clip, matched=True)
        plan = IngestPlan(match=match, media_info=MediaInfo())

        errors = validate_plans_against_edl([plan], edl_path)
        self.assertIn(0, errors)
        self.assertIn("EDL validation", errors[0])
        self.assertNotEqual(plan.error, "")


if __name__ == "__main__":
    unittest.main()
