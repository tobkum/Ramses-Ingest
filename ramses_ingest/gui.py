# -*- coding: utf-8 -*-
"""PySide6 GUI for Ramses Ingest — dark professional theme matching Ramses-Fusion."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem,
    QCheckBox, QTextEdit, QProgressBar, QFrame, QDialog,
    QLineEdit, QSplitter, QHeaderView, QSizePolicy, QMessageBox,
)

from ramses_ingest.app import IngestEngine
from ramses_ingest.publisher import IngestPlan, IngestResult
from ramses_ingest.config import load_rules, save_rules, DEFAULT_RULES_PATH


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = """
QMainWindow {
    background-color: #1e1e1e;
}

QWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
}

/* --- Labels --- */
QLabel {
    color: #d4d4d4;
}

QLabel#headerLabel {
    font-weight: bold;
    color: #ffffff;
}

QLabel#mutedLabel {
    color: #808080;
}

QLabel#statusConnected {
    color: #4ec9b0;
    font-weight: bold;
}

QLabel#statusDisconnected {
    color: #f44747;
}

/* --- Inputs --- */
QComboBox {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    border-radius: 4px;
    padding: 2px 8px;
    color: #d4d4d4;
    min-height: 24px;
}

QComboBox:hover {
    border-color: #007acc;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #252526;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
    selection-background-color: #094771;
}

QPushButton {
    background-color: #333333;
    border: 1px solid #454545;
    border-radius: 4px;
    padding: 4px 12px;
    color: #cccccc;
    min-height: 24px;
    text-align: center;
}

QPushButton:hover {
    background-color: #3c3c3c;
    border-color: #007acc;
}

QPushButton:pressed {
    background-color: #007acc;
    color: white;
}

QPushButton:disabled {
    background-color: #252526;
    color: #555555;
    border-color: #333333;
}

QPushButton#ingestButton {
    background-color: #0e639c;
    border: none;
    color: #ffffff;
    font-weight: bold;
    padding: 6px 20px;
}

QPushButton#ingestButton:hover {
    background-color: #1177bb;
}

QPushButton#ingestButton:disabled {
    background-color: #333333;
    color: #666666;
}

/* --- Tree --- */
QTreeWidget {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    alternate-background-color: #222222;
    color: #cccccc;
    outline: none;
}

QTreeWidget::item {
    padding: 3px;
    border-bottom: 1px solid #2d2d2d;
}

QTreeWidget::item:selected {
    background-color: #094771;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #252526;
    border: none;
    border-right: 1px solid #333333;
    padding: 4px;
    color: #888888;
    font-weight: bold;
}

/* --- Other --- */
QTextEdit {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    color: #85c46c;
}

QProgressBar {
    background-color: #252526;
    border: 1px solid #333333;
    border-radius: 2px;
    text-align: center;
    color: transparent;
    height: 4px;
}

QProgressBar::chunk {
    background-color: #007acc;
}

QCheckBox {
    color: #cccccc;
}

QFrame#dropZone {
    background-color: #252526;
    border: 2px dashed #3e3e42;
    border-radius: 8px;
}

