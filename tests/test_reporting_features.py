# -*- coding: utf-8 -*-
"""Tests for HTML report content: per-row errors/warnings, search/filter
toolbar, verification badge, escaping, and batched status field application."""

import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.publisher import IngestPlan, IngestResult, _apply_status_fields
from ramses_ingest.matcher import MatchResult
from ramses_ingest.prober import MediaInfo
from ramses_ingest.scanner import Clip
from ramses_ingest.reporting import generate_html_report


def _result(shot, ok=True, err="", warnings=None, missing=None, version=3):
    clip = Clip(
        base_name=f"{shot.lower()}_plate", extension="exr", directory=Path("/deliv"),
        is_sequence=True, frames=list(range(1001, 1097)),
    )
    clip.first_file = f"/deliv/{shot}.1001.exr"
    match = MatchResult(clip, matched=True, shot_id=shot, sequence_id="SEQ01")
    mi = MediaInfo(width=1920, height=1080, fps=24.0, codec="exr",
                   color_primaries="BT709", color_transfer="BT709")
    plan = IngestPlan(match=match, media_info=mi, sequence_id="SEQ01",
                      shot_id=shot, project_id="TEST", version=version)
    if warnings:
        plan.warnings = warnings
    res = IngestResult(plan=plan, success=ok, frames_copied=96,
                       bytes_copied=96 * 1024, checksum="abc123", error=err)
    if missing:
        res.missing_frames = missing
    return res


class TestHtmlReportFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "report.html")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _generate(self, results, **kwargs):
        self.assertTrue(generate_html_report(results, self.out, **kwargs))
        with open(self.out, encoding="utf-8") as f:
            return f.read()

    def test_failed_clip_shows_error_reason(self):
        """The failure reason must be readable in the report itself, not only
        in the JSON audit."""
        html = self._generate([_result("SH010", ok=False, err="Checksum mismatch: frame 1042")])
        self.assertIn("Checksum mismatch: frame 1042", html)
        self.assertIn('class="row-error"', html)

    def test_error_reason_is_escaped(self):
        html = self._generate([_result("SH010", ok=False, err="bad <script>x</script>")])
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_plan_warnings_are_shown(self):
        html = self._generate([_result("SH010", warnings=["COLORSPACE: Transfer mismatch"])])
        self.assertIn("COLORSPACE: Transfer mismatch", html)
        self.assertIn('class="row-warning"', html)

    def test_row_status_attributes_and_filter_toolbar(self):
        results = [
            _result("SH010"),                                   # ok
            _result("SH020", ok=False, err="Copy failed"),      # fail
            _result("SH030", missing=[1050]),                   # warn
        ]
        html = self._generate(results)
        self.assertIn('data-status="ok"', html)
        self.assertIn('data-status="fail"', html)
        self.assertIn('data-status="warn"', html)
        # Toolbar with live counts
        self.assertIn('id="clip-search"', html)
        self.assertIn("setFilter", html)
        self.assertIn("Failed <span class=\"filter-count\">(1)</span>", html)
        self.assertIn("Passed <span class=\"filter-count\">(1)</span>", html)

    def test_verification_badge(self):
        html = self._generate([_result("SH010")], verification="fast")
        self.assertIn("Fast (sampled MD5)", html)
        html = self._generate([_result("SH010")], verification="full")
        self.assertIn("Full (bit-perfect)", html)
        # Unknown/empty mode omits the badge rather than lying
        html = self._generate([_result("SH010")])
        self.assertNotIn("sampled MD5", html)


class TestApplyStatusFields(unittest.TestCase):
    """The batched status writer must set state, completion, version, and an
    ingest-provenance comment in a single setData round-trip."""

    def _run(self, status_name="OK", version=7, resource=""):
        res = _result("SH010", version=version)
        res.plan.resource = resource
        status = MagicMock()
        status.data.return_value = {"existing": "kept"}
        state = MagicMock()
        state.uuid.return_value = "state-uuid-ok"

        _apply_status_fields(status, state, res.plan, status_name)

        status.setData.assert_called_once()
        return status.setData.call_args[0][0]

    def test_all_fields_batched(self):
        data = self._run()
        self.assertEqual(data["state"], "state-uuid-ok")
        self.assertEqual(data["completionRatio"], 100)
        self.assertEqual(data["version"], 7)
        self.assertIn("Ingested v007", data["comment"])
        self.assertIn("via Ramses-Ingest", data["comment"])
        self.assertIn("/deliv", data["comment"])  # provenance: delivery folder
        self.assertIn("date", data)
        self.assertEqual(data["existing"], "kept")  # other keys preserved

    def test_wip_state_has_zero_completion(self):
        data = self._run(status_name="WIP")
        self.assertEqual(data["completionRatio"], 0)

    def test_resource_tag_in_comment(self):
        data = self._run(resource="BG")
        self.assertIn("[BG]", data["comment"])


if __name__ == "__main__":
    unittest.main()
