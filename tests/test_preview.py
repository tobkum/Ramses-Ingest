# -*- coding: utf-8 -*-
"""Comprehensive tests for ramses_ingest.preview module.

Tests coverage:
    - generate_thumbnail(): subprocess validation, OCIO path escaping, Windows paths
    - generate_proxy(): sequence vs movie, ffmpeg command construction, timeout handling
    - _escape_ffmpeg_filter_path(): Windows backslash/colon escaping, Unix paths
    - Subprocess failures: missing ffmpeg, invalid paths, timeout scenarios
"""

import os
import sys
import unittest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.preview import (
    generate_thumbnail,
    generate_proxy,
    _bake_lut_from_ocio,
    _color_transform_filter,
    _escape_ffmpeg_filter_path,
    THUMB_WIDTH,
    PROXY_WIDTH,
)

try:
    import PyOpenColorIO  # noqa: F401
    HAS_PYOCIO = True
except ImportError:
    HAS_PYOCIO = False
from ramses_ingest.scanner import Clip
from ramses_ingest.prober import MediaInfo


class TestEscapeFFmpegFilterPath(unittest.TestCase):
    """Test FFmpeg filter path escaping."""

    def test_windows_drive_letter_preserved(self):
        """Windows drive letters (C:, D:) should not be escaped."""
        result = _escape_ffmpeg_filter_path("C:\\OCIO\\config.ocio")
        self.assertEqual(result, "C:/OCIO/config.ocio")
        # Colon after C should not be escaped

    def test_windows_backslashes_converted(self):
        """Backslashes should be converted to forward slashes."""
        result = _escape_ffmpeg_filter_path("C:\\Users\\VFX\\config.ocio")
        self.assertEqual(result, "C:/Users/VFX/config.ocio")

    def test_unix_path_unchanged(self):
        """Unix paths without special chars should pass through."""
        result = _escape_ffmpeg_filter_path("/usr/local/ocio/config.ocio")
        self.assertEqual(result, "/usr/local/ocio/config.ocio")

    def test_unix_path_with_colon_escaped(self):
        """Colons in Unix paths (not drive letters) should be escaped."""
        result = _escape_ffmpeg_filter_path("/mnt/ocio:v2/config.ocio")
        self.assertEqual(result, "/mnt/ocio\\:v2/config.ocio")

    def test_unc_path_converted(self):
        """UNC paths (\\\\server\\share) should be converted."""
        result = _escape_ffmpeg_filter_path("\\\\server\\share\\ocio\\config.ocio")
        self.assertEqual(result, "//server/share/ocio/config.ocio")

    def test_d_drive_preserved(self):
        """D: drive should not have colon escaped."""
        result = _escape_ffmpeg_filter_path("D:\\VFX\\config.ocio")
        self.assertEqual(result, "D:/VFX/config.ocio")

    def test_multiple_colons_windows(self):
        """Windows path with folder name containing colon."""
        result = _escape_ffmpeg_filter_path("C:\\ocio:v2\\config.ocio")
        # C: preserved, but :v2 escaped
        self.assertEqual(result, "C:/ocio\\:v2/config.ocio")

    def test_empty_path(self):
        """Empty path should return empty."""
        result = _escape_ffmpeg_filter_path("")
        self.assertEqual(result, "")

    def test_relative_path_with_colon(self):
        """Relative paths with colons should escape them."""
        result = _escape_ffmpeg_filter_path("folder:v2/config.ocio")
        self.assertEqual(result, "folder\\:v2/config.ocio")


