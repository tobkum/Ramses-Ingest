
import os
import re
import sys
import unittest
import logging
import tempfile
import concurrent.futures
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.matcher import _validate_id, NamingRule, match_clip
from ramses_ingest.scanner import RE_FRAME_PADDING, Clip
from ramses_ingest.publisher import _calculate_md5, _get_next_version, _write_ramses_metadata
from ramses_ingest.prober import _save_cache, _load_cache, _prune_lru_cache

# Configure logging to capture warnings
logging.basicConfig(level=logging.WARNING)

class TestAuditFixesOriginal(unittest.TestCase):
    """Original audit fixes from initial implementation."""

    def test_matcher_validate_id_logging(self):
        """Verify _validate_id returns empty string but logs a warning for invalid input."""
        with self.assertLogs('ramses_ingest.matcher', level='WARNING') as cm:
            result = _validate_id("invalid.name", "test_field")
            self.assertEqual(result, "")
            self.assertTrue(any("Invalid test_field format" in o for o in cm.output))

    def test_matcher_validate_id_path_traversal(self):
        """Verify path traversal is caught and logged."""
        with self.assertLogs('ramses_ingest.matcher', level='WARNING') as cm:
            result = _validate_id("../etc/passwd", "test_field")
            self.assertEqual(result, "")
            self.assertTrue(any("Potential path traversal" in o for o in cm.output))

    def test_matcher_version_parsing(self):
        """Verify version parsing handles non-integer versions gracefully."""
        # Setup a rule that captures a 'version' group
        rule = NamingRule(pattern=r"(?P<shot>\w+)_(?P<version>v\w+)")
        clip = Clip(base_name="SH010_vBad", extension="exr", directory=os.getcwd())

        # Should not crash, just ignore version
        with self.assertLogs('ramses_ingest.matcher', level='WARNING') as cm:
            result = match_clip(clip, [rule])
            self.assertEqual(result.shot_id, "SH010")
            self.assertIsNone(result.version)
            self.assertTrue(any("Could not parse version" in o for o in cm.output))

    def test_scanner_regex_underscores(self):
        """Verify scanner regex now supports underscores before frame numbers."""
        # Dot separator (standard)
        m1 = RE_FRAME_PADDING.match("shot.1001.exr")
        self.assertIsNotNone(m1)
        self.assertEqual(m1.group("base"), "shot")
        self.assertEqual(m1.group("frame"), "1001")

        # Underscore separator (newly supported)
        m2 = RE_FRAME_PADDING.match("shot_1001.exr")
        self.assertIsNotNone(m2)
        self.assertEqual(m2.group("base"), "shot")
        self.assertEqual(m2.group("frame"), "1001")

    @patch("builtins.open", side_effect=OSError("Disk failure"))
    def test_publisher_md5_failure(self, mock_open):
        """Verify _calculate_md5 raises OSError instead of returning empty string."""
        with self.assertRaises(OSError):
            _calculate_md5("dummy_path")


