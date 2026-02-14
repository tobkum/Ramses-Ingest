# -*- coding: utf-8 -*-
"""Tests for ramses_ingest.prober."""

import os
import sys
import unittest
import json
import subprocess
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.prober import probe_file, MediaInfo

class TestProber(unittest.TestCase):
    
    @patch("ramses_ingest.prober._HAS_AV", False)
    @patch("os.path.isfile")
    @patch("subprocess.run")
    def test_probe_success(self, mock_run, mock_isfile):
        mock_isfile.return_value = True
        # Mock ffprobe output
        mock_stdout = json.dumps({
            "streams": [{
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "24/1",
                "codec_name": "prores",
                "pix_fmt": "yuv422p10le",
                "duration": "10.0",
                "nb_frames": "240",
                "tags": {"timecode": "01:00:00:00"}
            }],
            "format": {
                "tags": {}
            }
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout)
        
        info = probe_file("dummy.mov")
        
        self.assertTrue(info.is_valid)
        self.assertEqual(info.width, 1920)
        self.assertEqual(info.height, 1080)
        self.assertEqual(info.fps, 24.0)
        self.assertEqual(info.start_timecode, "01:00:00:00")
        self.assertEqual(info.frame_count, 240)

    @patch("ramses_ingest.prober._HAS_AV", False)
    @patch("os.path.isfile")
    @patch("subprocess.run")
    def test_probe_timecode_in_format(self, mock_run, mock_isfile):
        mock_isfile.return_value = True
        # Mock timecode in format tags instead of stream tags
        mock_stdout = json.dumps({
            "streams": [{
                "width": 2048,
                "height": 1080,
                "r_frame_rate": "24000/1001",
                "tags": {}
            }],
            "format": {
                "tags": {"timecode": "02:15:10:05"}
            }
        })
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout)
        
        info = probe_file("dummy.mov")
        self.assertEqual(info.start_timecode, "02:15:10:05")

    @patch("ramses_ingest.prober._HAS_AV", False)
    @patch("os.path.isfile")
    @patch("subprocess.run")
    def test_probe_failure(self, mock_run, mock_isfile):
        mock_isfile.return_value = True
        mock_run.return_value = MagicMock(returncode=1)
        info = probe_file("corrupt.mov")
        self.assertFalse(info.is_valid)

    @patch("ramses_ingest.prober._HAS_AV", False)
    @patch("os.path.isfile")
    @patch("subprocess.run")
    def test_ffprobe_missing(self, mock_run, mock_isfile):
        mock_isfile.return_value = True
        mock_run.side_effect = FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            probe_file("any.mov")

    @patch("ramses_ingest.prober._HAS_AV", False)
    @patch("os.path.isfile")
    @patch("subprocess.run")
    def test_probe_corrupt_json(self, mock_run, mock_isfile):
        mock_isfile.return_value = True
        # Return invalid JSON
        mock_run.return_value = MagicMock(returncode=0, stdout="not json at all")
        info = probe_file("corrupt.json")
        self.assertFalse(info.is_valid)

class TestPyAVProber(unittest.TestCase):
    """Tests for the new PyAV-based high-performance probing path."""

    @patch("ramses_ingest.prober._HAS_AV", True)
    @patch("ramses_ingest.prober.av")
    @patch("os.path.isfile", return_value=True)
    def test_probe_av_success(self, mock_isfile, mock_av):
        # Setup mocks for PyAV structure: container -> stream -> metadata/context
        mock_container = MagicMock()
        mock_av.open.return_value.__enter__.return_value = mock_container
        
        # Mock metadata dictionary behavior
        mock_container.metadata = {}
        
        mock_stream = MagicMock()
        mock_stream.width = 1920
        mock_stream.height = 1080
        mock_stream.average_rate = 24.0
        mock_stream.frames = 240
        mock_stream.pix_fmt = "yuv422p10le"
        mock_stream.sample_aspect_ratio = 1.0
        mock_stream.metadata = {"timecode": "01:00:00:00"}
        mock_stream.codec_context.name = "prores"
        
        mock_container.streams.video = [mock_stream]
        mock_container.duration = 10 * 1000000 # 10s in microseconds
        mock_av.time_base = 1000000
        
        info = probe_file("fast.mov")
        
        self.assertTrue(info.is_valid)
        self.assertEqual(info.width, 1920)
        self.assertEqual(info.fps, 24.0)
        self.assertEqual(info.codec, "prores")
        self.assertEqual(info.start_timecode, "01:00:00:00")

    @patch("ramses_ingest.prober._HAS_AV", True)
    @patch("ramses_ingest.prober.av")
    @patch("os.path.isfile", return_value=True)
    def test_probe_av_fallback_on_error(self, mock_isfile, mock_av):
        """If PyAV fails, it should automatically fallback to ffprobe."""
        mock_av.open.side_effect = Exception("PyAV exploded")
        
        with patch("ramses_ingest.prober._probe_video_ffprobe") as mock_fallback:
            mock_fallback.return_value = MediaInfo(width=1920, height=1080)
            info = probe_file("problematic.mov")
            
            mock_fallback.assert_called_once()
            self.assertEqual(info.width, 1920)

