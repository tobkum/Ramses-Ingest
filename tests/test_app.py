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

    def _make_plan(self, shot="SHOT", seq="SEQ", tmp="/tmp", media_info=None, resource=""):
        clip = Clip("shot", "mov", Path(tmp))
        clip.first_file = os.path.join(tmp, "shot.mov")
        match = MatchResult(clip, matched=True, shot_id=shot, sequence_id=seq)
        return IngestPlan(
            match=match,
            media_info=media_info or MediaInfo(),
            sequence_id=seq,
            shot_id=shot,
            project_id="TEST",
            resource=resource,
            target_publish_dir=f"/tmp/test_project/shots/{shot}/PLATE/_published/001_WIP",
        )

    @patch("ramses_ingest.app.check_disk_space")
    @patch("ramses_ingest.app.register_ramses_objects")
    @patch("ramses_ingest.app.execute_plan")
    @patch("ramses_ingest.app.generate_html_report")
    def test_registration_happens_after_transfer(self, mock_report, mock_exec, mock_reg, mock_disk):
        """DB registration must run AFTER the file transfer (zombie prevention):
        a failed copy leaves nothing behind in the database."""
        plan = self._make_plan()
        mock_disk.return_value = (True, "")
        mock_report.return_value = True

        call_order = []
        mock_exec.side_effect = lambda p, **kw: (
            call_order.append("transfer"),
            MagicMock(success=True, plan=p, frames_copied=1, bytes_copied=1024),
        )[1]
        mock_reg.side_effect = lambda *a, **kw: call_order.append("register")

        self.engine.execute([plan])

        self.assertEqual(call_order, ["transfer", "register"])

    @patch("ramses_ingest.app.check_disk_space")
    @patch("ramses_ingest.app.register_ramses_objects")
    @patch("ramses_ingest.app.execute_plan")
    @patch("ramses_ingest.app.generate_html_report")
    def test_no_registration_for_failed_transfer(self, mock_report, mock_exec, mock_reg, mock_disk):
        """A failed/rolled-back transfer must NOT create DB objects."""
        plan = self._make_plan()
        mock_disk.return_value = (True, "")
        mock_report.return_value = True
        mock_exec.return_value = MagicMock(
            success=False, plan=plan, frames_copied=0, bytes_copied=0, error="Copy failed"
        )

        results = self.engine.execute([plan])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        mock_reg.assert_not_called()

    @patch("ramses_ingest.app.check_disk_space")
    @patch("ramses_ingest.app.update_ramses_status")
    @patch("ramses_ingest.app.register_ramses_objects")
    @patch("ramses_ingest.app.execute_plan")
    @patch("ramses_ingest.app.generate_html_report")
    def test_registration_deduplicated_per_shot(self, mock_report, mock_exec, mock_reg, mock_status, mock_disk):
        """Multiple successful clips for the same shot/sequence register once."""
        hero = self._make_plan()
        aux = self._make_plan(resource="BG")
        aux.target_publish_dir = "/tmp/test_project/shots/SHOT/PLATE/_published/BG_001_WIP"
        mock_disk.return_value = (True, "")
        mock_report.return_value = True
        mock_exec.side_effect = lambda p, **kw: MagicMock(
            success=True, plan=p, frames_copied=1, bytes_copied=1024
        )

        self.engine.execute([hero, aux])

        mock_reg.assert_called_once()

    def test_colorspace_warning_does_not_block_execution(self):
        """Warning-severity colorspace issues (mixed transfer functions, same
        primaries) go to plan.warnings and must NOT block execution."""
        from ramses_ingest.app import apply_colorspace_validation

        mi_a = MediaInfo(width=1920, height=1080, color_primaries="BT709", color_transfer="BT709")
        mi_b = MediaInfo(width=1920, height=1080, color_primaries="BT709", color_transfer="SRGB")
        plan_a = self._make_plan(shot="SH010", media_info=mi_a)
        plan_b = self._make_plan(shot="SH020", media_info=mi_b)

        apply_colorspace_validation([plan_a, plan_b])

        self.assertTrue(plan_a.warnings, "Expected a transfer-mismatch warning")
        self.assertTrue(plan_b.warnings, "Expected a transfer-mismatch warning")
        self.assertEqual(plan_a.error, "")
        self.assertEqual(plan_b.error, "")
        self.assertTrue(plan_a.can_execute)
        self.assertTrue(plan_b.can_execute)

    def test_colorspace_critical_blocks_execution(self):
        """Critical colorspace issues (mixed primaries) block via plan.error."""
        from ramses_ingest.app import apply_colorspace_validation

        plans = [
            self._make_plan(shot=f"SH{i:03d}", media_info=MediaInfo(
                width=1920, height=1080, color_primaries=prim, color_transfer="BT709"
            ))
            for i, prim in enumerate(["BT709", "BT709", "BT2020"])
        ]

        apply_colorspace_validation(plans)

        outlier = plans[2]
        self.assertIn("COLORSPACE", outlier.error)
        self.assertFalse(outlier.can_execute)
        # The majority plans stay executable
        self.assertTrue(plans[0].can_execute)
        self.assertTrue(plans[1].can_execute)

    def test_execute_aborts_on_disconnect(self):
        """execute() with a real plan while disconnected must return a failed result, not silently drop it."""
        import tempfile, shutil
        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(tmp, "shot.mov")
            open(src, "wb").close()
            clip = Clip("shot", "mov", Path(tmp),
                        is_sequence=False, frames=[], first_file=src)
            match = MatchResult(clip, matched=True, shot_id="SH010", sequence_id="SEQ")
            plan = IngestPlan(
                match=match, media_info=MediaInfo(),
                sequence_id="SEQ", shot_id="SH010", project_id="TEST",
                target_publish_dir=os.path.join(tmp, "pub")
            )
            self.engine._connected = False
            results = self.engine.execute([plan])
            # When disconnected, execute must return one failed result per plan
            # (not silently drop plans or raise an exception)
            self.assertEqual(len(results), 1)
            self.assertFalse(results[0].success)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