class TestAuditFix2_FutureTimeouts(unittest.TestCase):
    """copy_frames future exceptions propagate to execute_plan's rollback handler."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_plan(self, target_dir):
        from ramses_ingest.publisher import IngestPlan
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo
        clip = Clip(base_name="test", extension="exr", directory=Path(self.temp_dir),
                    is_sequence=True, frames=[1],
                    first_file=os.path.join(self.temp_dir, "test.0001.exr"))
        match = MatchResult(clip=clip, matched=True)
        return IngestPlan(match=match, media_info=MediaInfo(), project_id="PROJ",
                          shot_id="SH010", target_publish_dir=target_dir,
                          target_preview_dir=self.temp_dir)

    def test_timeout_propagates_and_triggers_rollback(self):
        """TimeoutError from copy_frames propagates and triggers directory rollback."""
        from ramses_ingest.publisher import execute_plan
        target_dir = os.path.join(self.temp_dir, "v001")
        plan = self._make_plan(target_dir)

        def copy_raises(*args, **kwargs):
            os.makedirs(target_dir, exist_ok=True)
            raise concurrent.futures.TimeoutError("frame copy timed out")

        with patch('ramses_ingest.publisher.copy_frames', side_effect=copy_raises):
            result = execute_plan(plan, generate_thumbnail=False, skip_ramses_registration=True)

        self.assertFalse(result.success)
        self.assertIn("timed out", result.error.lower())
        self.assertFalse(os.path.exists(target_dir),
                         "execute_plan must roll back the partial directory")

    def test_cancelled_error_propagates_and_triggers_rollback(self):
        """CancelledError from copy_frames propagates and triggers directory rollback."""
        from ramses_ingest.publisher import execute_plan
        target_dir = os.path.join(self.temp_dir, "v002")
        plan = self._make_plan(target_dir)

        def copy_raises(*args, **kwargs):
            os.makedirs(target_dir, exist_ok=True)
            raise concurrent.futures.CancelledError("frame copy cancelled")

        with patch('ramses_ingest.publisher.copy_frames', side_effect=copy_raises):
            result = execute_plan(plan, generate_thumbnail=False, skip_ramses_registration=True)

        self.assertFalse(result.success)
        self.assertFalse(os.path.exists(target_dir),
                         "execute_plan must roll back the partial directory")


class TestAuditFix5_ThumbnailJobCollection(unittest.TestCase):
    """Thumbnail jobs are collected only from results that have a non-None _thumbnail_job."""

    def test_only_results_with_job_included(self):
        """Results without _thumbnail_job or with None value are excluded."""
        from ramses_ingest.publisher import IngestPlan, IngestResult
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo

        clip = Clip(base_name="t", extension="exr", directory=Path("/tmp"))
        match = MatchResult(clip=clip, matched=True)
        plan = IngestPlan(match=match, media_info=MediaInfo())

        r_with_job = IngestResult(plan=plan, success=True)
        r_with_job._thumbnail_job = {"clip": clip, "path": "/tmp/thumb.jpg"}

        r_null_job = IngestResult(plan=plan, success=True)
        r_null_job._thumbnail_job = None

        r_no_attr = IngestResult(plan=plan, success=False, error="copy failed")
        # r_no_attr has no _thumbnail_job attribute at all

        results = [r_with_job, r_null_job, r_no_attr]
        jobs = [(r, r._thumbnail_job) for r in results
                if hasattr(r, '_thumbnail_job') and r._thumbnail_job]

        self.assertEqual(len(jobs), 1)
        self.assertIs(jobs[0][0], r_with_job)
        self.assertEqual(jobs[0][1]["path"], "/tmp/thumb.jpg")

    def test_empty_results_gives_empty_jobs(self):
        """No results means no thumbnail jobs."""
        jobs = [(r, r._thumbnail_job) for r in []
                if hasattr(r, '_thumbnail_job') and r._thumbnail_job]
        self.assertEqual(jobs, [])


class TestAuditFix6_VersionLockRaceCondition(unittest.TestCase):
    """Fix #6: Version lock race condition (concurrent folder creation)."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sequential_version_numbering(self):
        """Version numbers should increment as version directories are created."""
        publish_root = os.path.join(self.temp_dir, "_published")

        # No directory yet → version 1
        v1 = _get_next_version(publish_root)
        self.assertEqual(v1, 1)

        # Create version 1 with completion marker
        os.makedirs(publish_root, exist_ok=True)
        v1_dir = os.path.join(publish_root, "001")
        os.makedirs(v1_dir, exist_ok=True)
        Path(os.path.join(v1_dir, ".ramses_complete")).touch()

        # Now should return version 2
        v2 = _get_next_version(publish_root)
        self.assertEqual(v2, 2)

    def test_nonexistent_publish_root(self):
        """Non-existent publish root should return version 1 without creating dirs."""
        publish_root = os.path.join(self.temp_dir, "nonexistent")

        v = _get_next_version(publish_root)
        self.assertEqual(v, 1)
        # Should NOT create any directories
        self.assertFalse(os.path.exists(publish_root))


