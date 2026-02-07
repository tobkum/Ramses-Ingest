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
    QTableWidget, QTableWidgetItem, QStyledItemDelegate, QAbstractItemView,
    QMenu, QGroupBox, QScrollArea,
)

from ramses_ingest.app import IngestEngine
from ramses_ingest.publisher import IngestPlan, IngestResult
from ramses_ingest.config import load_rules, save_rules, DEFAULT_RULES_PATH


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = """
QMainWindow {
    background-color: #121212;
}

QWidget {
    background-color: #121212;
    color: #e0e0e0;
}

/* --- Labels --- */
QLabel {
    color: #cccccc;
}

QLabel#headerLabel {
    font-size: 14px;
    font-weight: bold;
    color: #ffffff;
    letter-spacing: 1px;
}

QLabel#projectLabel {
    font-size: 12px;
    font-weight: bold;
    color: #00bff3;
}

QLabel#mutedLabel {
    color: #666666;
}

QLabel#statusConnected {
    color: #00bff3;
    font-weight: bold;
}

QLabel#statusDisconnected {
    color: #f44747;
}

/* --- Status Orb --- */
QFrame#statusOrb {
    border-radius: 6px;
    max-width: 12px;
    max-height: 12px;
    min-width: 12px;
    min-height: 12px;
}

/* --- Inputs --- */
QLineEdit {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 4px 10px;
    color: #ffffff;
}

QLineEdit:focus {
    border-color: #00bff3;
    background-color: #252526;
}

QComboBox {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 4px 10px;
}

QComboBox:hover {
    border-color: #444444;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #333333, stop:1 #2d2d2d);
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 5px 15px;
    color: #e0e0e0;
    font-weight: 500;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3d3d3d, stop:1 #333333);
    border-color: #00bff3;
}

QPushButton:pressed {
    background-color: #00bff3;
    color: white;
}

QPushButton#ingestButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00bff3, stop:1 #0095c2);
    border: none;
    color: #ffffff;
    font-weight: bold;
    padding: 8px 25px;
}

QPushButton#ingestButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #33ccff, stop:1 #00bff3);
}

QPushButton#ingestButton:disabled {
    background: #252526;
    color: #555555;
}

/* --- Production Grid --- */
QTreeWidget {
    background-color: #181818;
    border: 1px solid #2d2d2d;
    alternate-background-color: #1e1e1e;
    color: #d4d4d4;
    outline: none;
}

QTreeWidget::item {
    height: 32px;
    border-bottom: 1px solid #252526;
}

QTreeWidget::item:hover {
    background-color: #2a2d2e;
}

QTreeWidget::item:selected {
    background-color: #094771;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #252526;
    border: none;
    border-right: 1px solid #121212;
    padding: 6px;
    color: #888888;
    font-weight: bold;
    font-size: 10px;
    text-transform: uppercase;
}

/* --- Progress --- */
QProgressBar {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 3px;
    text-align: center;
    height: 6px;
}

QProgressBar::chunk {
    background-color: #00bff3;
}

QFrame#dropZone {
    background-color: #1e1e1e;
    border: 2px dashed #333333;
    border-radius: 10px;
}

QFrame#dropZone[dragOver="true"] {
    border-color: #00bff3;
    background-color: #162633;
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
# Helper Widgets for Professional UX
# ---------------------------------------------------------------------------

class StatusIndicator(QLabel):
    """Color-coded status dot (● instead of text)"""

    def __init__(self, status: str = "pending", parent=None):
        super().__init__(parent)
        self.set_status(status)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(20, 20)

    def set_status(self, status: str):
        """Update status color: ready=green, warning=yellow, error=red, pending=gray"""
        colors = {
            "ready": "#4ec9b0",      # Green
            "warning": "#f39c12",    # Yellow/Orange
            "error": "#f44747",      # Red
            "pending": "#666666",    # Gray
            "duplicate": "#999999",  # Light gray
        }
        color = colors.get(status, "#666666")
        self.setText("●")
        self.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
        self.setToolTip(status.title())


class EditableDelegate(QStyledItemDelegate):
    """Delegate for inline editing of table cells"""

    def createEditor(self, parent, option, index):
        """Create editor for shot ID override"""
        if index.column() == 3:  # Shot column
            editor = QLineEdit(parent)
            editor.setStyleSheet("background: #2d2d30; border: 1px solid #00bff3;")
            return editor
        return super().createEditor(parent, option, index)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class IngestWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RAMSES INGEST")
        self.resize(1200, 700)  # Wider for 3-panel layout

        self._engine = IngestEngine()
        self._plans: list[IngestPlan] = []
        self._scan_worker: ScanWorker | None = None
        self._ingest_worker: IngestWorker | None = None
        self._current_filter_status = "all"  # For filter sidebar
        self._selected_plan_idx = -1  # For detail panel

        self._build_ui()
        self._try_connect()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(12)

        # --- Header (Command Center) ----------------------------------------
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 10)
        
        # Connection Badge
        status_cont = QHBoxLayout()
        status_cont.setSpacing(8)
        self._status_orb = QFrame()
        self._status_orb.setObjectName("statusOrb")
        self._status_orb.setStyleSheet("background-color: #f44747; border: 1px solid rgba(255,255,255,0.1);")
        status_cont.addWidget(self._status_orb)
        
        self._status_label = QLabel("DISCONNECTED")
        self._status_label.setObjectName("statusDisconnected")
        self._status_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        status_cont.addWidget(self._status_label)
        header.addLayout(status_cont)
        
        header.addStretch()
        
        title = QLabel("RAMSES INGEST")
        title.setObjectName("headerLabel")
        header.addWidget(title)
        root.addLayout(header)

        # --- Project Context ------------------------------------------------
        proj_panel = QFrame()
        proj_panel.setStyleSheet("background-color: #1e1e1e; border-radius: 6px; padding: 5px;")
        proj_lay = QHBoxLayout(proj_panel)
        
        self._project_label = QLabel("PROJECT: —")
        self._project_label.setObjectName("projectLabel")
        proj_lay.addWidget(self._project_label)
        
        self._standards_label = QLabel("")
        self._standards_label.setObjectName("mutedLabel")
        self._standards_label.setFont(QFont("Segoe UI", 8))
        proj_lay.addWidget(self._standards_label)
        
        proj_lay.addStretch()
        
        proj_lay.addWidget(QLabel("Studio:"))
        self._studio_edit = QLineEdit(self._engine.studio_name)
        self._studio_edit.setMinimumWidth(140)
        self._studio_edit.textChanged.connect(self._on_studio_changed)
        proj_lay.addWidget(self._studio_edit)

        proj_lay.addWidget(QLabel("Step:"))
        self._step_combo = QComboBox()
        self._step_combo.setMinimumWidth(120)
        self._step_combo.addItem("PLATE")
        self._step_combo.currentTextChanged.connect(self._on_step_changed)
        proj_lay.addWidget(self._step_combo)
        root.addWidget(proj_panel)

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
        
        btn_architect = QPushButton("Architect...")
        btn_architect.clicked.connect(self._on_launch_architect)
        btn_architect.setStyleSheet("font-weight: bold; color: #00bff3;")
        rule_row.addWidget(btn_architect)

        self._btn_edl = QPushButton("Load EDL...")
        self._btn_edl.clicked.connect(self._on_load_edl)
        rule_row.addWidget(self._btn_edl)

        btn_edit_rules = QPushButton("Edit Rules...")
        btn_edit_rules.clicked.connect(self._on_edit_rules)
        rule_row.addWidget(btn_edit_rules)
        root.addLayout(rule_row)

        # --- Filter bar -----------------------------------------------------
        filter_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search by Shot or Sequence ID...")
        self._search_edit.textChanged.connect(self._on_search_changed)
        filter_row.addWidget(self._search_edit)
        root.addLayout(filter_row)

        # --- Shot table -----------------------------------------------------
        self._tree = QTreeWidget()
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._tree.setHeaderLabels([
            "", "Status", "Sequence", "Shot", "Frames", "Res", "FPS", "Source", "Destination",
        ])
        hdr = self._tree.header()
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
        
        # Reset modes to allow manual resizing while keeping smart defaults
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed) # Checkbox
        hdr.resizeSection(0, 28)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed) # Status
        hdr.resizeSection(1, 55)
        
        # All data columns are interactive by default
        for col in range(2, 8):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            hdr.resizeSection(col, 80) # Default starting width
            
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch) # Destination
        
        self._tree.setSortingEnabled(True) # Enable header sorting
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
        
        opt_row2.addSpacing(20)
        opt_row2.addWidget(QLabel("Colorspace:"))
        self._ocio_in = QComboBox()
        self._ocio_in.addItems(["sRGB", "Linear", "Rec.709", "LogC", "S-Log3", "V-Log"])
        self._ocio_in.currentTextChanged.connect(self._on_ocio_in_changed)
        opt_row2.addWidget(self._ocio_in)
        
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
        
        self._btn_view_report = QPushButton("View Report")
        self._btn_view_report.clicked.connect(self._on_view_report)
        self._btn_view_report.setVisible(False)
        self._btn_view_report.setStyleSheet("color: #4ec9b0; font-weight: bold;")
        btn_row.addWidget(self._btn_view_report)

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
            self._status_orb.setStyleSheet("""
                background-color: #00bff3; 
                border: 1px solid rgba(255,255,255,0.2);
                border-radius: 6px;
            """)
            # Apply glowing shadow for "Live" feel
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            glow = QGraphicsDropShadowEffect()
            glow.setBlurRadius(15)
            glow.setColor(QColor("#00bff3"))
            glow.setOffset(0)
            self._status_orb.setGraphicsEffect(glow)

            self._status_label.setText("DAEMON ONLINE")
            self._status_label.setObjectName("statusConnected")
            pid = self._engine.project_id
            pname = self._engine.project_name
            self._project_label.setText(f"PROJECT: {pid} | {pname}")
            
            # Update Standards Display
            fps = self._engine._project_fps
            w = self._engine._project_width
            h = self._engine._project_height
            self._standards_label.setText(f"STANDARD: {w}x{h} @ {fps:.2f} FPS")

            # Populate steps
            self._step_combo.clear()
            for s in self._engine.steps:
                self._step_combo.addItem(s)
            if "PLATE" in self._engine.steps:
                self._step_combo.setCurrentText("PLATE")
        else:
            self._status_orb.setStyleSheet("background-color: #f44747; border-radius: 6px;")
            self._status_orb.setGraphicsEffect(None)
            self._status_label.setText("DAEMON OFFLINE")
            self._status_label.setObjectName("statusDisconnected")
            self._project_label.setText("PROJECT: — (CONNECTION REQUIRED)")
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
        
        # Strict enforcement: Connection AND valid plans AND a defined pipeline step
        has_step = bool(self._step_combo.currentText())
        self._btn_ingest.setEnabled(n_enabled > 0 and self._engine.connected and has_step)
        
        if self._engine.connected and not has_step:
            self._btn_ingest.setToolTip("No Shot Production steps found in this project. Ingest disabled.")
        else:
            self._btn_ingest.setToolTip("")

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
            # Link the plan object to the tree item for robust retrieval during sorting
            item.setData(0, Qt.ItemDataRole.UserRole, plan)

            # Checkbox
            if plan.can_execute:
                item.setCheckState(0, Qt.CheckState.Checked)
            else:
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)

            # Status Badge (Tier 1 High-Fidelity)
            status_widget = QWidget()
            status_lay = QHBoxLayout(status_widget)
            status_lay.setContentsMargins(4, 4, 4, 4)
            status_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            lbl_badge = QLabel()
            lbl_badge.setFixedWidth(42)
            lbl_badge.setFixedHeight(18)
            lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_badge.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            
            if not plan.match.matched:
                lbl_badge.setText(" ? ")
                lbl_badge.setStyleSheet("background-color: #444; color: #888; border-radius: 4px;")
            elif plan.is_new_shot:
                lbl_badge.setText(" NEW ")
                lbl_badge.setStyleSheet("background-color: #27ae60; color: white; border-radius: 4px; font-weight: bold;")
            else:
                lbl_badge.setText(" UPD ")
                lbl_badge.setStyleSheet("background-color: #2980b9; color: white; border-radius: 4px; font-weight: bold;")
            
            status_lay.addWidget(lbl_badge)
            self._tree.addTopLevelItem(item)
            self._tree.setItemWidget(item, 1, status_widget)

            # Sequence / Shot
            item.setText(2, plan.sequence_id or "???")
            item.setText(3, plan.shot_id or "???")

            # Frames
            clip = plan.match.clip
            mi = plan.media_info
            if clip.is_sequence:
                item.setText(4, str(clip.frame_count))
            elif mi.frame_count > 0:
                item.setText(4, str(mi.frame_count))
            else:
                item.setText(4, "1") # Single file

            # --- Technical Validation (Tier 1 Heuristics) ---
            mi = plan.media_info
            # Get effective standard (Sequence override or Project default)
            target_fps, target_w, target_h = self._engine._project_fps, self._engine._project_width, self._engine._project_height
            if plan.sequence_id and plan.sequence_id.upper() in self._engine._sequence_settings:
                target_fps, target_w, target_h = self._engine._sequence_settings[plan.sequence_id.upper()]

            # Resolution Check
            if mi.is_valid:
                item.setText(5, f"{mi.width}x{mi.height}")
                if mi.width != target_w or mi.height != target_h:
                    item.setForeground(5, QColor("#f39c12")) # Amber warning
                    item.setToolTip(5, f"Resolution mismatch: {mi.width}x{mi.height} vs Standard {target_w}x{target_h}")
            else:
                item.setText(5, "—")

            # FPS Check
            display_fps = mi.fps
            if not clip.is_sequence and mi.frame_count <= 1:
                # Still image: assume target project FPS for consistency
                display_fps = target_fps

            if display_fps > 0:
                item.setText(6, f"{display_fps:.3f}")
                if round(display_fps, 3) != round(target_fps, 3):
                    item.setForeground(6, QColor("#f39c12")) # Amber warning
                    item.setToolTip(6, f"FPS mismatch: {display_fps:.3f} vs Standard {target_fps:.3f}")
            else:
                item.setText(6, "—")

            # Global Row Warning: if any technical spec is off, highlight the background subtly
            has_mismatch = (mi.is_valid and (mi.width != target_w or mi.height != target_h)) or \
                           (display_fps > 0 and round(display_fps, 3) != round(target_fps, 3))
            
            if has_mismatch:
                # Subtly tint the row to draw attention
                for col in range(self._tree.columnCount()):
                    if col != 1: # Don't tint the status badge area
                        item.setBackground(col, QColor(243, 156, 18, 20)) # 8% opacity Amber

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
                # Subtle red background for issues
                for col in range(self._tree.columnCount()):
                    item.setBackground(col, QColor("#3d1c1c"))

            self._tree.addTopLevelItem(item)

        self._update_summary()

    # -- Slots ---------------------------------------------------------------

    def _on_ocio_in_changed(self, text: str) -> None:
        self._engine.ocio_in = text

    def _on_ocio_out_changed(self, text: str) -> None:
        self._engine.ocio_out = text

    def _on_studio_changed(self, text: str) -> None:
        """Update engine and persist studio name to config."""
        self._engine.studio_name = text
        save_rules(self._engine.rules, DEFAULT_RULES_PATH, studio_name=text)

    def _on_view_report(self) -> None:
        """Open the last generated HTML report in the system browser."""
        if self._engine.last_report_path and os.path.exists(self._engine.last_report_path):
            import webbrowser
            webbrowser.open(f"file:///{os.path.abspath(self._engine.last_report_path)}")

    def keyPressEvent(self, event) -> None:
        """Handle Delete key for batch removal."""
        if event.key() == Qt.Key.Key_Delete:
            self._remove_selected_plans()
        else:
            super().keyPressEvent(event)

    def _on_step_changed(self, text: str) -> None:
        if text:
            self._engine.step_id = text
            self._chk_status.setText(f"Set {text} status to OK")
            # Re-resolve paths when step changes so Destination column updates
            if self._plans:
                self._engine.step_id = text
                if self._engine.connected:
                    from ramses_ingest.publisher import resolve_paths_from_daemon
                    resolve_paths_from_daemon(self._plans, self._engine._shot_objects)
                self._populate_tree()
        else:
            self._engine.step_id = ""
            self._chk_status.setText("Set status to OK")

        self._update_summary()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Update the button summary when a checkbox is toggled."""
        if column == 0:
            self._update_summary()

    def _on_search_changed(self, text: str) -> None:
        """Filter the shot table based on sequence or shot ID."""
        search = text.lower()
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            seq = item.text(2).lower()
            shot = item.text(3).lower()
            item.setHidden(search not in seq and search not in shot)

    def _on_context_menu(self, pos) -> None:
        """Show a right-click menu for the selected items."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        selected = self._tree.selectedItems()
        if not selected:
            return

        menu = QMenu(self)
        
        if len(selected) == 1:
            item = selected[0]
            idx = self._tree.indexOfTopLevelItem(item)
            plan = self._plans[idx]
            
            act_src = QAction("Open Source Folder", self)
            act_src.triggered.connect(lambda: os.startfile(plan.match.clip.directory))
            menu.addAction(act_src)

            if plan.target_publish_dir and os.path.exists(plan.target_publish_dir):
                act_dst = QAction("Open Destination Folder", self)
                act_dst.triggered.connect(lambda: os.startfile(plan.target_publish_dir))
                menu.addAction(act_dst)
            
            menu.addSeparator()
        
        label = f"Remove {len(selected)} item(s) from List"
        act_remove = QAction(label, self)
        act_remove.triggered.connect(self._remove_selected_plans)
        menu.addAction(act_remove)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _remove_selected_plans(self) -> None:
        """Batch remove all selected items robustly using plan object linkage."""
        selected = self._tree.selectedItems()
        if not selected:
            return
            
        # Get the actual plan objects from the selected items
        plans_to_remove = []
        for item in selected:
            plan = item.data(0, Qt.ItemDataRole.UserRole)
            if plan:
                plans_to_remove.append(plan)
        
        # Remove from internal list
        for plan in plans_to_remove:
            if plan in self._plans:
                self._plans.remove(plan)
        
        self._populate_tree()

    def _remove_plan_at(self, index: int) -> None:
        self._plans.pop(index)
        self._populate_tree()

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
        self._plans.extend(plans)
        self._populate_tree()
        self._drop_zone._label.setText("Drop Footage Here\nAccepts folders and files")
        self._log(f"Scan complete: {len(plans)} new clip(s) detected.")

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
        
        if self._engine.last_report_path:
            self._btn_view_report.setVisible(True)

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

    def _on_launch_architect(self) -> None:
        """Launch the visual rule builder and apply the result."""
        from ramses_ingest.architect import NamingArchitectDialog
        from ramses_ingest.matcher import NamingRule
        
        dlg = NamingArchitectDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            regex = dlg.get_final_regex()
            if regex:
                # Add to engine's rules and persist
                new_rule = NamingRule(pattern=regex)
                self._engine.rules.insert(0, new_rule)
                save_rules(self._engine.rules, DEFAULT_RULES_PATH, studio_name=self._engine.studio_name)
                
                # Refresh UI
                self._rule_combo.clear()
                self._rule_combo.addItem("Auto-detect")
                self._populate_rule_combo()
                self._rule_combo.setCurrentIndex(1) # Select the newly created rule
                self._log(f"New rule created via Architect: {regex}")

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