class TestGenerateThumbnail(unittest.TestCase):
    """Test thumbnail generation."""

    def setUp(self):
        """Create temp directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(self.source_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_sequence_clip(self, frame_count=10):
        """Helper to create a sequence clip."""
        frames = list(range(1, frame_count + 1))
        for f in frames:
            path = os.path.join(self.source_dir, f"test.{f:04d}.exr")
            Path(path).touch()

        return Clip(
            base_name="test",
            extension="exr",
            directory=Path(self.source_dir),
            is_sequence=True,
            frames=frames,
            first_file=os.path.join(self.source_dir, "test.0001.exr"),
        )

    def _make_movie_clip(self):
        """Helper to create a movie clip."""
        movie_path = os.path.join(self.source_dir, "test.mov")
        Path(movie_path).touch()

        return Clip(
            base_name="test",
            extension="mov",
            directory=Path(self.source_dir),
            is_sequence=False,
            frames=[],
            first_file=movie_path,
        )

    @patch("subprocess.run")
    @patch("os.path.isfile")
    def test_sequence_default_middle_frame(self, mock_isfile, mock_run):
        """Default frame_index should pick middle frame."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_isfile.return_value = True  # Pretend source files exist
        clip = self._make_sequence_clip(frame_count=10)
        output = os.path.join(self.output_dir, "thumb.jpg")

        result = generate_thumbnail(clip, output)

        self.assertTrue(result)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        # Should use frame 6 (index 5, middle of frames 1-10)
        # len(frames) // 2 = 10 // 2 = 5, frames[5] = 6
        self.assertIn("test.0006.exr", " ".join(cmd))

    @patch("subprocess.run")
    def test_sequence_specific_frame_index(self, mock_run):
        """Specific frame_index should be used."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_sequence_clip(frame_count=10)
        output = os.path.join(self.output_dir, "thumb.jpg")

        result = generate_thumbnail(clip, output, frame_index=2)

        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        # Should use frame 3 (index 2 of frames 1-10)
        self.assertIn("test.0003.exr", " ".join(cmd))

    @patch("subprocess.run")
    def test_sequence_frame_index_clamped(self, mock_run):
        """Frame index out of bounds should be clamped."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_sequence_clip(frame_count=5)
        output = os.path.join(self.output_dir, "thumb.jpg")

        # Request index 100 (out of bounds)
        result = generate_thumbnail(clip, output, frame_index=100)

        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        # Should use last frame (index 4 = frame 5)
        self.assertIn("test.0005.exr", " ".join(cmd))

    @patch("subprocess.run")
    def test_thumbnail_command_structure(self, mock_run):
        """Verify ffmpeg command structure."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_sequence_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")

        generate_thumbnail(clip, output)

        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-y", cmd)  # Overwrite
        self.assertIn("-i", cmd)
        self.assertIn("-vf", cmd)  # Video filter
        self.assertIn("-frames:v", cmd)
        self.assertIn("1", cmd)  # Single frame
        self.assertIn("-q:v", cmd)  # Quality
        self.assertEqual(cmd[-1], output)  # Output path

    @patch("subprocess.run")
    def test_thumbnail_with_ocio(self, mock_run):
        """OCIO config should be included in filter chain (no LUT present)."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_sequence_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")
        # Real config file; empty LUT folder so the ocio branch is exercised
        ocio_path = os.path.join(self.output_dir, "config.ocio")
        with open(ocio_path, "w") as f:
            f.write("ocio_profile_version: 2\n")

        with patch(
            "ramses_ingest.preview._luts_dir",
            return_value=os.path.join(self.output_dir, "no_luts"),
        ), patch("ramses_ingest.preview._bake_lut_from_ocio", return_value=False):
            result = generate_thumbnail(clip, output, ocio_config=ocio_path, ocio_in="ACEScg")

        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        vf_index = cmd.index("-vf")
        vf_value = cmd[vf_index + 1]

        self.assertIn("ocio=", vf_value)
        self.assertIn("input=ACEScg", vf_value)
        self.assertIn("sRGB", vf_value)
        # Path should be escaped/normalized
        self.assertIn("config.ocio", vf_value)

    @patch("subprocess.run")
    def test_thumbnail_scale_filter(self, mock_run):
        """Scale filter should use THUMB_WIDTH."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_sequence_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")

        generate_thumbnail(clip, output)

        cmd = mock_run.call_args[0][0]
        vf_index = cmd.index("-vf")
        vf_value = cmd[vf_index + 1]

        self.assertIn(f"scale={THUMB_WIDTH}:-1", vf_value)

    @patch("subprocess.run")
    def test_thumbnail_timeout(self, mock_run):
        """Subprocess timeout should be 90 seconds."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_sequence_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")

        generate_thumbnail(clip, output)

        kwargs = mock_run.call_args[1]
        self.assertEqual(kwargs["timeout"], 90)

    @patch("subprocess.run")
    def test_ffmpeg_failure_returns_false(self, mock_run):
        """FFmpeg non-zero return code should return False."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Error")
        clip = self._make_sequence_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")

        result = generate_thumbnail(clip, output)

        self.assertFalse(result)

    @patch("subprocess.run")
    def test_ffmpeg_not_found_returns_false(self, mock_run):
        """Missing ffmpeg should return False."""
        mock_run.side_effect = FileNotFoundError
        clip = self._make_sequence_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")

        result = generate_thumbnail(clip, output)

        self.assertFalse(result)

    @patch("subprocess.run")
    def test_timeout_returns_false(self, mock_run):
        """Subprocess timeout should return False."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=90)
        clip = self._make_sequence_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")

        result = generate_thumbnail(clip, output)

        self.assertFalse(result)

    @patch("subprocess.run")
    @patch("ramses_ingest.prober.probe_file")
    def test_movie_default_40_percent(self, mock_probe, mock_run):
        """Movie should seek to 40% by default."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_probe.return_value = MediaInfo(duration_seconds=100.0)

        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")

        result = generate_thumbnail(clip, output)

        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        ss_index = cmd.index("-ss")
        seek_value = float(cmd[ss_index + 1])
        self.assertAlmostEqual(seek_value, 40.0, places=1)  # 40% of 100s

    @patch("subprocess.run")
    def test_movie_specific_frame_index_as_seconds(self, mock_run):
        """Movie with frame_index should use it as seek seconds."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")

        result = generate_thumbnail(clip, output, frame_index=25)

        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        ss_index = cmd.index("-ss")
        self.assertEqual(cmd[ss_index + 1], "25")

    @patch("subprocess.run")
    @patch("ramses_ingest.prober.probe_file")
    def test_movie_probe_failure_defaults_to_zero(self, mock_probe, mock_run):
        """Probe failure should default to 0 seconds."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_probe.side_effect = Exception("Probe failed")

        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "thumb.jpg")

        result = generate_thumbnail(clip, output)

        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        ss_index = cmd.index("-ss")
        self.assertEqual(cmd[ss_index + 1], "0")

    def test_output_directory_created(self):
        """Output directory should be created if it doesn't exist."""
        clip = self._make_sequence_clip()
        nested_output = os.path.join(self.output_dir, "nested", "deep", "thumb.jpg")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            generate_thumbnail(clip, nested_output)

        self.assertTrue(os.path.isdir(os.path.dirname(nested_output)))