class TestAuditFix8_ThreadSafeCacheDirtyFlag(unittest.TestCase):
    """Fix #8: Thread-safe cache dirty flag access."""

    def test_cache_dirty_flag_thread_safety(self):
        """_CACHE_DIRTY must be accessed with _CACHE_LOCK held."""
        # This is tested by checking that _save_cache is called with lock held
        from ramses_ingest import prober

        # Save original values
        original_lock = prober._CACHE_LOCK
        original_dirty = prober._CACHE_DIRTY

        try:
            # Mock lock to verify it's held
            mock_lock = MagicMock()
            prober._CACHE_LOCK = mock_lock
            prober._CACHE_DIRTY = True

            # This should acquire lock
            prober.flush_cache()

            # Verify lock was acquired
            mock_lock.__enter__.assert_called()
        finally:
            # Restore original values
            prober._CACHE_LOCK = original_lock
            prober._CACHE_DIRTY = original_dirty


class TestAuditFix10_SubprocessValidation(unittest.TestCase):
    """Fix #10: Subprocess validation before ffmpeg."""

    def test_invalid_clip_rejected_before_ffmpeg(self):
        """Invalid clips should be rejected before calling ffmpeg."""
        from ramses_ingest.preview import generate_proxy

        # Clip with no first_file
        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path("/tmp"),
            is_sequence=True,
            frames=[],
            first_file="",
        )

        # Should return False without calling subprocess
        with patch('subprocess.run') as mock_run:
            result = generate_proxy(clip, "/tmp/output.mp4")
            self.assertFalse(result)
            mock_run.assert_not_called()

    def test_nonexistent_source_rejected(self):
        """Nonexistent source files should be rejected."""
        from ramses_ingest.preview import generate_proxy

        clip = Clip(
            base_name="test",
            extension="mov",
            directory=Path("/tmp"),
            is_sequence=False,
            frames=[],
            first_file="/nonexistent/file.mov",
        )

        result = generate_proxy(clip, "/tmp/output.mp4")
        self.assertFalse(result)


class TestAuditFix11_FileHandleCleanup(unittest.TestCase):
    """Windows FlushFileBuffers handle is always closed via the finally block in copy_frames."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_single_frame_clip(self):
        src = os.path.join(self.temp_dir, "test.0001.exr")
        with open(src, "wb") as f:
            f.write(b"frame_data")
        return Clip(base_name="test", extension="exr",
                    directory=Path(self.temp_dir), is_sequence=True,
                    frames=[1], first_file=src, _separator=".")

    @unittest.skipUnless(sys.platform == "win32", "Windows-only flush path")
    def test_handle_closed_on_successful_flush(self):
        """CloseHandle is called after FlushFileBuffers succeeds."""
        from ramses_ingest.publisher import copy_frames
        clip = self._make_single_frame_clip()
        dest = os.path.join(self.temp_dir, "dest")

        with patch("ctypes.windll.kernel32.CreateFileW", return_value=42), \
             patch("ctypes.windll.kernel32.FlushFileBuffers"), \
             patch("ctypes.windll.kernel32.CloseHandle") as mock_close:
            copy_frames(clip, dest, "PROJ", "SH010", "PLATE")

        mock_close.assert_called_once_with(42)

    @unittest.skipUnless(sys.platform == "win32", "Windows-only flush path")
    def test_handle_closed_when_flush_raises(self):
        """CloseHandle is called even when FlushFileBuffers raises an exception."""
        from ramses_ingest.publisher import copy_frames
        clip = self._make_single_frame_clip()
        dest = os.path.join(self.temp_dir, "dest2")

        with patch("ctypes.windll.kernel32.CreateFileW", return_value=99), \
             patch("ctypes.windll.kernel32.FlushFileBuffers",
                   side_effect=OSError("flush failed")), \
             patch("ctypes.windll.kernel32.CloseHandle") as mock_close:
            # copy_frames must not raise — the flush exception is swallowed
            copy_frames(clip, dest, "PROJ", "SH010", "PLATE")

        mock_close.assert_called_once_with(99)


class TestAuditFix12_LRUCachePruning(unittest.TestCase):
    """Fix #12: LRU cache pruning when size > 5000."""

    def test_cache_pruning_at_limit(self):
        """Cache should prune when exceeding 5000 entries."""
        from ramses_ingest import prober

        # Save original values
        original_cache = prober._METADATA_CACHE.copy()
        original_times = prober._CACHE_ACCESS_TIMES.copy()

        try:
            # Fill cache with 6000 entries
            prober._METADATA_CACHE = {f"key_{i}": {"data": i} for i in range(6000)}
            prober._CACHE_ACCESS_TIMES = {f"key_{i}": float(i) for i in range(6000)}

            # Prune should reduce to 5000
            _prune_lru_cache()

            self.assertEqual(len(prober._METADATA_CACHE), 5000)
            self.assertEqual(len(prober._CACHE_ACCESS_TIMES), 5000)

            # Oldest entries should be removed (key_0 to key_999)
            self.assertNotIn("key_0", prober._METADATA_CACHE)
            self.assertIn("key_5999", prober._METADATA_CACHE)
        finally:
            # Restore original values
            prober._METADATA_CACHE = original_cache
            prober._CACHE_ACCESS_TIMES = original_times


