# -*- coding: utf-8 -*-
"""Integration and high-level feature tests."""

import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.matcher import EDLMapper
from ramses_ingest.reporting import generate_html_report
from ramses_ingest.publisher import IngestResult, IngestPlan, MatchResult
from ramses_ingest.prober import MediaInfo
from ramses_ingest.scanner import Clip

class TestEDLMapper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.edl')
        self.tmp.write("001  SHOT010  V     C        00:00:00:00 00:00:01:00 01:00:00:00 01:00:01:00\n")
        self.tmp.write("* FROM CLIP NAME:  CLIP_A_001\n")
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_edl_mapping(self):
        mapper = EDLMapper(self.tmp.name)
        self.assertEqual(mapper.get_shot_id("CLIP_A_001"), "CLIP_A_001")
        self.assertIsNone(mapper.get_shot_id("UNKNOWN"))

class TestReporting(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generate_report(self):
        clip = Clip("test", "exr", Path("/tmp"))
        plan = IngestPlan(MatchResult(clip), MediaInfo(), "SEQ", "SHOT")
        res = IngestResult(plan, success=True, published_path="/path/to/pub", frames_copied=24)
        
        report_path = os.path.join(self.tmpdir, "report.html")
        ok = generate_html_report([res], report_path)
        
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(report_path))
        with open(report_path, "r") as f:
            content = f.read()
            self.assertIn("SHOT", content)
            self.assertIn("PASSED", content)

if __name__ == "__main__":
    unittest.main()
