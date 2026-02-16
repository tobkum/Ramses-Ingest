# -*- coding: utf-8 -*-
"""Tests for IngestEngine orchestration."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.app import IngestEngine
from ramses_ingest.publisher import IngestPlan, MatchResult
from ramses_ingest.prober import MediaInfo
from ramses_ingest.scanner import Clip

class TestIngestEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IngestEngine()
        # Mock connection as True with required project properties
        self.engine._connected = True
        self.engine._project_id = "TEST"
        self.engine._project_path = "/tmp/test_project"
        self.engine._project_fps = 24.0
        self.engine._project_width = 1920
        self.engine._project_height = 1080

    @patch("ramses_ingest.app.check_disk_space")
    @patch("ramses_ingest.app.register_ramses_objects")
    @patch("ramses_ingest.app.execute_plan")
    @patch("ramses_ingest.app.generate_html_report")
    def test_execute_two_phase_flow(self, mock_report, mock_exec, mock_reg, mock_disk):
        # Setup plans with all required fields for execution
        clip = Clip("shot", "mov", Path("/tmp"))
        clip.first_file = "/tmp/shot.mov"  # Ensure path is not empty for size calculation
        match = MatchResult(clip, matched=True, shot_id="SHOT", sequence_id="SEQ")
        plan = IngestPlan(
            match=match,
            media_info=MediaInfo(),
            sequence_id="SEQ",
            shot_id="SHOT",
            project_id="TEST",
            resource="", # HERO HIERARCHY FIX: Registration only happens if resource is empty
            target_publish_dir="/tmp/test_project/shots/SHOT/PLATE/_published/001_WIP"
        )

        mock_disk.return_value = (True, "")
        mock_exec.return_value = MagicMock(success=True, plan=plan, frames_copied=1, bytes_copied=1024)
        mock_report.return_value = True

        # Debug: verify plan is executable before calling execute
        self.assertTrue(plan.can_execute, f"Plan should be executable. Error: {plan.error}")

        results = self.engine.execute([plan])

        # Verify Registration (Phase 1) happened
        mock_reg.assert_called_once()
        
        # Verify Execution (Phase 2) happened with registration skipped
        mock_exec.assert_called_once()
        args, kwargs = mock_exec.call_args
        self.assertTrue(kwargs.get("skip_ramses_registration"))

        # Verify Report (Phase 4) happened
        mock_report.assert_called_once()

    def test_execute_aborts_on_disconnect(self):
        self.engine._connected = False
        results = self.engine.execute([])
        # Should return an empty list or error results if plans were provided
        self.assertEqual(len(results), 0)

if __name__ == "__main__":
    unittest.main()