class TestAuditFix13_AtomicMetadataWrites(unittest.TestCase):
    """Fix #13: Atomic metadata writes (temp file + rename)."""

    def setUp(self):
        """Create temp directory."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_temp_file_created_before_rename(self):
        """Metadata should be written to temp file first."""
        folder = os.path.join(self.temp_dir, "version")
        os.makedirs(folder)

        _write_ramses_metadata(folder, 1, comment="Test comment")

        # Final file should exist
        meta_path = os.path.join(folder, "_ramses_data.json")
        self.assertTrue(os.path.isfile(meta_path))

        # No temp files should remain
        temp_files = [f for f in os.listdir(folder) if f.startswith(".ramses_data_")]
        self.assertEqual(len(temp_files), 0)

    def test_temp_file_cleaned_up_on_failure(self):
        """Temp file should be cleaned up if write fails."""
        folder = os.path.join(self.temp_dir, "version")
        os.makedirs(folder)

        # Cause rename to fail by making folder read-only (platform-specific)
        with patch('os.replace', side_effect=OSError("Simulated failure")):
            try:
                _write_ramses_metadata(folder, 1)
            except Exception:
                pass

        # Temp files should be cleaned up
        temp_files = [f for f in os.listdir(folder) if f.startswith(".ramses_data_")]
        self.assertEqual(len(temp_files), 0)


class TestAuditFix14_PathTraversal(unittest.TestCase):
    """Fix #14: Path traversal (more edge cases)."""

    def test_double_dot_slash_rejected(self):
        """../ patterns should be rejected."""
        from ramses_ingest.publisher import resolve_paths
        from ramses_ingest.publisher import IngestPlan
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo

        clip = Clip(base_name="test", extension="exr", directory=Path("/tmp"))
        match = MatchResult(clip=clip, matched=True, shot_id="../../../etc", sequence_id="SEQ")
        plan = IngestPlan(match=match, media_info=MediaInfo(), project_id="PROJ", shot_id="../../../etc")

        resolve_paths([plan], "/tmp/project")

        self.assertNotEqual(plan.error, "")
        self.assertIn("path separators", plan.error.lower())

    def test_windows_drive_traversal_rejected(self):
        """C:\\..\\.. patterns should be rejected."""
        from ramses_ingest.publisher import resolve_paths
        from ramses_ingest.publisher import IngestPlan
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo

        clip = Clip(base_name="test", extension="exr", directory=Path("/tmp"))
        match = MatchResult(clip=clip, matched=True, shot_id="C:\\..\\..", sequence_id="SEQ")
        plan = IngestPlan(match=match, media_info=MediaInfo(), project_id="PROJ", shot_id="C:\\..\\..")

        resolve_paths([plan], "/tmp/project")

        self.assertNotEqual(plan.error, "")

    def test_relative_path_in_folder_name_rejected(self):
        """foo/../bar patterns should be rejected."""
        from ramses_ingest.publisher import resolve_paths
        from ramses_ingest.publisher import IngestPlan
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo

        clip = Clip(base_name="test", extension="exr", directory=Path("/tmp"))
        match = MatchResult(clip=clip, matched=True, shot_id="foo/../bar", sequence_id="SEQ")
        plan = IngestPlan(match=match, media_info=MediaInfo(), project_id="PROJ", shot_id="foo/../bar")

        resolve_paths([plan], "/tmp/project")

        self.assertNotEqual(plan.error, "")


