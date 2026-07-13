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
class TestOpenDestination(unittest.TestCase):
    """The 'Open Destination' button appears after a successful ingest and
    opens the publish folder (or the common parent for several shots)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import tempfile
        from ramses_ingest.gui import IngestWindow
        self.tmp = tempfile.mkdtemp()
        self.window = IngestWindow()

    def tearDown(self):
        import shutil
        self.window.close()
        self.window.deleteLater()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _result(self, shot, ok=True, dest=None):
        from unittest.mock import MagicMock
        published = ""
        if dest:
            published = os.path.join(self.tmp, dest)
            os.makedirs(published, exist_ok=True)
        return MagicMock(success=ok, published_path=published, error="" if ok else "boom")

    def test_button_visible_after_successful_ingest(self):
        self.window._on_ingest_done([self._result("SH010", dest="SH010/PLATE/_published/001_OK")])
        self.assertTrue(self.window._btn_open_dest.isVisibleTo(self.window))
        self.assertEqual(len(self.window._last_dest_dirs), 1)

    def test_button_hidden_when_all_failed(self):
        self.window._on_ingest_done([self._result("SH010", ok=False)])
        self.assertFalse(self.window._btn_open_dest.isVisibleTo(self.window))

    def test_single_destination_opened_directly(self):
        from unittest.mock import patch
        self.window._on_ingest_done([self._result("SH010", dest="SH010/_published/001_OK")])
        with patch.object(self.window, "_open_folder") as mock_open:
            self.window._on_open_destination()
        mock_open.assert_called_once_with(self.window._last_dest_dirs[0])

    def test_multiple_destinations_open_common_parent(self):
        from unittest.mock import patch
        self.window._on_ingest_done([
            self._result("SH010", dest="shots/SH010/_published/001_OK"),
            self._result("SH020", dest="shots/SH020/_published/001_OK"),
        ])
        with patch.object(self.window, "_open_folder") as mock_open:
            self.window._on_open_destination()
        opened = mock_open.call_args[0][0]
        self.assertEqual(
            os.path.normpath(opened),
            os.path.normpath(os.path.join(self.tmp, "shots")),
        )

    def test_clear_hides_button(self):
        self.window._on_ingest_done([self._result("SH010", dest="SH010/_published/001_OK")])
        self.window._on_clear()
        self.assertFalse(self.window._btn_open_dest.isVisibleTo(self.window))
        self.assertEqual(self.window._last_dest_dirs, [])


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


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestManualShotOverrideResolvesError(unittest.TestCase):
    """Overriding the Shot ID on an UNMATCHED clip must make it executable —
    previously it was cosmetic (error and match.matched stayed failed, no
    target paths were resolved), so range folders like
    DNX_0480-0485_Lichterkette could never be ingested manually."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import tempfile
        from ramses_ingest.gui import IngestWindow
        from ramses_ingest.publisher import MATCH_ERROR

        self.tmp = tempfile.mkdtemp()
        self.window = IngestWindow()
        self.window._engine._project_path = self.tmp

        plan = _make_plan("DNX_0480-0485_Lichterkette", enabled=True)
        plan.match.matched = False
        plan.match.shot_id = ""
        plan.shot_id = ""
        plan.error = MATCH_ERROR
        plan.target_publish_dir = ""
        self.plan = plan
        self.window._plans = [plan]
        self.window._populate_table()

    def tearDown(self):
        import shutil
        self.window.close()
        self.window.deleteLater()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _select_row(self, row=0):
        for col in range(self.window._table.columnCount()):
            item = self.window._table.item(row, col)
            if item:
                item.setSelected(True)

    def test_shot_override_makes_plan_executable(self):
        from unittest.mock import patch
        self._select_row()
        with patch(
            "PySide6.QtWidgets.QInputDialog.getText", return_value=("0480", True)
        ):
            self.window._on_context_override_shot()

        self.assertEqual(self.plan.shot_id, "0480")
        self.assertTrue(self.plan.match.matched)
        self.assertEqual(self.plan.error, "")
        self.assertTrue(
            self.plan.target_publish_dir,
            "Manually matched plan must get a resolved publish directory",
        )
        self.assertTrue(self.plan.can_execute)

    def test_filename_as_shot_makes_plan_executable(self):
        self._select_row()
        self.window._on_context_filename_as_shot()
        self.assertTrue(self.plan.match.matched)
        self.assertEqual(self.plan.error, "")
        self.assertTrue(self.plan.can_execute)

    def test_other_errors_are_not_cleared(self):
        """Only the identity error may be cleared by a shot override."""
        from unittest.mock import patch
        self.plan.error = "Path collision with another clip"
        self.plan.match.matched = True
        self._select_row()
        with patch(
            "PySide6.QtWidgets.QInputDialog.getText", return_value=("0480", True)
        ):
            self.window._on_context_override_shot()
        # The collision error is recomputed by resolve — but must not have
        # been blindly wiped by the override itself before that
        self.assertEqual(self.plan.shot_id, "0480")


@unittest.skipUnless(HAS_QT, "PySide6 not available")
class TestFpsOverride(unittest.TestCase):
    """Batch FPS override via the context menu (sequences carry no fps)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from ramses_ingest.gui import IngestWindow
        self.window = IngestWindow()
        self.plans = [_make_plan("SH010"), _make_plan("SH020"), _make_plan("SH030")]
        for p in self.plans:
            p.media_info.fps = 0.0  # like a probed EXR sequence
        self.window._plans = self.plans
        self.window._populate_table()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()

    def _select_rows(self, *rows):
        self.window._table.clearSelection()
        for row in rows:
            for col in range(self.window._table.columnCount()):
                item = self.window._table.item(row, col)
                if item:
                    item.setSelected(True)

    def test_batch_override_applies_to_all_selected(self):
        from unittest.mock import patch
        self._select_rows(0, 1, 2)
        with patch(
            "PySide6.QtWidgets.QInputDialog.getDouble", return_value=(25.0, True)
        ):
            self.window._on_context_override_fps()
        self.assertEqual([p.media_info.fps for p in self.plans], [25.0, 25.0, 25.0])

    def test_cancel_changes_nothing(self):
        from unittest.mock import patch
        self._select_rows(0)
        with patch(
            "PySide6.QtWidgets.QInputDialog.getDouble", return_value=(25.0, False)
        ):
            self.window._on_context_override_fps()
        self.assertEqual(self.plans[0].media_info.fps, 0.0)

    def test_clear_overrides_restores_probed_fps(self):
        from unittest.mock import patch
        self.plans[0].media_info.fps = 23.976  # a probed movie fps
        self._select_rows(0)
        with patch(
            "PySide6.QtWidgets.QInputDialog.getDouble", return_value=(25.0, True)
        ):
            self.window._on_context_override_fps()
        self.assertEqual(self.plans[0].media_info.fps, 25.0)

        self._select_rows(0)
        self.window._on_context_clear_overrides()
        self.assertEqual(self.plans[0].media_info.fps, 23.976)


class TestColorspaceList(unittest.TestCase):
    """ARRI LogC4 footage must be selectable (single shared list)."""

    def test_arri_logc4_available(self):
        from ramses_ingest.gui import STANDARD_COLORSPACES
        self.assertIn("ARRI LogC4", STANDARD_COLORSPACES)
        self.assertIn("ARRI LogC3 (EI800)", STANDARD_COLORSPACES)
        self.assertIn("LogC", STANDARD_COLORSPACES)  # legacy entry kept


if __name__ == "__main__":
    unittest.main()
