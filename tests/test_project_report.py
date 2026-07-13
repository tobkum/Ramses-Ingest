# -*- coding: utf-8 -*-
"""Tests for the whole-project ingest report (disk ground truth)."""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.project_report import (
    _parse_step_folder,
    _parse_version_folder,
    collect_ingested_versions,
    generate_project_report,
)
from ramses_ingest.prober import MediaInfo


def _write_version(step_dir: str, version_name: str, frames: list[int],
                   shot="SH010", step="PLATE", proj="TEST",
                   complete=True, sidecar=True, extra_meta=None,
                   lost_files=0) -> str:
    """Creates a published version folder with frames + Ingest sidecar."""
    vdir = os.path.join(step_dir, "_published", version_name)
    os.makedirs(vdir, exist_ok=True)
    meta = {}
    fnames = [f"{proj}_S_{shot}_{step}.{f:04d}.exr" for f in frames]
    for fname in fnames:
        with open(os.path.join(vdir, fname), "wb") as f:
            f.write(b"exr")
        entry = {
            "version": int(version_name.split("_")[0].lstrip("BGFG_") or 1)
            if version_name.split("_")[0].isdigit() else 1,
            "comment": "Ingested via Ramses-Ingest",
            "state": "wip",
            "date": int(time.time()),
            "md5": "d41d8cd98f00b204e9800998ecf8427e",
        }
        if extra_meta:
            entry.update(extra_meta)
        meta[fname] = entry
    # Files recorded at ingest but deleted since (integrity warning)
    for i in range(lost_files):
        meta[f"{proj}_S_{shot}_{step}.{9000 + i}.exr"] = dict(next(iter(meta.values())))
    if sidecar:
        with open(os.path.join(vdir, "_ramses_data.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
    if complete:
        with open(os.path.join(vdir, ".ramses_complete"), "w") as f:
            f.write(str(int(time.time())))
    return vdir


class TestParsing(unittest.TestCase):
    def test_parse_version_folder(self):
        self.assertEqual(_parse_version_folder("001_WIP"), ("", 1, "WIP"))
        self.assertEqual(_parse_version_folder("003"), ("", 3, ""))
        self.assertEqual(_parse_version_folder("BG_002_OK"), ("BG", 2, "OK"))
        self.assertEqual(_parse_version_folder("BG_CITY_001_OK"), ("BG_CITY", 1, "OK"))
        self.assertEqual(_parse_version_folder("not_a_version"), ("", 0, ""))

    def test_parse_step_folder(self):
        self.assertEqual(_parse_step_folder("TEST_S_SH010_PLATE"), ("TEST", "SH010", "PLATE"))
        self.assertEqual(_parse_step_folder("MY_S_PROJ_S_0957A_PLATE"), ("MY_S_PROJ", "0957A", "PLATE"))
        self.assertEqual(_parse_step_folder("garbage"), ("", "", ""))


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        from ramses.constants import FolderNames
        self.shots = os.path.join(self.tmp, FolderNames.shots)
        self.step_dir = os.path.join(self.shots, "TEST_S_SH010", "TEST_S_SH010_PLATE")
        os.makedirs(self.step_dir, exist_ok=True)

        # Probing real (fake) EXRs is pointless — return an empty MediaInfo.
        self._probe_patch = patch(
            "ramses_ingest.project_report.probe_file", return_value=MediaInfo()
        )
        self._probe_patch.start()
        self.addCleanup(self._probe_patch.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_only_ingested_versions(self):
        """Versions without the Ingest sidecar (foreign publishes) are excluded."""
        _write_version(self.step_dir, "001_WIP", [1001, 1002])
        _write_version(self.step_dir, "002_OK", [1001, 1002])
        _write_version(self.step_dir, "003_OK", [1001], sidecar=False)  # foreign

        results = collect_ingested_versions(self.tmp)
        self.assertEqual([r.plan.version for r in results], [1, 2])
        self.assertEqual(results[0].plan.shot_id, "SH010")
        self.assertEqual(results[0].plan.step_id, "PLATE")
        self.assertTrue(all(r.success for r in results))

    def test_frame_gap_detected_from_disk(self):
        _write_version(self.step_dir, "001_WIP", [1001, 1002, 1004])
        results = collect_ingested_versions(self.tmp)
        self.assertEqual(results[0].missing_frames, [1003])
        self.assertEqual(results[0].frames_copied, 3)

    def test_lost_files_produce_warning(self):
        """Files recorded at ingest but deleted since must be flagged."""
        _write_version(self.step_dir, "001_WIP", [1001, 1002], lost_files=2)
        results = collect_ingested_versions(self.tmp)
        self.assertTrue(any("missing on disk" in w for w in results[0].plan.warnings))

    def test_missing_completion_marker_produces_warning(self):
        _write_version(self.step_dir, "001_WIP", [1001], complete=False)
        results = collect_ingested_versions(self.tmp)
        self.assertTrue(any("completion marker" in w for w in results[0].plan.warnings))

    def test_provenance_fields_from_sidecar(self):
        _write_version(
            self.step_dir, "001_WIP", [1001],
            extra_meta={
                "source": "D:/tmp/DrNiceVFX/20260706/DNX_0195_10162503_v00",
                "sourceMedia": "DNX_0195_10162503_v00",
                "operator": "tobi",
                "verification": "fast",
            },
        )
        results = collect_ingested_versions(self.tmp)
        plan = results[0].plan
        self.assertEqual(plan.match.clip.base_name, "DNX_0195_10162503_v00")
        self.assertEqual(plan.ingest_operator, "tobi")
        self.assertEqual(plan.ingest_verification, "fast")
        self.assertTrue(plan.ingested_on)  # date rendered under the shot cell

    def test_resource_version_parsed(self):
        _write_version(self.step_dir, "BG_001_OK", [1001])
        results = collect_ingested_versions(self.tmp)
        self.assertEqual(results[0].plan.resource, "BG")
        self.assertEqual(results[0].plan.version, 1)

    def test_checksum_taken_from_sidecar(self):
        _write_version(self.step_dir, "001_WIP", [1001, 1002])
        results = collect_ingested_versions(self.tmp)
        self.assertEqual(results[0].checksum, "d41d8cd98f00b204e9800998ecf8427e")
        self.assertEqual(len(results[0].checksums), 2)


class TestGenerate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        from ramses.constants import FolderNames
        step_dir = os.path.join(self.tmp, FolderNames.shots, "TEST_S_SH010", "TEST_S_SH010_PLATE")
        os.makedirs(step_dir, exist_ok=True)
        _write_version(step_dir, "001_WIP", [1001, 1002],
                       extra_meta={"verification": "fast"})
        step_dir2 = os.path.join(self.tmp, FolderNames.shots, "TEST_S_SH020", "TEST_S_SH020_PLATE")
        os.makedirs(step_dir2, exist_ok=True)
        _write_version(step_dir2, "001_OK", [2001], shot="SH020",
                       extra_meta={"verification": "fast"})

        self._probe_patch = patch(
            "ramses_ingest.project_report.probe_file", return_value=MediaInfo()
        )
        self._probe_patch.start()
        self.addCleanup(self._probe_patch.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generates_html_and_json(self):
        out = os.path.join(self.tmp, "_ingest_reports")
        html_path, json_path = generate_project_report(
            self.tmp, out, project_id="TEST", operator="tobi"
        )
        self.assertTrue(html_path and os.path.isfile(html_path))
        self.assertTrue(json_path and os.path.isfile(json_path))

        with open(html_path, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("Project Ingest Report", html)
        self.assertIn("Report ID", html)
        self.assertIn("SH010", html)
        self.assertIn("SH020", html)
        self.assertIn("Ingested:", html)  # per-version date line
        # Uniform verification across versions -> badge shown
        self.assertIn("Fast (sampled MD5)", html)

        with open(json_path, encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["summary"]["total_clips"], 2)
        self.assertEqual(manifest["clips"][0]["shot_id"], "SH010")

    def test_empty_project_returns_none(self):
        empty = tempfile.mkdtemp()
        try:
            html_path, json_path = generate_project_report(empty, empty)
            self.assertIsNone(html_path)
            self.assertIsNone(json_path)
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class TestSidecarProvenance(unittest.TestCase):
    """The ingest-time sidecar now records provenance for the project report."""

    def test_write_metadata_includes_provenance(self):
        from ramses_ingest.publisher import _write_ramses_metadata
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, "a.exr"), "wb") as f:
                f.write(b"x")
            _write_ramses_metadata(
                tmp, 3, comment="c", state="OK",
                checksums={"a.exr": "abc"},
                source="D:/deliveries/day1",
                source_media="DNX_0195_10162503_v00",
                operator="tobi",
                verification="full",
            )
            with open(os.path.join(tmp, "_ramses_data.json"), encoding="utf-8") as f:
                data = json.load(f)
            entry = data["a.exr"]
            self.assertEqual(entry["source"], "D:/deliveries/day1")
            self.assertEqual(entry["sourceMedia"], "DNX_0195_10162503_v00")
            self.assertEqual(entry["operator"], "tobi")
            self.assertEqual(entry["verification"], "full")
            self.assertEqual(entry["md5"], "abc")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestHistoryLog(unittest.TestCase):
    """One line per clip in <project>/_deliveries/ingest_history.log."""

    def test_append_history_log(self):
        from pathlib import Path
        from ramses_ingest.app import IngestEngine
        from ramses_ingest.publisher import IngestPlan, IngestResult
        from ramses_ingest.matcher import MatchResult
        from ramses_ingest.scanner import Clip

        tmp = tempfile.mkdtemp()
        try:
            engine = IngestEngine()
            engine._project_path = tmp
            engine._operator_name = "tobi"

            clip = Clip("DNX_0195_10162503_v00", "exr", Path("D:/deliveries/day1"))
            plan = IngestPlan(
                match=MatchResult(clip=clip, shot_id="0195", matched=True),
                media_info=MediaInfo(),
                shot_id="0195", step_id="PLATE", version=1,
            )
            ok = IngestResult(plan=plan, success=True, frames_copied=104)
            fail = IngestResult(plan=plan, success=False, error="disk full")

            engine._append_history_log([ok, fail], "fast")

            log_path = os.path.join(tmp, "_deliveries", "ingest_history.log")
            with open(log_path, encoding="utf-8") as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("0195 PLATE v001", lines[0])
            self.assertIn("104 frames", lines[0])
            self.assertIn("OK", lines[0])
            self.assertIn("FAIL: disk full", lines[1])
            self.assertIn("tobi", lines[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