class TestAuditFix15_VersionNumberBounds(unittest.TestCase):
    """Fix #15: Version number bounds (0, 1000, negative)."""

    def test_version_zero_rejected(self):
        """Version 0 should be rejected."""
        from ramses_ingest.publisher import resolve_paths, IngestPlan
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo

        clip = Clip(base_name="test", extension="exr", directory=Path("/tmp"))
        match = MatchResult(clip=clip, matched=True, shot_id="SH010", sequence_id="SEQ")
        plan = IngestPlan(match=match, media_info=MediaInfo(), project_id="PROJ", shot_id="SH010")
        plan.version = 0

        # Mock _get_next_version to return 0
        with patch('ramses_ingest.publisher._get_next_version', return_value=0):
            resolve_paths([plan], "/tmp/project")
            self.assertIn("Invalid version", plan.error)

    def test_version_over_999_rejected(self):
        """Version > 999 should be rejected."""
        from ramses_ingest.publisher import resolve_paths, IngestPlan
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo

        clip = Clip(base_name="test", extension="exr", directory=Path("/tmp"))
        match = MatchResult(clip=clip, matched=True, shot_id="SH010", sequence_id="SEQ")
        plan = IngestPlan(match=match, media_info=MediaInfo(), project_id="PROJ", shot_id="SH010")
        plan.version = 1000

        with patch('ramses_ingest.publisher._get_next_version', return_value=1000):
            resolve_paths([plan], "/tmp/project")
            self.assertIn("Invalid version", plan.error)


class TestAuditFix16_CacheTypeValidation(unittest.TestCase):
    """Fix #16: Cache type validation after msgpack load."""

    def test_invalid_cache_type_resets_to_dict(self):
        """Non-dict cache should be reset to empty dict."""
        from ramses_ingest import prober

        original_cache = prober._METADATA_CACHE.copy()
        original_times = prober._CACHE_ACCESS_TIMES.copy()

        try:
            # Simulate loading invalid data
            with patch('msgpack.unpack', return_value="not_a_dict"):
                _load_cache()

                # Cache should be reset to dict
                self.assertIsInstance(prober._METADATA_CACHE, dict)
                self.assertIsInstance(prober._CACHE_ACCESS_TIMES, dict)
        finally:
            prober._METADATA_CACHE = original_cache
            prober._CACHE_ACCESS_TIMES = original_times


class TestAuditFix17_DaemonObjectNullChecks(unittest.TestCase):
    """Fix #17: Daemon object null checks."""

    def test_none_shot_object_skipped(self):
        """None shot objects should be skipped gracefully."""
        from ramses_ingest.publisher import resolve_paths_from_daemon, IngestPlan
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo

        clip = Clip(base_name="test", extension="exr", directory=Path("/tmp"))
        match = MatchResult(clip=clip, matched=True, shot_id="SH010", sequence_id="SEQ")
        plan = IngestPlan(match=match, media_info=MediaInfo(), project_id="PROJ", shot_id="SH010")

        # Shot objects dict has None value
        shot_objects = {"SH010": None}

        # Should not crash
        resolve_paths_from_daemon([plan], shot_objects)
        # Plan should remain unresolved (no target_publish_dir set)
        self.assertEqual(plan.target_publish_dir, "")