QFrame#dropZone[dragOver="true"] {
    border-color: #007acc;
    background-color: #1c2b3a;
}
"""


# ---------------------------------------------------------------------------
# Drop Zone
# ---------------------------------------------------------------------------

class DropZone(QFrame):
    """Drag-and-drop zone accepting folders and files."""

    paths_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label = QLabel("Drop Footage Here\nAccepts folders and files")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setObjectName("mutedLabel")
        layout.addWidget(self._label)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragOver", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

        paths = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                paths.append(local)

        if paths:
            self.paths_dropped.emit(paths)


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

class ScanWorker(QThread):
    """Scans delivery paths in a background thread."""

    progress = Signal(str)
    finished_plans = Signal(list)
    error = Signal(str)

    def __init__(self, engine: IngestEngine, paths: list[str], parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._paths = paths

    def run(self) -> None:
        try:
            plans = self._engine.load_delivery(
                self._paths,
                progress_callback=self.progress.emit,
            )
            self.finished_plans.emit(plans)
        except Exception as exc:
            self.error.emit(str(exc))


class IngestWorker(QThread):
    """Executes ingest plans in a background thread."""

    progress = Signal(str)
    step_done = Signal(int)
    finished_results = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        engine: IngestEngine,
        plans: list[IngestPlan],
        thumbnails: bool,
        proxies: bool,
        update_status: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._plans = plans
        self._thumbnails = thumbnails
        self._proxies = proxies
        self._update_status = update_status
        self._count = 0

    def run(self) -> None:
        try:

            def _cb(msg: str) -> None:
                self.progress.emit(msg)
                if msg.startswith("["):
                    self._count += 1
                    self.step_done.emit(self._count)

            results = self._engine.execute(
                self._plans,
                generate_thumbnails=self._thumbnails,
                generate_proxies=self._proxies,
                progress_callback=_cb,
                update_status=self._update_status,
            )
            self.finished_results.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Rules Editor Dialog
# ---------------------------------------------------------------------------

class RulesEditorDialog(QDialog):
    """Simple YAML text editor for naming rules (Consolas, dark theme)."""

    def __init__(self, rules_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Naming Rules")
        self.resize(600, 400)
        self._path = rules_path

        layout = QVBoxLayout(self)
        self._editor = QTextEdit()
        layout.addWidget(self._editor)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_cancel = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)

        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._editor.setPlainText(f.read())
        except FileNotFoundError:
            self._editor.setPlainText("rules:\n  []")

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(self._editor.toPlainText())
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Could not save: {exc}")


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class IngestWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RAMSES INGEST")
        self.resize(780, 700)

        self._engine = IngestEngine()
        self._plans: list[IngestPlan] = []
        self._scan_worker: ScanWorker | None = None
        self._ingest_worker: IngestWorker | None = None

        self._build_ui()
        self._try_connect()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # --- Header ---------------------------------------------------------
        header = QHBoxLayout()
        title = QLabel("RAMSES INGEST")
        title.setObjectName("headerLabel")
        header.addWidget(title)
        header.addStretch()
        self._status_label = QLabel("Disconnected")
        self._status_label.setObjectName("statusDisconnected")
        header.addWidget(self._status_label)
        root.addLayout(header)

        # --- Project / Step -------------------------------------------------
        proj_row = QHBoxLayout()
        self._project_label = QLabel("Project: —")
        proj_row.addWidget(self._project_label)
        proj_row.addStretch()
        
        proj_row.addWidget(QLabel("Studio:"))
        self._studio_edit = QLineEdit(self._engine.studio_name)
        self._studio_edit.setMinimumWidth(120)
        self._studio_edit.textChanged.connect(self._on_studio_changed)
        proj_row.addWidget(self._studio_edit)

        proj_row.addWidget(QLabel("Step:"))
        self._step_combo = QComboBox()
        self._step_combo.setMinimumWidth(100)
        self._step_combo.addItem("PLATE")
        self._step_combo.currentTextChanged.connect(self._on_step_changed)
        proj_row.addWidget(self._step_combo)
        root.addLayout(proj_row)

        # --- Drop zone ------------------------------------------------------
        self._drop_zone = DropZone()
        self._drop_zone.paths_dropped.connect(self._on_drop)
        root.addWidget(self._drop_zone)

        # --- Rule selector --------------------------------------------------
        rule_row = QHBoxLayout()
        rule_row.addWidget(QLabel("Naming Rule:"))
        self._rule_combo = QComboBox()
        self._rule_combo.setMinimumWidth(200)
        self._rule_combo.addItem("Auto-detect")
        self._populate_rule_combo()
        rule_row.addWidget(self._rule_combo, 1)
        
        self._btn_edl = QPushButton("Load EDL...")
        self._btn_edl.clicked.connect(self._on_load_edl)
        rule_row.addWidget(self._btn_edl)

        btn_edit_rules = QPushButton("Edit Rules...")
        btn_edit_rules.clicked.connect(self._on_edit_rules)
        rule_row.addWidget(btn_edit_rules)
        root.addLayout(rule_row)

        # --- Shot table -----------------------------------------------------
        self._tree = QTreeWidget()
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._tree.setHeaderLabels([
            "", "Status", "Sequence", "Shot", "Frames", "Res", "FPS", "Source", "Destination",
        ])
        hdr = self._tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(0, 28)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(1, 50)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        for col in (2, 3, 4, 5, 6):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setMinimumHeight(180)
        root.addWidget(self._tree, 1)

        # --- Options --------------------------------------------------------
        opt_row1 = QHBoxLayout()
        self._chk_thumb = QCheckBox("Generate thumbnails")
        self._chk_thumb.setChecked(True)
        opt_row1.addWidget(self._chk_thumb)
        self._chk_proxy = QCheckBox("Generate video proxies")
        self._chk_proxy.setChecked(False)
        opt_row1.addWidget(self._chk_proxy)
        opt_row1.addStretch()
        root.addLayout(opt_row1)

        opt_row2 = QHBoxLayout()
        self._chk_status = QCheckBox("Set PLATE status to OK")
        self._chk_status.setChecked(True)
        opt_row2.addWidget(self._chk_status)
        opt_row2.addStretch()
        root.addLayout(opt_row2)

        # --- Summary --------------------------------------------------------
        self._summary_label = QLabel("No delivery loaded.")
        self._summary_label.setObjectName("mutedLabel")
        root.addWidget(self._summary_label)

        # --- Action buttons -------------------------------------------------
        btn_row = QHBoxLayout()
        self._btn_clear = QPushButton("Clear")
        self._btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self._btn_clear)
        btn_row.addStretch()
        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_cancel.setVisible(False)
        btn_row.addWidget(self._btn_cancel)
        self._btn_ingest = QPushButton("Ingest 0/0")
        self._btn_ingest.setObjectName("ingestButton")
        self._btn_ingest.setEnabled(False)
        self._btn_ingest.clicked.connect(self._on_ingest)
        btn_row.addWidget(self._btn_ingest)
        root.addLayout(btn_row)

        # --- Progress bar ---------------------------------------------------
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # --- Log panel (collapsible) ----------------------------------------
        self._log_toggle = QPushButton("[ + ] Log")
        self._log_toggle.setMaximumWidth(80)
        self._log_toggle.clicked.connect(self._toggle_log)
        root.addWidget(self._log_toggle)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumHeight(160)
        self._log_edit.setVisible(False)
        root.addWidget(self._log_edit)

    # -- Helpers -------------------------------------------------------------

    def _log(self, msg: str) -> None:
        self._log_edit.append(msg)
        sb = self._log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _try_connect(self) -> None:
        ok = self._engine.connect_ramses()
        if ok:
            self._status_label.setText("Connected")
            self._status_label.setObjectName("statusConnected")
            pid = self._engine.project_id
            pname = self._engine.project_name
            self._project_label.setText(f"Project: {pid} | {pname}")
            # Populate steps
            self._step_combo.clear()
            for s in self._engine.steps:
                self._step_combo.addItem(s)
            if "PLATE" in self._engine.steps:
                self._step_combo.setCurrentText("PLATE")
        else:
            self._status_label.setText("Disconnected")
            self._status_label.setObjectName("statusDisconnected")
            self._project_label.setText("Project: — (daemon offline)")
            self._btn_ingest.setToolTip("Ramses connection required to ingest.")

        # Re-polish to apply dynamic objectName change
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        self._update_summary()

    def _populate_rule_combo(self) -> None:
        rules, _ = load_rules()
        for i, rule in enumerate(rules):
            label = rule.pattern[:40] + ("..." if len(rule.pattern) > 40 else "")
            self._rule_combo.addItem(f"Rule {i + 1}: {label}")

    def _update_summary(self) -> None:
        if not self._plans:
            self._summary_label.setText("No delivery loaded.")
            self._btn_ingest.setText("Ingest 0/0")
            self._btn_ingest.setEnabled(False)
            return

        total = len(self._plans)
        matched = sum(1 for p in self._plans if p.match.matched)
        unmatched = total - matched
        new_shots = sum(1 for p in self._plans if p.is_new_shot and p.match.matched)
        updates = matched - new_shots

        enabled = self._get_enabled_plans()
        n_enabled = len(enabled)

        parts = []
        if matched:
            parts.append(f"{matched} shot{'s' if matched != 1 else ''}")
            sub = []
            if new_shots:
                sub.append(f"{new_shots} new")
            if updates:
                sub.append(f"{updates} update")
            if sub:
                parts[-1] += f" ({', '.join(sub)})"
        if unmatched:
            parts.append(f"{unmatched} unmatched")

        self._summary_label.setText(f"Summary: {', '.join(parts)}")
        self._btn_ingest.setText(f"Ingest {n_enabled}/{total}")
        # Only enable if there are plans AND we are connected
        self._btn_ingest.setEnabled(n_enabled > 0 and self._engine.connected)

    def _get_enabled_plans(self) -> list[IngestPlan]:
        enabled = []
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked and i < len(self._plans):
                plan = self._plans[i]
                if plan.can_execute:
                    enabled.append(plan)
        return enabled

    def _populate_tree(self) -> None:
        self._tree.clear()
        for plan in self._plans:
            item = QTreeWidgetItem()

            # Checkbox
            if plan.can_execute:
                item.setCheckState(0, Qt.CheckState.Checked)
            else:
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)

            # Status
            if not plan.match.matched:
                item.setText(1, "---")
                item.setForeground(1, QColor("#B2B24C"))
            elif plan.is_new_shot:
                item.setText(1, "NEW")
                item.setForeground(1, QColor("#4CB24C"))
            else:
                item.setText(1, "UPD")
                item.setForeground(1, QColor("#4C8CB2"))

            # Sequence / Shot
            item.setText(2, plan.sequence_id or "???")
            item.setText(3, plan.shot_id or "???")

            # Frames
            clip = plan.match.clip
            if clip.is_sequence:
                item.setText(4, f"{clip.frame_count}fr")
            else:
                item.setText(4, "movie")

            # Resolution
            mi = plan.media_info
            if mi.is_valid:
                item.setText(5, f"{mi.width}x{mi.height}")
            else:
                item.setText(5, "—")

            # FPS
            if mi.fps > 0:
                item.setText(6, f"{mi.fps:.3f}")
            else:
                item.setText(6, "—")

            # Source
            item.setText(7, clip.base_name)
            item.setToolTip(7, clip.first_file)

            # Destination
            if plan.target_publish_dir:
                dest_base = os.path.basename(os.path.dirname(plan.target_publish_dir)) # _published
                version = os.path.basename(plan.target_publish_dir) # v001
                # Show a shortened version: SHOT/STEP/_published/v001
                display_path = f"{plan.shot_id}/{plan.step_id}/{dest_base}/{version}"
                item.setText(8, display_path)
                item.setToolTip(8, plan.target_publish_dir)
            else:
                item.setText(8, "—")

            # Editable seq/shot for unmatched
            if not plan.match.matched:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

            self._tree.addTopLevelItem(item)

        self._update_summary()

    # -- Slots ---------------------------------------------------------------

    def _on_step_changed(self, text: str) -> None:
        if text:
            self._engine.step_id = text

    def _on_studio_changed(self, text: str) -> None:
        self._engine.studio_name = text
        save_rules(self._engine.rules, DEFAULT_RULES_PATH, studio_name=text)

    def _on_drop(self, paths: list[str]) -> None:
        if self._scan_worker and self._scan_worker.isRunning():
            return

        self._log(f"Loading delivery: {len(paths)} item(s)")
        self._drop_zone._label.setText(f"Scanning {len(paths)} item(s)...")

        # Scan all dropped paths. LoadDelivery in app might need to be updated 
        # or we call it multiple times. Let's update engine.load_delivery to handle list.
        self._scan_worker = ScanWorker(self._engine, paths, parent=self)
        self._scan_worker.progress.connect(self._log)
        self._scan_worker.finished_plans.connect(self._on_scan_done)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_done(self, plans: list[IngestPlan]) -> None:
        self._plans = plans
        self._populate_tree()
        self._drop_zone._label.setText("Drop Footage Here\nAccepts folders and files")
        self._log(f"Scan complete: {len(plans)} clip(s) detected.")

    def _on_scan_error(self, msg: str) -> None:
        self._log(f"ERROR: {msg}")
        self._drop_zone._label.setText("Drop Footage Here\nAccepts folders and files")

    def _on_clear(self) -> None:
        self._plans.clear()
        self._tree.clear()
        self._update_summary()
        self._log_edit.clear()
        self._progress.setVisible(False)

    def _on_cancel(self) -> None:
        if self._ingest_worker and self._ingest_worker.isRunning():
            self._ingest_worker.terminate()
            self._log("Ingest cancelled by user.")
            self._btn_cancel.setVisible(False)
            self._btn_ingest.setEnabled(True)
            self._progress.setVisible(False)

    def _on_ingest(self) -> None:
        enabled = self._get_enabled_plans()
        if not enabled:
            return

        self._btn_ingest.setEnabled(False)
        self._btn_cancel.setVisible(True)
        self._progress.setMaximum(len(enabled))
        self._progress.setValue(0)
        self._progress.setVisible(True)

        # Show log automatically
        if not self._log_edit.isVisible():
            self._toggle_log()

        self._ingest_worker = IngestWorker(
            self._engine,
            enabled,
            thumbnails=self._chk_thumb.isChecked(),
            proxies=self._chk_proxy.isChecked(),
            update_status=self._chk_status.isChecked(),
            parent=self,
        )
        self._ingest_worker.progress.connect(self._log)
        self._ingest_worker.step_done.connect(self._progress.setValue)
        self._ingest_worker.finished_results.connect(self._on_ingest_done)
        self._ingest_worker.error.connect(self._on_ingest_error)
        self._ingest_worker.start()

    def _on_ingest_done(self, results: list[IngestResult]) -> None:
        self._btn_cancel.setVisible(False)
        self._btn_ingest.setEnabled(True)

        ok = sum(1 for r in results if r.success)
        fail = len(results) - ok
        self._log(f"Ingest complete: {ok} succeeded, {fail} failed.")

    def _on_ingest_error(self, msg: str) -> None:
        self._btn_cancel.setVisible(False)
        self._btn_ingest.setEnabled(True)
        self._progress.setVisible(False)
        self._log(f"INGEST ERROR: {msg}")

    def _on_edit_rules(self) -> None:
        dlg = RulesEditorDialog(DEFAULT_RULES_PATH, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._rule_combo.clear()
            self._rule_combo.addItem("Auto-detect")
            self._populate_rule_combo()
            rules, studio = load_rules()
            self._engine.rules = rules
            self._engine.studio_name = studio
            self._studio_edit.setText(studio)
            self._log("Rules and Studio name reloaded.")

    def _on_load_edl(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select EDL File", "", "EDL Files (*.edl);;All Files (*.*)"
        )
        if not path:
            return

        self._log(f"Applying EDL mapping: {os.path.basename(path)}")
        from ramses_ingest.matcher import EDLMapper
        mapper = EDLMapper(path)
        
        updated = 0
        for plan in self._plans:
            # Try to map by clip name
            clip_name = plan.match.clip.base_name
            edl_shot = mapper.get_shot_id(clip_name)
            if edl_shot:
                plan.shot_id = edl_shot
                plan.match.matched = True # Force matched if EDL finds it
                plan.error = ""
                updated += 1
        
        if updated:
            self._log(f"  Mapped {updated} shot(s) from EDL.")
            self._populate_tree()
        else:
            self._log("  No matches found in EDL.")

    def _toggle_log(self) -> None:
        visible = not self._log_edit.isVisible()
        self._log_edit.setVisible(visible)
        self._log_toggle.setText("[ - ] Log" if visible else "[ + ] Log")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def launch_gui() -> None:
    """Create the QApplication and show the main window."""
    existing = QApplication.instance()
    app = existing or QApplication(sys.argv)
    
    # Tier 1 UI: Set consistent global font (9pt is standard for VFX apps)
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    app.setStyleSheet(STYLESHEET)

    window = IngestWindow()
    window.show()

    # Only start the event loop if we created the application ourselves
    if existing is None:
        sys.exit(app.exec())
