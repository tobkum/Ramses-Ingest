# -*- coding: utf-8 -*-
"""PySide6 GUI for Ramses Ingest — dark professional theme matching Ramses-Fusion."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QCheckBox,
    QTextEdit,
    QProgressBar,
    QFrame,
    QDialog,
    QLineEdit,
    QSplitter,
    QHeaderView,
    QSizePolicy,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QStyledItemDelegate,
    QAbstractItemView,
    QMenu,
    QGroupBox,
    QScrollArea,
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
        fast_verify: bool = False,
        dry_run: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._plans = plans
        self._thumbnails = thumbnails
        self._proxies = proxies
        self._update_status = update_status
        self._fast_verify = fast_verify
        self._dry_run = dry_run
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
                fast_verify=self._fast_verify,
                dry_run=self._dry_run,
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
            "ready": "#4ec9b0",  # Green
            "warning": "#f39c12",  # Yellow/Orange
            "error": "#f44747",  # Red
            "pending": "#666666",  # Gray
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
        self.resize(1400, 800)  # Increased from 1200x700

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
        """Build professional 3-panel master-detail layout (ShotGrid-style)"""
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ═══════════════════════════════════════════════════════════════════════
        # HEADER BAR - Minimal (Project + Step + Studio + Status)
        # ═══════════════════════════════════════════════════════════════════════
        header = QFrame()
        header.setStyleSheet(
            "background-color: #1e1e1e; border-radius: 4px; padding: 6px;"
        )
        header_lay = QHBoxLayout(header)
        header_lay.setContentsMargins(8, 4, 8, 4)
        header_lay.setSpacing(12)

        # Status orb
        self._status_orb = QFrame()
        self._status_orb.setObjectName("statusOrb")
        self._status_orb.setStyleSheet(
            "background-color: #f44747; border: 1px solid rgba(255,255,255,0.1);"
        )
        header_lay.addWidget(self._status_orb)

        self._status_label = QLabel("OFFLINE")
        self._status_label.setObjectName("statusDisconnected")
        self._status_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        header_lay.addWidget(self._status_label)

        header_lay.addWidget(QLabel(" | "))

        # Project
        header_lay.addWidget(QLabel("Project:"))
        self._project_combo = QComboBox()
        self._project_combo.setMinimumWidth(120)
        self._project_combo.addItem("—")
        header_lay.addWidget(self._project_combo)

        # Step
        header_lay.addWidget(QLabel("Step:"))
        self._step_combo = QComboBox()
        self._step_combo.setMinimumWidth(100)
        self._step_combo.addItem("PLATE")
        self._step_combo.currentTextChanged.connect(self._on_step_changed)
        header_lay.addWidget(self._step_combo)

        header_lay.addStretch()

        # Studio
        header_lay.addWidget(QLabel("Studio:"))
        self._studio_edit = QLineEdit(self._engine.studio_name)
        self._studio_edit.setMaximumWidth(140)
        self._studio_edit.textChanged.connect(self._on_studio_changed)
        header_lay.addWidget(self._studio_edit)

        root.addWidget(header)

        # ═══════════════════════════════════════════════════════════════════════
        # MAIN CONTENT - 3-Panel Splitter Layout
        # ═══════════════════════════════════════════════════════════════════════
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        # ───────────────────────────────────────────────────────────────────────
        # LEFT PANEL: Filter Sidebar (20%)
        # ───────────────────────────────────────────────────────────────────────
        left_panel = QFrame()
        left_panel.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
        left_panel.setMinimumWidth(160)
        left_panel.setMaximumWidth(220)
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(10, 10, 10, 10)
        left_lay.setSpacing(8)

        # Search box
        search_label = QLabel("QUICK FILTER")
        search_label.setStyleSheet("color: #888; font-size: 9px; font-weight: bold;")
        left_lay.addWidget(search_label)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍 Search...")
        self._search_edit.textChanged.connect(self._on_search_changed)
        left_lay.addWidget(self._search_edit)

        left_lay.addSpacing(8)

        # Status filters
        status_label = QLabel("STATUS")
        status_label.setStyleSheet("color: #888; font-size: 9px; font-weight: bold;")
        left_lay.addWidget(status_label)

        self._filter_all = QPushButton("● All (0)")
        self._filter_all.setCheckable(True)
        self._filter_all.setChecked(True)
        self._filter_all.clicked.connect(lambda: self._apply_filter("all"))
        left_lay.addWidget(self._filter_all)

        self._filter_ready = QPushButton("● Ready (0)")
        self._filter_ready.setCheckable(True)
        self._filter_ready.setStyleSheet(
            "QPushButton { text-align: left; color: #4ec9b0; }"
        )
        self._filter_ready.clicked.connect(lambda: self._apply_filter("ready"))
        left_lay.addWidget(self._filter_ready)

        self._filter_warning = QPushButton("● Warnings (0)")
        self._filter_warning.setCheckable(True)
        self._filter_warning.setStyleSheet(
            "QPushButton { text-align: left; color: #f39c12; }"
        )
        self._filter_warning.clicked.connect(lambda: self._apply_filter("warning"))
        left_lay.addWidget(self._filter_warning)

        self._filter_error = QPushButton("● Errors (0)")
        self._filter_error.setCheckable(True)
        self._filter_error.setStyleSheet(
            "QPushButton { text-align: left; color: #f44747; }"
        )
        self._filter_error.clicked.connect(lambda: self._apply_filter("error"))
        left_lay.addWidget(self._filter_error)

        left_lay.addSpacing(8)

        # Type filters
        type_label = QLabel("TYPE")
        type_label.setStyleSheet("color: #888; font-size: 9px; font-weight: bold;")
        left_lay.addWidget(type_label)

        self._chk_sequences = QCheckBox("Sequences")
        self._chk_sequences.setChecked(True)
        self._chk_sequences.stateChanged.connect(self._on_type_filter_changed)
        left_lay.addWidget(self._chk_sequences)

        self._chk_movies = QCheckBox("Movies")
        self._chk_movies.setChecked(True)
        self._chk_movies.stateChanged.connect(self._on_type_filter_changed)
        left_lay.addWidget(self._chk_movies)

        left_lay.addStretch()

        # Advanced options button (moved here)
        btn_options = QPushButton("⚙ Options...")
        btn_options.clicked.connect(self._show_advanced_options)
        left_lay.addWidget(btn_options)

        main_splitter.addWidget(left_panel)

        # ───────────────────────────────────────────────────────────────────────
        # CENTER PANEL: Clip Table (60%)
        # ───────────────────────────────────────────────────────────────────────
        center_panel = QWidget()
        center_lay = QVBoxLayout(center_panel)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(4)

        # Drop zone (compact)
        self._drop_zone = DropZone()
        self._drop_zone.setMinimumHeight(60)
        self._drop_zone.setMaximumHeight(80)
        self._drop_zone.paths_dropped.connect(self._on_drop)
        center_lay.addWidget(self._drop_zone)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ["", "Filename", "Shot", "Ver", "Seq", "Frames", "Res", "Status"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemChanged.connect(self._on_table_item_changed)

        # Set column widths
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 28)  # Checkbox
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Filename
        for col in [2, 3, 4, 5, 6]:  # Shot, Ver, Seq, Frames, Res
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(col, 60 if col == 3 else 80)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(7, 55)  # Status (dot)

        # Set delegate for inline editing
        self._table.setItemDelegateForColumn(
            2, EditableDelegate(self._table)
        )  # Shot column

        center_lay.addWidget(self._table, 1)

        main_splitter.addWidget(center_panel)

        # ───────────────────────────────────────────────────────────────────────
        # RIGHT PANEL: Detail Panel (20%)
        # ───────────────────────────────────────────────────────────────────────
        right_panel = QFrame()
        right_panel.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
        right_panel.setMinimumWidth(250)
        right_panel.setMaximumWidth(450)
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(10, 10, 10, 10)
        right_lay.setSpacing(8)

        detail_label = QLabel("SELECTION DETAILS")
        detail_label.setStyleSheet("color: #888; font-size: 9px; font-weight: bold;")
        right_lay.addWidget(detail_label)

        self._detail_widget = QTextEdit()
        self._detail_widget.setReadOnly(True)
        self._detail_widget.setMaximumHeight(200)
        self._detail_widget.setPlaceholderText("Select a clip to view details...")
        right_lay.addWidget(self._detail_widget)

        right_lay.addSpacing(8)

        # Override controls
        override_label = QLabel("OVERRIDE")
        override_label.setStyleSheet("color: #888; font-size: 9px; font-weight: bold;")
        right_lay.addWidget(override_label)

        right_lay.addWidget(QLabel("Shot ID:"))
        self._override_shot = QLineEdit()
        self._override_shot.setPlaceholderText("Override shot ID...")
        self._override_shot.setEnabled(False)
        self._override_shot.textChanged.connect(self._on_override_changed)
        right_lay.addWidget(self._override_shot)

        right_lay.addWidget(QLabel("Sequence ID:"))
        self._override_seq = QLineEdit()
        self._override_seq.setPlaceholderText("Override sequence ID...")
        self._override_seq.setEnabled(False)
        self._override_seq.textChanged.connect(self._on_override_seq_changed)
        right_lay.addWidget(self._override_seq)

        right_lay.addStretch()
        main_splitter.addWidget(right_panel)

        # Set splitter proportions (20% | 50% | 30%)
        main_splitter.setSizes([200, 500, 300])

        root.addWidget(main_splitter, 1)

        # ═══════════════════════════════════════════════════════════════════════
        # BOTTOM ACTION BAR
        # ═══════════════════════════════════════════════════════════════════════
        action_bar = QFrame()
        action_bar.setStyleSheet(
            "background-color: #1e1e1e; border-radius: 4px; padding: 6px;"
        )
        action_bar_lay = QHBoxLayout(action_bar)
        action_bar_lay.setContentsMargins(8, 4, 8, 4)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.clicked.connect(self._on_clear)
        action_bar_lay.addWidget(self._btn_clear)

        self._summary_label = QLabel("No delivery loaded.")
        self._summary_label.setObjectName("mutedLabel")
        action_bar_lay.addWidget(self._summary_label)

        action_bar_lay.addStretch()

        self._btn_view_report = QPushButton("View Report")
        self._btn_view_report.clicked.connect(self._on_view_report)
        self._btn_view_report.setVisible(False)
        self._btn_view_report.setStyleSheet("color: #4ec9b0; font-weight: bold;")
        action_bar_lay.addWidget(self._btn_view_report)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_cancel.setVisible(False)
        action_bar_lay.addWidget(self._btn_cancel)

        self._btn_ingest = QPushButton("Execute")
        self._btn_ingest.setObjectName("ingestButton")
        self._btn_ingest.setEnabled(False)
        self._btn_ingest.clicked.connect(self._on_ingest)
        self._btn_ingest.setMinimumWidth(120)
        self._btn_ingest.setMinimumHeight(36)
        action_bar_lay.addWidget(self._btn_ingest)

        root.addWidget(action_bar)

        # Progress bar (hidden by default)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # Log panel (collapsible)
        self._log_toggle = QPushButton("[ + ] Log")
        self._log_toggle.setMaximumWidth(80)
        self._log_toggle.clicked.connect(self._toggle_log)
        root.addWidget(self._log_toggle)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumHeight(160)
        self._log_edit.setVisible(False)
        root.addWidget(self._log_edit)

        # Keyboard shortcuts
        self._setup_shortcuts()

        # Initialize naming rule combo
        self._rule_combo = QComboBox()
        self._rule_combo.addItem("Auto-detect")
        self._populate_rule_combo()

        # Initialize options checkboxes
        self._chk_thumb = QCheckBox()
        self._chk_thumb.setChecked(True)
        self._chk_proxy = QCheckBox()
        self._chk_proxy.setChecked(False)
        self._chk_status = QCheckBox()
        self._chk_status.setChecked(True)
        self._chk_fast_verify = QCheckBox()
        self._chk_fast_verify.setChecked(False)
        self._chk_dry_run = QCheckBox()
        self._chk_dry_run.setChecked(False)
        self._ocio_in = QComboBox()
        self._ocio_in.addItems(["sRGB", "Linear", "Rec.709", "LogC", "S-Log3", "V-Log"])
        self._btn_edl = QPushButton("Load EDL...")

    # -- Professional UI Methods ---------------------------------------------

    def _open_folder(self, path: str) -> None:
        """Open folder in system file manager (cross-platform)"""
        import platform
        import subprocess

        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", path])
            else:  # Linux
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self._log(f"Failed to open folder: {e}")

    def _setup_shortcuts(self) -> None:
        """Setup keyboard shortcuts for professional workflow"""
        from PySide6.QtGui import QShortcut, QKeySequence

        # Ctrl+F = Focus search
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self._search_edit.setFocus())

        # Enter = Execute (if enabled)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, self._on_shortcut_execute)

        # Escape = Clear selection
        QShortcut(
            QKeySequence(Qt.Key.Key_Escape), self, lambda: self._table.clearSelection()
        )

        # Delete = Remove selected clips
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self._on_remove_selected)

    def _on_shortcut_execute(self) -> None:
        """Execute ingest via keyboard shortcut"""
        if self._btn_ingest.isEnabled():
            self._on_ingest()

    def _apply_filter(self, filter_type: str) -> None:
        """Apply status filter (all/ready/warning/error)"""
        self._current_filter_status = filter_type

        # Update button states
        self._filter_all.setChecked(filter_type == "all")
        self._filter_ready.setChecked(filter_type == "ready")
        self._filter_warning.setChecked(filter_type == "warning")
        self._filter_error.setChecked(filter_type == "error")

        # Apply filter to table
        self._apply_table_filters()

    def _on_type_filter_changed(self) -> None:
        """Apply type filters (sequences/movies)"""
        self._apply_table_filters()

    def _on_search_changed(self, text: str) -> None:
        """Filter table rows by search text"""
        self._apply_table_filters()

    def _apply_table_filters(self) -> None:
        """Apply all active filters to table rows"""
        for row in range(self._table.rowCount()):
            show = True

            # Status filter
            if self._current_filter_status != "all":
                # Check status column
                status_item = self._table.cellWidget(row, 7)  # Status column (was 6)
                if status_item and hasattr(status_item, "toolTip"):
                    status = status_item.toolTip().lower()
                    if self._current_filter_status not in status:
                        show = False

            # Type filter
            if show:
                # Check if it's a sequence or movie
                if row < len(self._plans):
                    is_sequence = self._plans[row].match.clip.is_sequence
                    if is_sequence and not self._chk_sequences.isChecked():
                        show = False
                    elif not is_sequence and not self._chk_movies.isChecked():
                        show = False

            # Search filter
            if show and self._search_edit.text():
                search = self._search_edit.text().lower()
                shot_item = self._table.item(row, 2)  # Shot column
                seq_item = self._table.item(row, 3)  # Seq column
                file_item = self._table.item(row, 1)  # Filename column

                match = False
                if shot_item and search in shot_item.text().lower():
                    match = True
                if seq_item and search in seq_item.text().lower():
                    match = True
                if file_item and search in file_item.text().lower():
                    match = True

                if not match:
                    show = False

            self._table.setRowHidden(row, not show)

    def _on_selection_changed(self) -> None:
        """Update detail panel when selection changes"""
        selected = self._table.selectedItems()
        if not selected:
            self._detail_widget.clear()
            self._override_shot.clear()
            self._override_shot.setEnabled(False)
            self._override_seq.clear()
            self._override_seq.setEnabled(False)
            self._selected_plan_idx = -1
            return

        # Get the first selected row
        row = self._table.currentRow()
        if row < 0 or row >= len(self._plans):
            return

        self._selected_plan_idx = row
        plan = self._plans[row]

        # Update detail panel
        details = []
        details.append(
            f"<b>Clip:</b> {plan.match.clip.base_name}.{plan.match.clip.extension}"
        )
        details.append(f"<b>Shot:</b> {plan.shot_id or '—'}")
        details.append(f"<b>Sequence:</b> {plan.sequence_id or '—'}")

        # Proper frame count for movies
        fc = (
            plan.match.clip.frame_count
            if plan.match.clip.is_sequence
            else plan.media_info.frame_count
        )
        if not plan.match.clip.is_sequence and fc <= 0:
            fc = 1  # Fallback

        details.append(f"<b>Frames:</b> {fc}")

        if plan.media_info.width and plan.media_info.height:
            details.append(
                f"<b>Resolution:</b> {plan.media_info.width}x{plan.media_info.height}"
            )
        if plan.media_info.fps:
            details.append(f"<b>FPS:</b> {plan.media_info.fps:.2f}")
        if plan.media_info.codec:
            details.append(f"<b>Codec:</b> {plan.media_info.codec}")
        if plan.media_info.color_space:
            details.append(f"<b>Colorspace:</b> {plan.media_info.color_space}")

        if plan.error:
            details.append(f"<br><b style='color:#f44747'>Error:</b> {plan.error}")

        if plan.match.clip.missing_frames:
            details.append(
                f"<br><b style='color:#f39c12'>Missing Frames:</b> {len(plan.match.clip.missing_frames)}"
            )

        if plan.target_publish_dir:
            details.append(
                f"<br><b style='color:#00bff3; font-size:10px;'>DESTINATION PATH:</b><br><code style='color:#aaa; font-size:10px;'>{plan.target_publish_dir}</code>"
            )

        self._detail_widget.setHtml("<br>".join(details))

        # Enable override
        self._override_shot.setEnabled(True)
        if plan.shot_id:
            self._override_shot.setText(plan.shot_id)

        self._override_seq.setEnabled(True)
        self._override_seq.setText(plan.sequence_id or "")

    def _on_override_changed(self, text: str) -> None:
        """Apply shot ID override to selected plan"""
        if self._selected_plan_idx >= 0 and self._selected_plan_idx < len(self._plans):
            plan = self._plans[self._selected_plan_idx]
            plan.shot_id = text

            # Re-resolve paths for this plan to update versioning
            self._resolve_all_paths()

            # Update table with signals blocked to prevent race condition
            item = self._table.item(self._selected_plan_idx, 2)
            if item:
                blocked = self._table.blockSignals(True)
                item.setText(text)

                # Update Version column too
                ver_item = self._table.item(self._selected_plan_idx, 3)
                if ver_item:
                    ver_item.setText(f"v{plan.version:03d}")

                self._table.blockSignals(blocked)
            self._update_summary()

    def _on_override_seq_changed(self, text: str) -> None:
        """Apply sequence ID override to selected plan"""
        if self._selected_plan_idx >= 0 and self._selected_plan_idx < len(self._plans):
            plan = self._plans[self._selected_plan_idx]
            plan.sequence_id = text

            # Update table
            item = self._table.item(self._selected_plan_idx, 4)  # Seq column
            if item:
                blocked = self._table.blockSignals(True)
                item.setText(text or "—")
                self._table.blockSignals(blocked)
            self._update_summary()

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle inline edits in table"""
        if item.column() == 2:  # Shot column
            row = item.row()
            if row < len(self._plans):
                self._plans[row].shot_id = item.text()

                # Re-resolve paths to update versioning
                self._resolve_all_paths()

                # Update Version column
                ver_item = self._table.item(row, 3)
                if ver_item:
                    blocked = self._table.blockSignals(True)
                    ver_item.setText(f"v{self._plans[row].version:03d}")
                    self._table.blockSignals(blocked)

                self._update_summary()

    def _on_remove_selected(self) -> None:
        """Remove selected clips from table"""
        selected_rows = sorted(
            set(item.row() for item in self._table.selectedItems()), reverse=True
        )
        for row in selected_rows:
            if row < len(self._plans):
                del self._plans[row]
            self._table.removeRow(row)

        self._update_summary()
        self._update_filter_counts()

    def _show_advanced_options(self) -> None:
        """Show advanced options dialog"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Advanced Options")
        dialog.resize(400, 300)

        lay = QVBoxLayout(dialog)

        # Thumbnails
        chk_thumb = QCheckBox("Generate thumbnails")
        chk_thumb.setChecked(self._chk_thumb.isChecked())
        lay.addWidget(chk_thumb)

        # Proxies
        chk_proxy = QCheckBox("Generate video proxies")
        chk_proxy.setChecked(self._chk_proxy.isChecked())
        lay.addWidget(chk_proxy)

        # Status update
        chk_status = QCheckBox("Set step status to OK on success")
        chk_status.setChecked(self._chk_status.isChecked())
        lay.addWidget(chk_status)

        # Fast Verify
        chk_fast = QCheckBox("Fast Verify (MD5 first/mid/last only)")
        chk_fast.setToolTip(
            "Speeds up ingest by only verifying 3 frames per sequence instead of all."
        )
        chk_fast.setChecked(self._chk_fast_verify.isChecked())
        lay.addWidget(chk_fast)

        # Dry Run
        chk_dry = QCheckBox("Dry Run (Simulation mode)")
        chk_dry.setToolTip("Runs the entire process but skips actual file copying.")
        chk_dry.setChecked(self._chk_dry_run.isChecked())
        lay.addWidget(chk_dry)

        lay.addSpacing(10)

        # OCIO
        ocio_group = QGroupBox("Color Management (OCIO)")
        ocio_lay = QVBoxLayout(ocio_group)

        ocio_lay.addWidget(QLabel("Source Colorspace:"))
        ocio_in = QComboBox()
        ocio_in.addItems(["sRGB", "Linear", "Rec.709", "LogC", "S-Log3", "V-Log"])
        ocio_in.setCurrentText(self._ocio_in.currentText())
        ocio_in.currentTextChanged.connect(self._on_ocio_in_changed)
        ocio_lay.addWidget(ocio_in)

        lay.addWidget(ocio_group)

        lay.addSpacing(10)

        # Naming rules
        rule_group = QGroupBox("Naming Rules")
        rule_lay = QVBoxLayout(rule_group)

        rule_combo = QComboBox()
        rule_combo.addItem("Auto-detect")
        # Copy existing rules to dialog
        for i in range(1, self._rule_combo.count()):
            rule_combo.addItem(self._rule_combo.itemText(i))
        rule_combo.setCurrentIndex(self._rule_combo.currentIndex())
        rule_lay.addWidget(rule_combo)

        rule_btns = QHBoxLayout()
        btn_architect = QPushButton("Architect...")
        btn_architect.clicked.connect(self._on_launch_architect)
        rule_btns.addWidget(btn_architect)

        btn_edl = QPushButton("Load EDL...")
        btn_edl.clicked.connect(self._on_load_edl)
        rule_btns.addWidget(btn_edl)

        btn_edit = QPushButton("Edit Rules...")
        btn_edit.clicked.connect(self._on_edit_rules)
        rule_btns.addWidget(btn_edit)

        rule_lay.addLayout(rule_btns)

        lay.addWidget(rule_group)

        lay.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(
            lambda: self._apply_options(
                chk_thumb,
                chk_proxy,
                chk_status,
                chk_fast,
                chk_dry,
                ocio_in,
                rule_combo,
                dialog,
            )
        )
        btn_row.addWidget(btn_apply)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        dialog.exec()

    def _apply_options(
        self,
        chk_thumb,
        chk_proxy,
        chk_status,
        chk_fast,
        chk_dry,
        ocio_in,
        rule_combo,
        dialog,
    ):
        """Apply options from dialog"""
        self._chk_thumb.setChecked(chk_thumb.isChecked())
        self._chk_proxy.setChecked(chk_proxy.isChecked())
        self._chk_status.setChecked(chk_status.isChecked())
        self._chk_fast_verify.setChecked(chk_fast.isChecked())
        self._chk_dry_run.setChecked(chk_dry.isChecked())
        self._ocio_in.setCurrentText(ocio_in.currentText())
        self._rule_combo.setCurrentIndex(rule_combo.currentIndex())
        self._update_summary()
        dialog.accept()

    def _update_filter_counts(self) -> None:
        """Update the count badges on filter buttons"""
        if not hasattr(self, "_plans"):
            return

        total = len(self._plans)
        ready = sum(1 for p in self._plans if p.can_execute and not p.error)
        warning = sum(
            1
            for p in self._plans
            if p.can_execute and p.error and "warning" in p.error.lower()
        )
        error = sum(
            1
            for p in self._plans
            if not p.can_execute or (p.error and "error" in p.error.lower())
        )

        self._filter_all.setText(f"● All ({total})")
        self._filter_ready.setText(f"● Ready ({ready})")
        self._filter_warning.setText(f"● Warnings ({warning})")
        self._filter_error.setText(f"● Errors ({error})")

    def _populate_table(self) -> None:
        """Populate the table with current plans (replaces _populate_tree)"""
        # Block signals to prevent triggering itemChanged during population
        blocked = self._table.blockSignals(True)

        self._table.setRowCount(0)
        self._table.setRowCount(len(self._plans))

        for idx, plan in enumerate(self._plans):
            clip = plan.match.clip

            # Column 0: Checkbox
            chk = QCheckBox()
            chk.setChecked(plan.enabled)
            chk.stateChanged.connect(self._on_checkbox_changed)
            chk_widget = QWidget()
            chk_lay = QHBoxLayout(chk_widget)
            chk_lay.addWidget(chk)
            chk_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_lay.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(idx, 0, chk_widget)

            # Column 1: Filename
            filename = f"{clip.base_name}.{clip.extension}"
            if clip.is_sequence:
                filename = f"{clip.base_name}.####.{clip.extension}"
            file_item = QTableWidgetItem(filename)
            file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(idx, 1, file_item)

            # Column 2: Shot (editable)
            shot_item = QTableWidgetItem(plan.shot_id or "")
            if not plan.shot_id:
                shot_item.setForeground(QColor("#f44747"))  # Red if missing
            self._table.setItem(idx, 2, shot_item)

            # Column 3: Version (new)
            ver_item = QTableWidgetItem(f"v{plan.version:03d}")
            ver_item.setFlags(ver_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            ver_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(idx, 3, ver_item)

            # Column 4: Sequence
            seq_item = QTableWidgetItem(plan.sequence_id or "—")
            seq_item.setFlags(seq_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(idx, 4, seq_item)

            # Column 5: Frames
            if clip.is_sequence:
                fc = clip.frame_count
            else:
                fc = (
                    plan.media_info.frame_count
                    if plan.media_info.frame_count > 0
                    else 1
                )

            frames_item = QTableWidgetItem(str(fc))
            frames_item.setFlags(frames_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(idx, 5, frames_item)

            # Column 6: Resolution
            res_text = "—"
            if plan.media_info.width and plan.media_info.height:
                res_text = f"{plan.media_info.width}x{plan.media_info.height}"
            res_item = QTableWidgetItem(res_text)
            res_item.setFlags(res_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(idx, 6, res_item)

            # Column 7: Status (color dot)
            status = "pending"
            if plan.can_execute and not plan.error:
                status = "ready"
            elif plan.error:
                if "warning" in plan.error.lower():
                    status = "warning"
                else:
                    status = "error"
            elif plan.is_duplicate:
                status = "duplicate"

            status_indicator = StatusIndicator(status)
            self._table.setCellWidget(idx, 7, status_indicator)

            # Set row height for better readability
            self._table.setRowHeight(idx, 28)

        # Re-enable signals
        self._table.blockSignals(blocked)

        # Update filter counts
        self._update_filter_counts()
        self._update_summary()

    def _on_checkbox_changed(self, state: int) -> None:
        """Handle checkbox state changes"""
        # Find which row changed
        sender = self.sender()
        for row in range(self._table.rowCount()):
            chk_widget = self._table.cellWidget(row, 0)
            if chk_widget and chk_widget.findChild(QCheckBox) == sender:
                if row < len(self._plans):
                    self._plans[row].enabled = state == Qt.CheckState.Checked.value
                break

        self._update_summary()

    def _on_context_override_shot(self) -> None:
        """Override shot ID for selected clips"""
        from PySide6.QtWidgets import QInputDialog

        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        if not selected_rows:
            return

        shot_id, ok = QInputDialog.getText(
            self, "Override Shot ID", f"Enter shot ID for {len(selected_rows)} clip(s):"
        )

        if ok and shot_id:
            for row in selected_rows:
                if row < len(self._plans):
                    self._plans[row].shot_id = shot_id
                    item = self._table.item(row, 2)
                    if item:
                        item.setText(shot_id)

            self._update_summary()

    def _on_context_override_seq(self) -> None:
        """Override sequence ID for selected clips"""
        from PySide6.QtWidgets import QInputDialog

        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        if not selected_rows:
            return

        seq_id, ok = QInputDialog.getText(
            self,
            "Override Sequence ID",
            f"Enter sequence ID for {len(selected_rows)} clip(s):",
        )

        if ok:
            for row in selected_rows:
                if row < len(self._plans):
                    self._plans[row].sequence_id = seq_id
                    item = self._table.item(row, 4)  # Seq column
                    if item:
                        item.setText(seq_id or "—")

            self._update_summary()

    def _on_context_skip(self) -> None:
        """Skip selected clips (uncheck them)"""
        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        for row in selected_rows:
            if row < len(self._plans):
                self._plans[row].enabled = False
                chk_widget = self._table.cellWidget(row, 0)
                if chk_widget:
                    chk = chk_widget.findChild(QCheckBox)
                    if chk:
                        chk.setChecked(False)

        self._update_summary()

    # -- Helpers -------------------------------------------------------------

    def _log(self, msg: str) -> None:
        self._log_edit.append(msg)
        sb = self._log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

        def _resolve_all_paths(self) -> None:
            """Update target paths and version numbers for all plans."""
            if not self._plans:
                return
                
            from ramses_ingest.publisher import resolve_paths, resolve_paths_from_daemon, check_for_path_collisions
            
            # Reset errors before re-calculating (clears old collisions)
            for p in self._plans:
                if "COLLISION" in (p.error or ""):
                    p.error = "" 
    
            # 1. Try resolving via daemon if connected
            if self._engine.connected and self._engine._shot_objects:
                resolve_paths_from_daemon(self._plans, self._engine._shot_objects)
                
            # 2. Use project path as fallback for any unresolved plans
            if self._engine.project_path:
                unresolved = [p for p in self._plans if not p.target_publish_dir]
                if unresolved:
                    resolve_paths(unresolved, self._engine.project_path)
    
            # 3. Check for collisions in the new state
            check_for_path_collisions(self._plans)
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
            self._project_combo.clear()
            self._project_combo.addItem(f"{pid} - {pname}")
            self._project_combo.setCurrentIndex(0)

            # Note: Standards display removed from minimal header in professional UI
            # fps = self._engine._project_fps
            # w = self._engine._project_width
            # h = self._engine._project_height

            # Populate steps
            self._step_combo.clear()
            for s in self._engine.steps:
                self._step_combo.addItem(s)
            if "PLATE" in self._engine.steps:
                self._step_combo.setCurrentText("PLATE")
        else:
            self._status_orb.setStyleSheet(
                "background-color: #f44747; border-radius: 6px;"
            )
            self._status_orb.setGraphicsEffect(None)
            self._status_label.setText("OFFLINE")
            self._status_label.setObjectName("statusDisconnected")
            self._project_combo.clear()
            self._project_combo.addItem("— (Connection Required)")
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

        is_dry = self._chk_dry_run.isChecked()
        btn_text = "Simulate" if is_dry else "Ingest"
        self._btn_ingest.setText(f"{btn_text} {n_enabled}/{total}")

        # UI Polish: Change button style if simulating
        if is_dry:
            self._btn_ingest.setStyleSheet(
                "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f39c12, stop:1 #d35400); color: white;"
            )
        else:
            self._btn_ingest.setStyleSheet("")  # Reset to STYLESHEET default

        # Strict enforcement: Connection AND valid plans AND a defined pipeline step
        has_step = bool(self._step_combo.currentText())
        self._btn_ingest.setEnabled(
            n_enabled > 0 and self._engine.connected and has_step
        )

        if self._engine.connected and not has_step:
            self._btn_ingest.setToolTip(
                "No Shot Production steps found in this project. Ingest disabled."
            )
        else:
            self._btn_ingest.setToolTip("")

    def _get_enabled_plans(self) -> list[IngestPlan]:
        """Get list of plans that can be executed"""
        return [p for p in self._plans if p.can_execute]

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
        if self._engine.last_report_path and os.path.exists(
            self._engine.last_report_path
        ):
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
            # Re-resolve paths when step changes so Ver column updates
            if self._plans:
                self._resolve_all_paths()
                self._populate_table()
        else:
            self._engine.step_id = ""
            self._chk_status.setText("Set status to OK")

        self._update_summary()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Update the button summary when a checkbox is toggled."""
        if column == 0:
            self._update_summary()

    def _on_context_menu(self, pos) -> None:
        """Show context menu for selected clips"""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        # Get selected rows
        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        if not selected_rows:
            return

        menu = QMenu(self)

        # Actions
        act_override = QAction("Override Shot ID...", self)
        act_override.triggered.connect(self._on_context_override_shot)
        menu.addAction(act_override)

        act_override_seq = QAction("Override Sequence ID...", self)
        act_override_seq.triggered.connect(self._on_context_override_seq)
        menu.addAction(act_override_seq)

        act_skip = QAction("Skip Selected", self)
        act_skip.triggered.connect(self._on_context_skip)
        menu.addAction(act_skip)

        menu.addSeparator()

        # Single selection actions
        if len(selected_rows) == 1:
            row = selected_rows[0]
            if row < len(self._plans):
                plan = self._plans[row]

                act_src = QAction("Open Source Folder", self)
                act_src.triggered.connect(
                    lambda: self._open_folder(plan.match.clip.directory)
                )
                menu.addAction(act_src)

                if plan.target_publish_dir and os.path.exists(plan.target_publish_dir):
                    act_dst = QAction("Open Destination Folder", self)
                    act_dst.triggered.connect(
                        lambda: self._open_folder(plan.target_publish_dir)
                    )
                    menu.addAction(act_dst)

                menu.addSeparator()

        act_remove = QAction("Remove from List", self)
        act_remove.triggered.connect(self._on_remove_selected)
        menu.addAction(act_remove)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _remove_plan_at(self, index: int) -> None:
        self._plans.pop(index)
        self._populate_table()

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
        self._populate_table()
        self._drop_zone._label.setText("Drop Footage Here\nAccepts folders and files")
        self._log(f"Scan complete: {len(plans)} new clip(s) detected.")

    def _on_scan_error(self, msg: str) -> None:
        self._log(f"ERROR: {msg}")
        self._drop_zone._label.setText("Drop Footage Here\nAccepts folders and files")

    def _on_clear(self) -> None:
        self._plans.clear()
        self._table.setRowCount(0)
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
            fast_verify=self._chk_fast_verify.isChecked(),
            dry_run=self._chk_dry_run.isChecked(),
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
                save_rules(
                    self._engine.rules,
                    DEFAULT_RULES_PATH,
                    studio_name=self._engine.studio_name,
                )

                # Refresh UI
                self._rule_combo.clear()
                self._rule_combo.addItem("Auto-detect")
                self._populate_rule_combo()
                self._rule_combo.setCurrentIndex(1)  # Select the newly created rule
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
                plan.match.matched = True  # Force matched if EDL finds it
                plan.error = ""
                updated += 1

        if updated:
            self._log(f"  Mapped {updated} shot(s) from EDL.")
            self._populate_table()
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
