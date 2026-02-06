# -*- coding: utf-8 -*-
"""Tests for ramses_ingest.prober."""

import os
import sys
import unittest
import json
import subprocess
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.prober import probe_file, MediaInfo

class TestProber(unittest.TestCase):
    
    @patch("subprocess.run")
    def test_probe_success(self, mock_run):
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

    @patch("subprocess.run")
    def test_probe_timecode_in_format(self, mock_run):
        # Mock timecode in format tags instead of stream tags
        mock_stdout = json.dumps({
            "streams": [{
                "width": 2048,
                "height": 1080,
                "r_frame_rate": "23.976/1", # ffprobe can sometimes return this or "24000/1001"
                "tags": {}
            }],
            "format": {
                "tags": {"timecode": "02:15:10:05"}
            }
        })
        # Note: r_frame_rate split logic might fail on "23.976/1" if it's not "num/den"
        # but ffprobe usually does "24000/1001"
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout)
        
        info = probe_file("dummy.exr")
        self.assertEqual(info.start_timecode, "02:15:10:05")

    @patch("subprocess.run")
    def test_probe_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        info = probe_file("corrupt.mov")
        self.assertFalse(info.is_valid)

    @patch("subprocess.run")
    def test_ffprobe_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            probe_file("any.mov")

if __name__ == "__main__":
    unittest.main()