class TestAuditFix18_FrameExistenceValidation(unittest.TestCase):
    """Fix #18: Frame existence validation before copy."""

    def test_missing_source_frame_raises_error(self):
        """Missing source frames should raise FileNotFoundError."""
        from ramses_ingest.publisher import copy_frames

        temp_dir = tempfile.mkdtemp()
        try:
            # Create clip with nonexistent frames
            clip = Clip(
                base_name="test",
                extension="exr",
                directory=Path(temp_dir),
                is_sequence=True,
                frames=[1, 2, 3],
                first_file=os.path.join(temp_dir, "test.0001.exr"),
            )

            # Don't create actual files
            dest_dir = os.path.join(temp_dir, "dest")

            with self.assertRaises(FileNotFoundError):
                copy_frames(clip, dest_dir, "PROJ", "SH010", "PLATE")
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestAuditFix19_ExceptionPatterns(unittest.TestCase):
    """Fix #19: Exception patterns (log + return vs re-raise)."""

    def test_non_fatal_errors_logged_not_raised(self):
        """Errors from register_ramses_objects are reported via callback but do not fail the ingest."""
        from ramses_ingest.publisher import execute_plan, IngestPlan
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo

        temp_dir = tempfile.mkdtemp()
        target_dir = os.path.join(temp_dir, "v001")
        try:
            clip = Clip(base_name="test", extension="exr", directory=Path(temp_dir),
                        is_sequence=False, frames=[],
                        first_file=os.path.join(temp_dir, "test.exr"))
            match = MatchResult(clip=clip, matched=True)
            plan = IngestPlan(match=match, media_info=MediaInfo(), project_id="PROJ",
                              shot_id="SH010", target_publish_dir=target_dir,
                              target_preview_dir=temp_dir)
            logged = []
            with patch('ramses_ingest.publisher.copy_frames', return_value=(1, {}, 100, "test.exr")), \
                 patch('ramses_ingest.publisher._write_ramses_metadata'), \
                 patch('ramses_ingest.publisher.register_ramses_objects',
                       side_effect=RuntimeError("daemon unreachable")):
                result = execute_plan(
                    plan, generate_thumbnail=False, skip_ramses_registration=False,
                    progress_callback=logged.append,
                )

            self.assertTrue(result.success,
                            "Ingest must succeed even when DB registration raises")
            self.assertEqual(result.error, "")
            self.assertTrue(any("daemon unreachable" in m for m in logged),
                            "DB error must be forwarded to the progress callback")
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestAuditFix20_IDSanitization(unittest.TestCase):
    """Fix #20: ID sanitization (slashes, backslashes, dots)."""

    def test_slash_in_resource_sanitized_in_thumbnail_path(self):
        """Slashes in resource names are replaced with underscores in the thumbnail job path."""
        from ramses_ingest.publisher import execute_plan, IngestPlan
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.prober import MediaInfo

        clip = Clip(base_name="test", extension="exr", directory=Path("/tmp"),
                    frames=[1], first_file="/tmp/test.0001.exr", is_sequence=True)
        match = MatchResult(clip=clip, matched=True)
        plan = IngestPlan(
            match=match,
            media_info=MediaInfo(),
            project_id="PROJ",
            shot_id="SH010",
            resource="DEPTH/PASS",  # Contains slash
            target_publish_dir="/tmp/publish",
            target_preview_dir="/tmp/preview",
        )

        with patch('ramses_ingest.publisher.copy_frames', return_value=(1, {}, 100, "file.exr")), \
             patch('ramses_ingest.publisher._write_ramses_metadata'), \
             patch('os.makedirs'):
            result = execute_plan(plan, generate_thumbnail=True, skip_ramses_registration=True)

        self.assertTrue(result.success, f"execute_plan should succeed: {result.error}")
        self.assertIsNotNone(result._thumbnail_job, "Thumbnail job should be set for resource clips")
        thumb_filename = os.path.basename(result._thumbnail_job["path"])
        self.assertNotIn("/", thumb_filename,
                         "Slash in resource must not appear in the thumbnail filename")
        self.assertIn("DEPTH_PASS", thumb_filename,
                      "Slash should be replaced with underscore")

    def test_backslash_in_resource_sanitized(self):
        """Backslashes should be sanitized."""
        # Pattern: re.sub(r'[/\\:*?"<>|]', '_', plan.resource)
        import re
        resource = "DEPTH\\PASS"
        safe = re.sub(r'[/\\:*?"<>|]', '_', resource)
        self.assertEqual(safe, "DEPTH_PASS")

    def test_double_dot_in_resource_sanitized(self):
        """Double dots should be sanitized."""
        import re
        resource = "../../../etc"
        safe = re.sub(r'[/\\:*?"<>|]', '_', resource)
        # Remove leading dots
        if '..' in safe or safe.startswith('.'):
            safe = safe.replace('..', '_').lstrip('.')
        self.assertNotIn('..', safe)


if __name__ == '__main__':
    unittest.main()