class TestGenerateProxy(unittest.TestCase):
    """Test proxy generation."""

    def setUp(self):
        """Create temp directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_dir, "source")
        self.output_dir = os.path.join(self.temp_dir, "output")
        os.makedirs(self.source_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_sequence_clip(self):
        """Helper to create a sequence clip."""
        frames = list(range(1, 11))
        for f in frames:
            path = os.path.join(self.source_dir, f"test.{f:04d}.exr")
            Path(path).touch()

        return Clip(
            base_name="test",
            extension="exr",
            directory=Path(self.source_dir),
            is_sequence=True,
            frames=frames,
            first_file=os.path.join(self.source_dir, "test.0001.exr"),
            _padding=4,
        )

    def _make_movie_clip(self):
        """Helper to create a movie clip."""
        movie_path = os.path.join(self.source_dir, "test.mov")
        Path(movie_path).touch()

        return Clip(
            base_name="test",
            extension="mov",
            directory=Path(self.source_dir),
            is_sequence=False,
            frames=[],
            first_file=movie_path,
        )

    @patch("subprocess.run")
    def test_sequence_uses_pattern_input(self, mock_run):
        """Sequence should use -start_number and frame pattern."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_sequence_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        result = generate_proxy(clip, output)

        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        self.assertIn("-start_number", cmd)
        self.assertIn("1", cmd)
        # Should have pattern like test.%04d.exr
        input_pattern = [c for c in cmd if "%04d" in c]
        self.assertTrue(len(input_pattern) > 0)

    @patch("subprocess.run")
    def test_movie_uses_direct_input(self, mock_run):
        """Movie should use direct file input."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        result = generate_proxy(clip, output)

        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        self.assertNotIn("-start_number", cmd)
        self.assertIn(clip.first_file, cmd)

    @patch("subprocess.run")
    def test_proxy_h264_encoding(self, mock_run):
        """Proxy should use libx264 codec."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        generate_proxy(clip, output)

        cmd = mock_run.call_args[0][0]
        self.assertIn("-c:v", cmd)
        self.assertIn("libx264", cmd)

    @patch("subprocess.run")
    def test_proxy_crf_quality(self, mock_run):
        """Proxy should use CRF encoding."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        generate_proxy(clip, output)

        cmd = mock_run.call_args[0][0]
        self.assertIn("-crf", cmd)
        crf_index = cmd.index("-crf")
        # CRF should be numeric
        self.assertTrue(cmd[crf_index + 1].isdigit())

    @patch("subprocess.run")
    def test_proxy_yuv420p_pixel_format(self, mock_run):
        """Proxy should use yuv420p for compatibility."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        generate_proxy(clip, output)

        cmd = mock_run.call_args[0][0]
        self.assertIn("-pix_fmt", cmd)
        self.assertIn("yuv420p", cmd)

    @patch("subprocess.run")
    def test_proxy_scale_filter(self, mock_run):
        """Proxy should scale to PROXY_WIDTH."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        generate_proxy(clip, output)

        cmd = mock_run.call_args[0][0]
        vf_index = cmd.index("-vf")
        vf_value = cmd[vf_index + 1]
        self.assertIn(f"scale={PROXY_WIDTH}:-2", vf_value)

    @patch("subprocess.run")
    def test_proxy_with_ocio(self, mock_run):
        """Proxy with OCIO should include filter (no LUT present)."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")
        ocio_path = os.path.join(self.output_dir, "config.ocio")
        with open(ocio_path, "w") as f:
            f.write("ocio_profile_version: 2\n")

        with patch(
            "ramses_ingest.preview._luts_dir",
            return_value=os.path.join(self.output_dir, "no_luts"),
        ), patch("ramses_ingest.preview._bake_lut_from_ocio", return_value=False):
            result = generate_proxy(clip, output, ocio_config=ocio_path, ocio_in="Linear")

        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        vf_index = cmd.index("-vf")
        vf_value = cmd[vf_index + 1]
        self.assertIn("ocio=", vf_value)
        self.assertIn("input=Linear", vf_value)
        self.assertIn("config.ocio", vf_value)

    @patch("subprocess.run")
    def test_proxy_timeout_600_seconds(self, mock_run):
        """Proxy should have 600 second timeout."""
        mock_run.return_value = MagicMock(returncode=0)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        generate_proxy(clip, output)

        kwargs = mock_run.call_args[1]
        self.assertEqual(kwargs["timeout"], 600)

    @patch("subprocess.run")
    def test_proxy_failure_returns_false(self, mock_run):
        """FFmpeg failure should return False."""
        mock_run.return_value = MagicMock(returncode=1)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        result = generate_proxy(clip, output)

        self.assertFalse(result)

    @patch("subprocess.run")
    def test_proxy_timeout_returns_false(self, mock_run):
        """Timeout should return False."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=600)
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        result = generate_proxy(clip, output)

        self.assertFalse(result)

    @patch("subprocess.run")
    def test_proxy_missing_ffmpeg_returns_false(self, mock_run):
        """Missing ffmpeg should return False."""
        mock_run.side_effect = FileNotFoundError
        clip = self._make_movie_clip()
        output = os.path.join(self.output_dir, "proxy.mp4")

        result = generate_proxy(clip, output)

        self.assertFalse(result)

    def test_invalid_clip_returns_false(self):
        """Invalid clip (no first_file) should return False."""
        clip = Clip(
            base_name="test",
            extension="exr",
            directory=Path(self.source_dir),
            is_sequence=True,
            frames=[],
            first_file="",
        )
        output = os.path.join(self.output_dir, "proxy.mp4")

        result = generate_proxy(clip, output)

        self.assertFalse(result)

    def test_nonexistent_source_returns_false(self):
        """Nonexistent source file should return False."""
        clip = Clip(
            base_name="test",
            extension="mov",
            directory=Path(self.source_dir),
            is_sequence=False,
            frames=[],
            first_file="/nonexistent/file.mov",
        )
        output = os.path.join(self.output_dir, "proxy.mp4")

        result = generate_proxy(clip, output)

        self.assertFalse(result)

    def test_output_directory_created(self):
        """Output directory should be created."""
        clip = self._make_movie_clip()
        nested_output = os.path.join(self.output_dir, "deep", "nested", "proxy.mp4")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            generate_proxy(clip, nested_output)

        self.assertTrue(os.path.isdir(os.path.dirname(nested_output)))


class TestColorTransformFilter(unittest.TestCase):
    """Preview color conversion: LUT first (works on every ffmpeg build),
    ffmpeg `ocio` filter second (needs FFmpeg >= 8.1 built with OCIO)."""

    def setUp(self):
        import shutil
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.luts = os.path.join(self.tmp, "luts")
        os.makedirs(self.luts, exist_ok=True)
        self._luts_patch = patch(
            "ramses_ingest.preview._luts_dir", return_value=self.luts
        )
        self._luts_patch.start()
        self.addCleanup(self._luts_patch.stop)
        # Auto-baking is exercised by dedicated tests; disabled by default so
        # the priority tests stay deterministic without PyOpenColorIO.
        self._bake_patch = patch(
            "ramses_ingest.preview._bake_lut_from_ocio", return_value=False
        )
        self.mock_bake = self._bake_patch.start()
        self.addCleanup(self._bake_patch.stop)

    def _make_lut(self, name):
        path = os.path.join(self.luts, name)
        with open(path, "w") as f:
            f.write("LUT_3D_SIZE 2\n")
        return path

    def _make_config(self):
        path = os.path.join(self.tmp, "config.ocio")
        with open(path, "w") as f:
            f.write("ocio_profile_version: 2\n")
        return path

    def test_lut_wins_even_when_ocio_config_present(self):
        self._make_lut("ARRI LogC4.cube")
        cfg = self._make_config()
        flt = _color_transform_filter(cfg, "ARRI LogC4")
        self.assertTrue(flt.startswith("lut3d="))
        self.assertIn("ARRI LogC4.cube", flt)

    def test_ocio_filter_uses_correct_option_names(self):
        """The filter options are input/display/view — in_label/out_label
        do not exist and made the filter fail on OCIO-enabled builds too."""
        cfg = self._make_config()
        flt = _color_transform_filter(cfg, "ARRI LogC4")
        self.assertIn("ocio=config=", flt)
        self.assertIn(":input=ARRI LogC4", flt)
        self.assertIn(":display=sRGB - Display", flt)
        self.assertIn(":view=ACES 1.0 - SDR Video", flt)
        self.assertNotIn("in_label", flt)
        self.assertNotIn("out_label", flt)

    def test_no_lut_no_config_returns_none(self):
        """Nothing available (manual LUT absent, bake failed, no config)."""
        self.assertIsNone(_color_transform_filter(None, "ARRI LogC4"))
        self.assertIsNone(_color_transform_filter("/nonexistent.ocio", "sRGB"))

    def test_auto_baked_lut_used_and_cached(self):
        """A baked LUT lands in luts/_auto and is reused without re-baking."""
        def fake_bake(ocio_in, out_path, ocio_config=None):
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w") as f:
                f.write("LUT_3D_SIZE 2\n")
            return True

        self.mock_bake.side_effect = fake_bake
        flt = _color_transform_filter(None, "ARRI LogC4")
        self.assertTrue(flt.startswith("lut3d="))
        self.assertIn("_auto", flt)

        flt2 = _color_transform_filter(None, "ARRI LogC4")
        self.assertEqual(flt, flt2)
        self.assertEqual(self.mock_bake.call_count, 1)  # cache hit, no re-bake

    def test_manual_lut_preferred_over_auto_bake(self):
        self._make_lut("ARRI LogC4.cube")
        flt = _color_transform_filter(None, "ARRI LogC4")
        self.assertNotIn("_auto", flt)
        self.mock_bake.assert_not_called()

    def test_colorspace_name_sanitized_for_lut_lookup(self):
        """Slashes/colons in colorspace names map to underscores."""
        self._make_lut("Input _ ARRI _ LogC4.cube")
        flt = _color_transform_filter(None, "Input / ARRI / LogC4")
        self.assertTrue(flt and flt.startswith("lut3d="))

    def test_thumbnail_command_includes_lut(self):
        """End to end: the LUT lands in the ffmpeg -vf chain."""
        self._make_lut("ARRI LogC4.cube")
        src = os.path.join(self.tmp, "plate.0001.exr")
        with open(src, "wb") as f:
            f.write(b"x")
        clip = Clip(
            base_name="plate", extension="exr", directory=Path(self.tmp),
            is_sequence=True, frames=[1], first_file=src,
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            generate_thumbnail(
                clip, os.path.join(self.tmp, "out.jpg"), ocio_in="ARRI LogC4"
            )
        cmd = mock_run.call_args[0][0]
        vf = cmd[cmd.index("-vf") + 1]
        self.assertIn("lut3d=", vf)


@unittest.skipUnless(HAS_PYOCIO, "PyOpenColorIO not installed")
class TestRealOcioBake(unittest.TestCase):
    """Real bakes against the pinned builtin ACES Studio config — proves the
    whole no-vendoring premise (config compiled into the wheel)."""

    def setUp(self):
        import shutil
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _bake(self, colorspace):
        out = os.path.join(self.tmp, "out.cube")
        ok = _bake_lut_from_ocio(colorspace, out)
        return ok, out

    def test_bakes_logc4_display_lut(self):
        ok, out = self._bake("ARRI LogC4")
        self.assertTrue(ok)
        with open(out, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("LUT_3D_SIZE", content)

    def test_legacy_dropdown_names_resolve_via_alias_map(self):
        for name in ("sRGB", "LogC", "S-Log3", "Rec.709", "Gamma 2.4"):
            ok, _ = self._bake(name)
            self.assertTrue(ok, f"{name!r} must bake via the alias map")

    def test_every_dropdown_entry_bakes(self):
        """Completeness guarantee: every colorspace offered in the UI must
        bake against the pinned builtin config — except the documented
        manual-LUT-only entries. Adding a dropdown entry without a working
        transform fails here."""
        from ramses_ingest.preview import (
            MANUAL_LUT_ONLY_COLORSPACES,
            STANDARD_COLORSPACES,
        )
        failures = []
        for name in STANDARD_COLORSPACES:
            if name in MANUAL_LUT_ONLY_COLORSPACES:
                continue
            out = os.path.join(self.tmp, "entry.cube")
            if not _bake_lut_from_ocio(name, out):
                failures.append(name)
        self.assertEqual(failures, [], f"Dropdown entries that do not bake: {failures}")

    def test_manual_only_entries_are_documented_not_bakeable(self):
        from ramses_ingest.preview import MANUAL_LUT_ONLY_COLORSPACES
        for name in MANUAL_LUT_ONLY_COLORSPACES:
            out = os.path.join(self.tmp, "manual.cube")
            self.assertFalse(
                _bake_lut_from_ocio(name, out),
                f"{name!r} bakes now — remove it from MANUAL_LUT_ONLY_COLORSPACES",
            )

    def test_scene_linear_input_bakes(self):
        """ACEScg is scene-linear — bakes with the documented [0,1] domain
        limitation (highlights above 1.0 clip in previews)."""
        ok, _ = self._bake("ACEScg")
        self.assertTrue(ok)

    def test_unknown_colorspace_returns_false(self):
        ok, _ = self._bake("Totally Made Up Space")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
