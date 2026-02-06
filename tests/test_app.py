# -*- coding: utf-8 -*-
"""Tests for IngestEngine orchestration."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.app import IngestEngine
from ramses_ingest.publisher import IngestPlan, MatchResult
from ramses_ingest.prober import MediaInfo
from ramses_ingest.scanner import Clip

class TestIngestEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IngestEngine()
        # Mock connection as True
        self.engine._connected = True
        self.engine._project_id = "TEST"
        self.engine._project_path = "/tmp/test_project"

    @patch("ramses_ingest.app.register_ramses_objects")
    @patch("ramses_ingest.app.execute_plan")
    @patch("ramses_ingest.reporting.generate_html_report")
    def test_execute_two_phase_flow(self, mock_report, mock_exec, mock_reg):
        # Setup plans
        clip = Clip("shot", "mov", Path("/tmp"))
        plan = IngestPlan(MatchResult(clip, matched=True), MediaInfo(), "SEQ", "SHOT")
        
        mock_exec.return_value = MagicMock(success=True, plan=plan)
        mock_report.return_value = True

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
