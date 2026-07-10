# -*- coding: utf-8 -*-
"""GUI regression tests for the plan table (offscreen Qt).

Covers the sorting-desync fix: the enable checkbox (column 0) and the status
dot (column 11) are now table *items*, which travel with their rows when the
user sorts. The previous cell-widget implementation stayed at fixed physical
rows, so after sorting a skipped plan could show a checked box (and toggles
could hit the wrong plan's visual state).
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:
    HAS_QT = False

from ramses_ingest.publisher import IngestPlan
from ramses_ingest.matcher import MatchResult
from ramses_ingest.prober import MediaInfo
from ramses_ingest.scanner import Clip


def _make_plan(shot: str, enabled: bool = True) -> IngestPlan:
    clip = Clip(base_name=shot.lower(), extension="mov", directory=Path("/tmp"))
    clip.first_file = f"/tmp/{shot.lower()}.mov"
    match = MatchResult(clip=clip, matched=True, shot_id=shot, sequence_id="SEQ")
    plan = IngestPlan(
        match=match,
        media_info=MediaInfo(),
        sequence_id="SEQ",
        shot_id=shot,
        project_id="TEST",
        target_publish_dir=f"/tmp/pub/{shot}/001_WIP",
    )
    plan.enabled = enabled
    return plan


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestPlanTableSorting(unittest.TestCase):
    """The checkbox and status columns must survive user sorting."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from ramses_ingest.gui import IngestWindow
        self.window = IngestWindow()
        self.plans = [
            _make_plan("SH010", enabled=True),
            _make_plan("SH020", enabled=False),
            _make_plan("SH030", enabled=True),
        ]
        self.window._plans = self.plans
        self.window._populate_table()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def _row_of_shot(self, shot: str) -> int:
        table = self.window._table
        for row in range(table.rowCount()):
            if table.item(row, 3).text() == shot:
                return row
        raise AssertionError(f"Shot {shot} not found in table")

    def test_checkbox_items_reflect_plan_state(self):
        table = self.window._table
        for shot, enabled in (("SH010", True), ("SH020", False), ("SH030", True)):
            row = self._row_of_shot(shot)
            item = table.item(row, 0)
            self.assertTrue(item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
            expected = Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked
            self.assertEqual(item.checkState(), expected, shot)

    def test_checkstates_follow_rows_after_sorting(self):
        """After sorting by Shot descending, the unchecked plan (SH020) must
        still display unchecked in whichever row it landed."""
        table = self.window._table
        table.sortItems(3, Qt.SortOrder.DescendingOrder)

        # Row order is now SH030, SH020, SH010
        self.assertEqual(table.item(0, 3).text(), "SH030")
        self.assertEqual(table.item(1, 3).text(), "SH020")
        self.assertEqual(table.item(2, 3).text(), "SH010")

        self.assertEqual(table.item(0, 0).checkState(), Qt.CheckState.Checked)
        self.assertEqual(table.item(1, 0).checkState(), Qt.CheckState.Unchecked)
        self.assertEqual(table.item(2, 0).checkState(), Qt.CheckState.Checked)

        # Status dots moved with their rows too
        self.assertEqual(table.item(1, 11).data(Qt.ItemDataRole.UserRole), "skipped")

        # And the row→plan anchor still resolves the right plan
        self.assertIs(self.window._get_plan_from_row(1), self.plans[1])

    def test_toggle_after_sorting_hits_correct_plan(self):
        """Toggling a checkbox in a sorted table must update the plan shown in
        that row — not the plan that originally occupied the physical row."""
        table = self.window._table
        table.sortItems(3, Qt.SortOrder.DescendingOrder)

        row = self._row_of_shot("SH020")
        table.item(row, 0).setCheckState(Qt.CheckState.Checked)  # fires itemChanged

        self.assertTrue(self.plans[1].enabled, "SH020's plan should be enabled")
        self.assertTrue(self.plans[0].enabled and self.plans[2].enabled,
                        "Other plans must be untouched")

    def test_status_filter_reads_item_data(self):
        """The status sidebar filter reads the status from item data."""
        self.window._apply_filter("skipped")  # not a sidebar value, but exercises filtering
        self.window._current_filter_status = "skipped"
        self.window._apply_table_filters()
        table = self.window._table
        hidden = {table.item(r, 3).text() for r in range(table.rowCount()) if table.isRowHidden(r)}
        self.assertEqual(hidden, {"SH010", "SH030"})

    def test_ui_lock_disables_mutating_controls(self):
        self.window._set_ui_locked(True)
        self.assertFalse(self.window._table.isEnabled())
        self.assertFalse(self.window._step_combo.isEnabled())
        self.assertFalse(self.window._drop_zone.acceptDrops())
        self.window._set_ui_locked(False)
        self.assertTrue(self.window._table.isEnabled())
        self.assertTrue(self.window._drop_zone.acceptDrops())


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestEDLLoadResolvesPaths(unittest.TestCase):
    """EDL-mapped plans must get their target paths resolved immediately —
    previously they stayed unresolved and failed at execute time with
    'No target publish directory resolved.'"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import tempfile
        from ramses_ingest.gui import IngestWindow

        self.tmp = tempfile.mkdtemp()
        self.window = IngestWindow()
        self.window._engine._project_path = self.tmp

        # An unmatched plan, as produced for a clip no naming rule recognised
        # (clip keeps its delivery filename; the Ramses identity is empty)
        plan = _make_plan("A010_RAW", enabled=True)
        plan.match.matched = False
        plan.match.shot_id = ""
        plan.shot_id = ""
        plan.error = "Could not match clip to a shot identity."
        plan.target_publish_dir = ""
        self.plan = plan
        self.window._plans = [plan]
        self.window._populate_table()

        # CMX 3600 EDL mapping the clip name to a shot id
        self.edl_path = os.path.join(self.tmp, "conform.edl")
        clip_name = plan.match.clip.base_name.upper()
        with open(self.edl_path, "w", encoding="utf-8") as f:
            f.write(f"* FROM CLIP NAME: {clip_name}\n")
            f.write("* COMMENT: SH099\n")

    def tearDown(self):
        import shutil
        self.window.close()
        self.window.deleteLater()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_edl_mapping_resolves_target_paths(self):
        from unittest.mock import patch
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(self.edl_path, ""),
        ):
            self.window._on_load_edl()

        self.assertEqual(self.plan.shot_id, "SH099")
        self.assertTrue(self.plan.match.matched)
        self.assertTrue(
            self.plan.target_publish_dir,
            "EDL-mapped plan must have a resolved publish directory",
        )
        self.assertTrue(self.plan.can_execute)


if __name__ == "__main__":
    unittest.main()