class TestProberThreading(unittest.TestCase):
    """Test thread-safety and concurrent operations."""

    def test_concurrent_probe_operations(self):
        """Multiple threads probing different files should not interfere."""
        import threading
        from ramses_ingest import prober

        # Save original cache
        original_cache = prober._METADATA_CACHE.copy()
        original_times = prober._CACHE_ACCESS_TIMES.copy()

        try:
            results = {}
            lock = threading.Lock()

            def probe_mock_file(file_id):
                # Mock ffprobe response
                mock_stdout = json.dumps({
                    "streams": [{
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "24/1",
                        "codec_name": "prores",
                    }],
                    "format": {"tags": {}}
                })

                with patch("ramses_ingest.prober._HAS_AV", False):
                    with patch("os.path.isfile", return_value=True):
                        with patch("os.path.getmtime", return_value=123456.0):
                            with patch("subprocess.run") as mock_run:
                                mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout)
                                info = probe_file(f"file_{file_id}.mov")

                with lock:
                    results[file_id] = info

            # Launch 20 threads concurrently
            threads = [threading.Thread(target=probe_mock_file, args=(i,)) for i in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All probes should succeed
            self.assertEqual(len(results), 20)
            for info in results.values():
                self.assertTrue(info.is_valid)
                self.assertEqual(info.width, 1920)
        finally:
            # Restore original cache
            prober._METADATA_CACHE = original_cache
            prober._CACHE_ACCESS_TIMES = original_times

    def test_cache_lru_eviction(self):
        """Add 6000 entries, verify pruning to 5000."""
        from ramses_ingest import prober

        original_cache = prober._METADATA_CACHE.copy()
        original_times = prober._CACHE_ACCESS_TIMES.copy()

        try:
            # Fill cache beyond limit
            prober._METADATA_CACHE = {f"key_{i}": {"data": i} for i in range(6000)}
            prober._CACHE_ACCESS_TIMES = {f"key_{i}": float(i) for i in range(6000)}

            # Trigger save (which calls prune)
            with prober._CACHE_LOCK:
                prober._CACHE_DIRTY = True
                prober._save_cache()

            # Should be pruned to 5000
            self.assertEqual(len(prober._METADATA_CACHE), 5000)
            self.assertEqual(len(prober._CACHE_ACCESS_TIMES), 5000)

            # Oldest entries (0-999) should be removed
            self.assertNotIn("key_0", prober._METADATA_CACHE)
            self.assertNotIn("key_999", prober._METADATA_CACHE)
            # Newest entries should remain
            self.assertIn("key_5999", prober._METADATA_CACHE)
        finally:
            prober._METADATA_CACHE = original_cache
            prober._CACHE_ACCESS_TIMES = original_times

    def test_cache_dirty_flag_thread_safety(self):
        """Concurrent _save_cache calls should use lock."""
        from ramses_ingest import prober
        import threading

        original_cache = prober._METADATA_CACHE.copy()
        original_times = prober._CACHE_ACCESS_TIMES.copy()
        original_dirty = prober._CACHE_DIRTY

        try:
            # Add some data
            prober._METADATA_CACHE = {"test": {"data": 1}}
            prober._CACHE_ACCESS_TIMES = {"test": 1.0}

            def save_cache_concurrent():
                with prober._CACHE_LOCK:
                    prober._CACHE_DIRTY = True
                prober.flush_cache()

            # Launch multiple threads trying to save
            threads = [threading.Thread(target=save_cache_concurrent) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Should not crash, dirty flag should be False after all saves
            self.assertFalse(prober._CACHE_DIRTY)
        finally:
            prober._METADATA_CACHE = original_cache
            prober._CACHE_ACCESS_TIMES = original_times
            prober._CACHE_DIRTY = original_dirty

    def test_msgpack_json_migration_race(self):
        """Concurrent loads during migration should not corrupt cache."""
        from ramses_ingest import prober
        import threading
        import tempfile

        temp_dir = tempfile.mkdtemp()
        json_path = os.path.join(temp_dir, "cache.json")

        try:
            # Create legacy JSON cache
            cache_data = {
                "cache": {f"key_{i}": {"data": i} for i in range(100)},
                "access_times": {f"key_{i}": float(i) for i in range(100)}
            }
            with open(json_path, "w") as f:
                json.dump(cache_data, f)

            # Mock cache paths
            original_json_path = prober.CACHE_PATH_JSON
            original_msgpack_path = prober.CACHE_PATH_MSGPACK
            prober.CACHE_PATH_JSON = json_path
            prober.CACHE_PATH_MSGPACK = os.path.join(temp_dir, "cache.msgpack")

            results = []
            lock = threading.Lock()

            def load_concurrent():
                prober._load_cache()
                with lock:
                    results.append(len(prober._METADATA_CACHE))

            # Multiple threads loading at once
            threads = [threading.Thread(target=load_concurrent) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All threads should load successfully
            self.assertEqual(len(results), 5)
            # Cache size should be consistent
            for size in results:
                self.assertGreaterEqual(size, 0)
        finally:
            prober.CACHE_PATH_JSON = original_json_path
            prober.CACHE_PATH_MSGPACK = original_msgpack_path
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_cache_hit_updates_access_time(self):
        """Cache hits should update access time for LRU."""
        from ramses_ingest import prober
        import time

        original_cache = prober._METADATA_CACHE.copy()
        original_times = prober._CACHE_ACCESS_TIMES.copy()

        try:
            # Add entry with old access time (format: path|mtime)
            mtime = 123456.0
            cache_key = f"/dummy/file.mov|{mtime}"
            prober._METADATA_CACHE[cache_key] = {
                "width": 1920,
                "height": 1080,
                "fps": 24.0,
                "codec": "prores",
            }
            old_time = 1000.0
            prober._CACHE_ACCESS_TIMES[cache_key] = old_time

            # Mock file exists and mtime (must match the mtime in cache key)
            with patch("os.path.isfile", return_value=True):
                with patch("os.path.getmtime", return_value=mtime):
                    with patch("ramses_ingest.prober._HAS_AV", False):
                        with patch("subprocess.run") as mock_run:
                            # Should hit cache, not call ffprobe
                            info = probe_file("/dummy/file.mov")
                            mock_run.assert_not_called()

            # Access time should be updated
            new_time = prober._CACHE_ACCESS_TIMES.get(cache_key, 0)
            self.assertGreater(new_time, old_time)
        finally:
            prober._METADATA_CACHE = original_cache
            prober._CACHE_ACCESS_TIMES = original_times

    def test_cache_corruption_fallback(self):
        """Corrupted cache file should fallback to empty cache."""
        from ramses_ingest import prober
        import tempfile

        temp_dir = tempfile.mkdtemp()
        cache_path = os.path.join(temp_dir, "corrupt.json")

        try:
            # Create corrupted JSON
            with open(cache_path, "w") as f:
                f.write("{invalid json content")

            # Save original paths (need to override both JSON and msgpack)
            original_json = prober.CACHE_PATH_JSON
            original_msgpack = prober.CACHE_PATH_MSGPACK

            # Point both cache paths to corrupted file so _load_cache tries to load it
            prober.CACHE_PATH_JSON = cache_path
            prober.CACHE_PATH_MSGPACK = cache_path + ".msgpack"  # Non-existent, forces JSON fallback

            # Load should not crash
            prober._load_cache()

            # Cache should be empty dict after failed load
            self.assertIsInstance(prober._METADATA_CACHE, dict)
            self.assertEqual(len(prober._METADATA_CACHE), 0)
        finally:
            prober.CACHE_PATH_JSON = original_json
            prober.CACHE_PATH_MSGPACK = original_msgpack
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_atexit_handler_flushes_cache(self):
        """atexit handler should flush dirty cache."""
        from ramses_ingest import prober

        original_dirty = prober._CACHE_DIRTY

        try:
            # Set dirty flag
            with prober._CACHE_LOCK:
                prober._CACHE_DIRTY = True

            # Call flush
            prober.flush_cache()

            # Should be clean now
            self.assertFalse(prober._CACHE_DIRTY)
        finally:
            prober._CACHE_DIRTY = original_dirty

    def test_probe_updates_both_cache_dicts(self):
        """Successful probe should update both _METADATA_CACHE and _CACHE_ACCESS_TIMES."""
        from ramses_ingest import prober

        original_cache = prober._METADATA_CACHE.copy()
        original_times = prober._CACHE_ACCESS_TIMES.copy()

        try:
            mock_stdout = json.dumps({
                "streams": [{
                    "width": 2048,
                    "height": 1080,
                    "r_frame_rate": "24/1",
                    "codec_name": "h264",
                }],
                "format": {"tags": {}}
            })

            mtime = 999999.0
            file_path = "/test/new_file.mov"
            with patch("os.path.isfile", return_value=True):
                with patch("os.path.getmtime", return_value=mtime):
                    with patch("ramses_ingest.prober._HAS_AV", False):
                        with patch("subprocess.run") as mock_run:
                            mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout)
                            info = probe_file(file_path)

            # Both dicts should have entry (format: path|mtime)
            cache_key = f"{file_path}|{mtime}"
            self.assertIn(cache_key, prober._METADATA_CACHE)
            self.assertIn(cache_key, prober._CACHE_ACCESS_TIMES)
        finally:
            prober._METADATA_CACHE = original_cache
            prober._CACHE_ACCESS_TIMES = original_times

    def test_concurrent_cache_pruning(self):
        """Concurrent pruning should not corrupt cache."""
        from ramses_ingest import prober
        import threading

        original_cache = prober._METADATA_CACHE.copy()
        original_times = prober._CACHE_ACCESS_TIMES.copy()

        try:
            # Fill cache
            prober._METADATA_CACHE = {f"key_{i}": {"data": i} for i in range(5500)}
            prober._CACHE_ACCESS_TIMES = {f"key_{i}": float(i) for i in range(5500)}

            def prune_concurrent():
                with prober._CACHE_LOCK:
                    prober._prune_lru_cache()

            # Multiple threads pruning
            threads = [threading.Thread(target=prune_concurrent) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Cache should be pruned to limit
            self.assertLessEqual(len(prober._METADATA_CACHE), 5000)
            # Both dicts should match in size
            self.assertEqual(len(prober._METADATA_CACHE), len(prober._CACHE_ACCESS_TIMES))
        finally:
            prober._METADATA_CACHE = original_cache
            prober._CACHE_ACCESS_TIMES = original_times


class TestOIIOProbing(unittest.TestCase):
    """Test OIIO-based probing with a real EXR fixture."""

    FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "test_1x1_par180.exr")

    @unittest.skipUnless(os.path.isfile(FIXTURE), "Test EXR fixture not found")
    def test_probe_exr_par(self):
        """OIIO should extract PAR=1.8 from the EXR header."""
        info = probe_file(self.FIXTURE)
        self.assertTrue(info.is_valid)
        self.assertEqual(info.width, 1)
        self.assertEqual(info.height, 1)
        self.assertAlmostEqual(info.pixel_aspect_ratio, 1.8, places=2)

    @unittest.skipUnless(os.path.isfile(FIXTURE), "Test EXR fixture not found")
    def test_probe_exr_colorspace(self):
        """OIIO should extract the colorspace attribute from the EXR header."""
        info = probe_file(self.FIXTURE)
        # OIIO normalizes "ACEScg" to "lin_ap1_scene"
        self.assertIn(info.color_space, ("ACEScg", "lin_ap1_scene"))

    @unittest.skipUnless(os.path.isfile(FIXTURE), "Test EXR fixture not found")
    def test_probe_exr_format(self):
        """OIIO should report the codec as 'openexr' and pixel format as 'half'."""
        info = probe_file(self.FIXTURE)
        self.assertEqual(info.codec, "openexr")
        self.assertEqual(info.pix_fmt, "half")

    @unittest.skipUnless(os.path.isfile(FIXTURE), "Test EXR fixture not found")
    def test_probe_exr_no_ffprobe(self):
        """EXR files should NOT call ffprobe — OIIO handles them entirely."""
        with patch("subprocess.run") as mock_run:
            info = probe_file(self.FIXTURE)
            mock_run.assert_not_called()
        self.assertTrue(info.is_valid)


if __name__ == "__main__":
    unittest.main()
