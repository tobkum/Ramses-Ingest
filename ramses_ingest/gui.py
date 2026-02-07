# -*- coding: utf-8 -*-
"""PySide6 GUI for Ramses Ingest — dark professional theme matching Ramses-Fusion."""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QUrl, QTimer
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
    background-color: transparent;
}

QLabel#headerLabel {
    font-size: 14px;
    font-weight: bold;
    color: #ffffff;
    letter-spacing: 1px;
    background-color: transparent;
}

QLabel#projectLabel {
    font-size: 12px;
    font-weight: bold;
    color: #ffffff;
    background-color: transparent;
}

QLabel#mutedLabel {
    color: #666666;
    background-color: transparent;
}

QLabel#statusConnected {
    color: #27ae60;
    font-weight: bold;
    background-color: transparent;
}

QLabel#statusDisconnected {
    color: #f44747;
    background-color: transparent;
}

/* --- Inputs --- */
QLineEdit {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 6px 12px;
    color: #ffffff;
}

QLineEdit:focus {
    border-color: #00bff3;
    background-color: #252526;
}

QTextEdit {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 8px;
    color: #ffffff;
}

QTextEdit:focus {
    border-color: #00bff3;
    background-color: #252526;
}

QComboBox {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 6px 12px;
}

QComboBox:hover {
    border-color: #444444;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QCheckBox {
    spacing: 8px;
    background-color: transparent;
    color: #e0e0e0;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #555555; /* Light grey border */
    background-color: #1e1e1e; /* Dark background for the box */
    border-radius: 3px; /* Slightly rounded corners */
}

QCheckBox::indicator:checked {
    background-color: #094771; /* Darker accent color when checked */
    border-color: #094771;
}

QCheckBox::indicator:hover {
    border-color: #00bff3; /* Accent color on hover */
}

QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #333333, stop:1 #2d2d2d);
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 6px 16px;
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

/* Secondary button style for less prominent actions */
QPushButton#secondaryButton {
    background: transparent;
    border: 1px solid #333333;
    color: #888888;
    padding: 4px 12px;
}

QPushButton#secondaryButton:hover {
    border-color: #555555;
    color: #cccccc;
}

QPushButton#ingestButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00bff3, stop:1 #0095c2);
    border: none;
    color: #ffffff;
    font-weight: bold;
    font-size: 13px;
    padding: 10px 32px;
    min-height: 40px;
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
    background-color: #2d2d2d;
    border: none;
    border-right: 1px solid #1a1a1a;
    border-bottom: 2px solid #444444;
    padding: 12px 8px;
    color: #aaaaaa;
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* --- Table --- */
QTableWidget {
    background-color: #181818;
    border: 1px solid #2d2d2d;
    gridline-color: #252526;
    border-radius: 4px;
    show-decoration-selected: 0;
    outline: none;
}

QTableWidget:focus {
    outline: none;
    border: 1px solid #2d2d2d;
}

QTableWidget::item {
    padding: 8px;
    border-bottom: 1px solid #252526;
    min-height: 42px;
}

QTableWidget::item:selected {
    background-color: rgba(0, 191, 243, 0.15);
    outline: none;
}

QTableWidget::item:selected:focus {
    background-color: rgba(0, 191, 243, 0.25);
}

/* --- Progress --- */
QProgressBar {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 4px;
    text-align: center;
    height: 12px;
    font-size: 10px;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #0a7fad;
    border-radius: 4px;
}

QFrame#dropZone {
    background-color: #1e1e1e;
    border: 2px dashed #333333;
    border-radius: 8px;
}

QFrame#dropZone:hover {
    border-color: #444444;
    background-color: #242424;
}

QFrame#dropZone[dragOver="true"] {
    border-color: #00bff3;
    background-color: #162633;
}

/* --- Group Box --- */
QGroupBox {
    background-color: #1e1e1e;
    border: 1px solid #333333;
    border-radius: 4px;
    margin-top: 10px; /* Space for the title */
    padding: 10px;
    color: #e0e0e0;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left; /* Position at the top left */
    padding: 0 5px;
    color: #cccccc;
    background-color: transparent; /* Ensure title background is transparent */
}
"""


# ---------------------------------------------------------------------------
# Logging Handler
# ---------------------------------------------------------------------------


class GuiLogHandler(logging.Handler):
    """Custom logging handler that redirects logs to the IngestWindow._log method."""

    def __init__(self, log_callback) -> None:
        super().__init__()
        self.log_callback = log_callback

    def emit(self, record) -> None:
        try:
            msg = self.handle_record(record)
            self.log_callback(msg)
        except Exception:
            self.handleError(record)

    def handle_record(self, record) -> str:
        """Simple format: LEVEL: Message"""
        return f"{record.levelname}: {record.getMessage()}"


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


class ConnectionWorker(QThread):
    """Connects to Ramses daemon in a background thread."""

    finished = Signal(bool)

    def __init__(self, engine: IngestEngine, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine

    def run(self) -> None:
        # No try/except needed as connect_ramses handles its own exceptions internally
        # and returns False on failure.
        ok = self._engine.connect_ramses()
        self.finished.emit(ok)


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
        self.setContentsMargins(0, 0, 0, 0)

    def set_status(self, status: str):
        """Update status color: ready=green, warning=yellow, error=red, pending=gray"""
        colors = {
            "ready": "#27ae60",  # Green (matches DAEMON ONLINE)
            "warning": "#f39c12",  # Yellow/Orange
            "error": "#f44747",  # Red
            "pending": "#666666",  # Gray
            "duplicate": "#999999",  # Light gray
        }
        color = colors.get(status, "#666666")
        self.setText("●")
        self.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold; padding: 0; margin: 0;")
        self.setToolTip(status.title())


class EditableDelegate(QStyledItemDelegate):
    """Delegate for inline editing of table cells"""

    def createEditor(self, parent, option, index):
        """Create editor for shot ID override"""
        if index.column() == 3:  # Shot column (swapped with Ver)
            editor = QLineEdit(parent)
            editor.setStyleSheet("background: #2d2d30; border: 1px solid #094771;")
            return editor
        return super().createEditor(parent, option, index)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------


class IngestWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ramses Ingest")
        self.resize(1400, 800)  # Increased from 1200x700

        self._engine = IngestEngine()
        self._plans: list[IngestPlan] = []
        self._scan_worker: ScanWorker | None = None
        self._ingest_worker: IngestWorker | None = None
        self._connection_worker: ConnectionWorker | None = None
        self._current_filter_status = "all"  # For filter sidebar
        self._selected_plan: IngestPlan | None = None  # For detail panel

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(5000) # Check every 5 seconds
        self._reconnect_timer.timeout.connect(self._try_connect)

        # Initialize logging handler
        self._setup_logging()

        # Debounce timer for expensive path resolution (e.g. while typing overrides)
        self._resolve_timer = QTimer(self)
        self._resolve_timer.setSingleShot(True)
        self._resolve_timer.setInterval(300)  # 300ms debounce
        self._resolve_timer.timeout.connect(self._on_resolve_timeout)

        self._build_ui()
        # Connect asynchronously on startup
        QTimer.singleShot(100, self._try_connect)

    def _setup_logging(self) -> None:
        """Redirect ramses_ingest package logs to the GUI log panel."""
        handler = GuiLogHandler(self._log)
        logger = logging.getLogger("ramses_ingest")
        logger.addHandler(handler)
        # Ensure we capture at least INFO level
        if logger.level == logging.NOTSET or logger.level > logging.INFO:
            logger.setLevel(logging.INFO)

    def _on_resolve_timeout(self) -> None:
        """Called after debounce period to resolve paths and update UI."""
        self._resolve_all_paths()
        self._populate_table()

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

        self._status_label = QLabel("OFFLINE")
        self._status_label.setObjectName("statusDisconnected")
        self._status_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        header_lay.addWidget(self._status_label)

        self._btn_reconnect = QPushButton("Reconnect")
        self._btn_reconnect.setFixedWidth(80)
        self._btn_reconnect.setFixedHeight(22)
        self._btn_reconnect.setStyleSheet("font-size: 9px; padding: 2px;")
        self._btn_reconnect.clicked.connect(self._try_connect)
        self._btn_reconnect.setVisible(False)
        header_lay.addWidget(self._btn_reconnect)

        self._btn_refresh = QPushButton("↻ Refresh")
        self._btn_refresh.setFixedWidth(70)
        self._btn_refresh.setFixedHeight(22)
        self._btn_refresh.setStyleSheet("font-size: 9px; padding: 2px;")
        self._btn_refresh.clicked.connect(self._try_connect)
        self._btn_refresh.setVisible(False)  # Hidden until connected
        header_lay.addWidget(self._btn_refresh)
        header_lay.addWidget(QLabel(" | "))

        # Project
        header_lay.addWidget(QLabel("Project:"))
        self._project_label_display = QLabel("—")
        self._project_label_display.setStyleSheet("color: #ffffff; font-weight: 800; font-size: 13px;")
        header_lay.addWidget(self._project_label_display)

        # Step
        header_lay.addWidget(QLabel("Step:"))
        self._step_combo = QComboBox()
        self._step_combo.setMinimumWidth(100)
        self._step_combo.addItem("PLATE")
        self._step_combo.currentTextChanged.connect(self._on_step_changed)
        header_lay.addWidget(self._step_combo)

        header_lay.addSpacing(10)

        # Standards
        self._standards_label = QLabel("—")
        self._standards_label.setStyleSheet("color: #888; font-family: 'Consolas', monospace; font-size: 10px;")
        header_lay.addWidget(self._standards_label)

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
            "QPushButton { text-align: left; color: #27ae60; }"
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
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels(
            ["", "Filename", "Ver", "Shot", "Seq", "Frames", "Res", "FPS", "Status"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(42)
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
        for col in [2, 3, 4, 5, 6, 7]:  # Ver, Shot, Seq, Frames, Res, FPS
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(col, 60 if col in [2, 7] else 80)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(8, 55)  # Status (dot)

        # Set delegate for inline editing
        self._table.setItemDelegateForColumn(
            3, EditableDelegate(self._table)
        )  # Shot column (now index 3)

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
        self._detail_widget.setMinimumHeight(300)
        self._detail_widget.setPlaceholderText("Select a clip to view details...")
        self._detail_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_lay.addWidget(self._detail_widget)

        right_lay.addSpacing(20)

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
        self._btn_clear.setObjectName("secondaryButton")
        self._btn_clear.setToolTip("Clear all clips from the table")
        self._btn_clear.clicked.connect(self._on_clear)
        action_bar_lay.addWidget(self._btn_clear)

        self._summary_label = QLabel("No delivery loaded.")
        self._summary_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #888888;")
        action_bar_lay.addWidget(self._summary_label)

        action_bar_lay.addStretch()

        self._btn_view_report = QPushButton("View Report")
        self._btn_view_report.clicked.connect(self._on_view_report)
        self._btn_view_report.setVisible(False)
        self._btn_view_report.setStyleSheet("""
            background-color: rgba(39, 174, 96, 0.1);
            border: 1px solid #27ae60;
            color: #27ae60;
            font-weight: bold;
            padding: 6px 16px;
        """)
        action_bar_lay.addWidget(self._btn_view_report)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._btn_cancel.setVisible(False)
        action_bar_lay.addWidget(self._btn_cancel)

        # Dry Run Toggle (Moved to main window for visibility)
        self._chk_dry_run = QCheckBox("Dry Run")
        self._chk_dry_run.setToolTip("Simulation mode: skips actual file copying.")
        self._chk_dry_run.setChecked(False)
        self._chk_dry_run.stateChanged.connect(self._update_summary)
        action_bar_lay.addWidget(self._chk_dry_run)

        action_bar_lay.addSpacing(10)

        self._btn_ingest = QPushButton("Execute")
        self._btn_ingest.setObjectName("ingestButton")
        self._btn_ingest.setEnabled(False)
        self._btn_ingest.setToolTip("Start ingest execution (Enter)")
        self._btn_ingest.setFixedWidth(200)
        self._btn_ingest.clicked.connect(self._on_ingest)
        action_bar_lay.addWidget(self._btn_ingest)

        root.addWidget(action_bar)

        # Progress bar (hidden by default)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # Log panel (collapsible)
        log_header = QHBoxLayout()
        self._log_toggle = QPushButton("▼ Show Log")
        self._log_toggle.setObjectName("secondaryButton")
        self._log_toggle.setMaximumWidth(100)
        self._log_toggle.clicked.connect(self._toggle_log)
        log_header.addWidget(self._log_toggle)

        log_header.addStretch()

        # Overmind Studios credit
        credit_label = QLabel('<a href="https://www.overmind-studios.de/" style="color: #666666; text-decoration: none;">Made by Overmind Studios</a>')
        credit_label.setStyleSheet("font-size: 10px; font-style: italic;")
        credit_label.setOpenExternalLinks(True)
        credit_label.setCursor(Qt.CursorShape.PointingHandCursor)
        log_header.addWidget(credit_label)

        log_header.addSpacing(12)

        self._btn_clear_log = QPushButton("Clear Log")
        self._btn_clear_log.setObjectName("secondaryButton")
        self._btn_clear_log.setMaximumWidth(80)
        self._btn_clear_log.clicked.connect(lambda: self._log_edit.clear())
        self._btn_clear_log.setVisible(False)
        log_header.addWidget(self._btn_clear_log)

        root.addLayout(log_header)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumHeight(160)
        self._log_edit.setVisible(False)
        self._log_edit.setStyleSheet("QTextEdit { font-family: 'Consolas', monospace; font-size: 11px; }")
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
                status_item = self._table.cellWidget(row, 8)  # Status column (was 7)
                if status_item and hasattr(status_item, "toolTip"):
                    status = status_item.toolTip().lower()
                    if self._current_filter_status not in status:
                        show = False

            # Type filter
            if show:
                # Check if it's a sequence or movie
                plan = self._get_plan_from_row(row)
                if plan:
                    is_sequence = plan.match.clip.is_sequence
                    if is_sequence and not self._chk_sequences.isChecked():
                        show = False
                    elif not is_sequence and not self._chk_movies.isChecked():
                        show = False

                        # Search filter

                        if show and self._search_edit.text():

                            search = self._search_edit.text().lower()

                            shot_item = self._table.item(row, 3)  # Shot column (swapped)

                            seq_item = self._table.item(row, 4)   # Seq column

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
            # Block signals while clearing to prevent triggering overrides
            self._override_shot.blockSignals(True)
            self._override_seq.blockSignals(True)
            
            self._detail_widget.clear()
            self._override_shot.clear()
            self._override_shot.setEnabled(False)
            self._override_seq.clear()
            self._override_seq.setEnabled(False)
            
            self._override_shot.blockSignals(False)
            self._override_seq.blockSignals(False)
            
            self._selected_plan = None
            return

        # Get plan from the first selected row item data (anchored)
        row = self._table.currentRow()
        plan = self._get_plan_from_row(row)
        if not plan:
            return

        self._selected_plan = plan

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
            res_val = f"{plan.media_info.width}x{plan.media_info.height}"

            if self._engine._project_width > 0 and (
                plan.media_info.width != self._engine._project_width
                or plan.media_info.height != self._engine._project_height
            ):
                res_val = f"<b style='color:#f44747'>{res_val} (Project: {self._engine._project_width}x{self._engine._project_height})</b>"

            details.append(f"<b>Resolution:</b> {res_val}")

        if plan.media_info.fps:
            fps_val = f"{plan.media_info.fps:.3f}"

            if (
                self._engine._project_fps > 0
                and abs(plan.media_info.fps - self._engine._project_fps) > 0.001
            ):
                fps_val = f"<b style='color:#f44747'>{fps_val} (Project: {self._engine._project_fps:.3f})</b>"

            details.append(f"<b>FPS:</b> {fps_val}")

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
                f"<br><b style='color:#888; font-size:11px; text-transform: uppercase;'>Destination Path:</b><br>"
                f"<div style='background:#1a1a1a; padding:8px; border-radius:4px; margin-top:4px;'>"
                f"<code style='color:#00bff3; font-size:11px; word-wrap:break-word;'>{plan.target_publish_dir}</code>"
                f"</div>"
            )

        self._detail_widget.setHtml("<br>".join(details))

        # --- Update Overrides (SIGNAL PROTECTED) ---
        # Block signals so that setting text from data doesn't trigger a "change" back to data
        self._override_shot.blockSignals(True)
        self._override_seq.blockSignals(True)

        self._override_shot.setEnabled(True)
        self._override_shot.setText(plan.shot_id or "")

        self._override_seq.setEnabled(True)
        self._override_seq.setText(plan.sequence_id or "")
        
        self._override_shot.blockSignals(False)
        self._override_seq.blockSignals(False)

    def _on_override_changed(self, text: str) -> None:
        """Apply shot ID override to selected plan"""
        if self._selected_plan:
            # Update the data model immediately
            plan = self._selected_plan
            plan.shot_id = text
            
            # Debounce the expensive resolution/update cycle
            self._resolve_timer.start()

    def _on_override_seq_changed(self, text: str) -> None:
        """Apply sequence ID override to selected plan"""
        if self._selected_plan:
            plan = self._selected_plan
            plan.sequence_id = text

            # Update table
            row = self._table.currentRow()
            item = self._table.item(row, 4)  # Seq column
            if item:
                blocked = self._table.blockSignals(True)
                item.setText(text or "—")
                self._table.blockSignals(blocked)
            self._update_summary()

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle inline edits in table"""
        if item.column() == 3:  # Shot column (was 2)
            row = item.row()
            plan = self._get_plan_from_row(row)
            if plan:
                plan.shot_id = item.text()

                # Re-resolve paths to update versioning
                self._resolve_all_paths()

                # Update Version column (index 2)
                ver_item = self._table.item(row, 2)
                if ver_item:
                    blocked = self._table.blockSignals(True)
                    ver_item.setText(f"v{plan.version:03d}")
                    self._table.blockSignals(blocked)

                self._update_summary()

    def _on_remove_selected(self) -> None:
        """Remove selected clips from table"""
        selected_rows = sorted(
            set(item.row() for item in self._table.selectedItems()), reverse=True
        )
        for row in selected_rows:
            plan = self._get_plan_from_row(row)
            if plan and plan in self._plans:
                self._plans.remove(plan)
            self._table.removeRow(row)

        # Re-resolve and re-populate to clear any collisions that might have been resolved
        self._resolve_all_paths()
        self._populate_table()
        self._update_summary()
        self._update_filter_counts()

    def _show_advanced_options(self) -> None:
        """Show advanced options dialog"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Advanced Options")
        dialog.resize(400, 300)
        dialog.setStyleSheet(STYLESHEET)

        lay = QVBoxLayout(dialog)

        # Ingest Options Group
        ingest_options_group = QGroupBox("Ingest Processing Options")
        ingest_options_lay = QVBoxLayout(ingest_options_group)
        
        # Thumbnails
        chk_thumb = QCheckBox("Generate thumbnails")
        chk_thumb.setChecked(self._chk_thumb.isChecked())
        ingest_options_lay.addWidget(chk_thumb)

        # Proxies
        chk_proxy = QCheckBox("Generate video proxies")
        chk_proxy.setChecked(self._chk_proxy.isChecked())
        ingest_options_lay.addWidget(chk_proxy)

        # Status update
        chk_status = QCheckBox("Set step status to OK on success")
        chk_status.setChecked(self._chk_status.isChecked())
        ingest_options_lay.addWidget(chk_status)

        # Fast Verify
        chk_fast = QCheckBox("Fast Verify (MD5 first/mid/last only)")
        chk_fast.setToolTip(
            "Speeds up ingest by only verifying 3 frames per sequence instead of all."
        )
        chk_fast.setChecked(self._chk_fast_verify.isChecked())
        ingest_options_lay.addWidget(chk_fast)
        
        lay.addWidget(ingest_options_group)
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

        lay.addSpacing(10)

        # Daemon Settings
        from ramses.ram_settings import RamSettings
        ram_settings = RamSettings.instance()

        daemon_group = QGroupBox("Daemon Connection")
        daemon_lay = QVBoxLayout(daemon_group)

        daemon_lay.addWidget(QLabel("Daemon Port:"))
        port_edit = QLineEdit(str(ram_settings.ramsesClientPort))
        port_edit.setPlaceholderText("18185 (default)")
        daemon_lay.addWidget(port_edit)

        daemon_lay.addWidget(QLabel("Daemon Address:"))
        address_edit = QLineEdit("localhost")
        address_edit.setPlaceholderText("localhost (default)")
        address_edit.setEnabled(False)  # Usually always localhost
        daemon_lay.addWidget(address_edit)

        daemon_lay.addWidget(QLabel("Ramses Client Path (optional):"))
        path_edit = QLineEdit(ram_settings.ramsesClientPath)
        path_edit.setPlaceholderText("Path to Ramses Client executable...")
        daemon_lay.addWidget(path_edit)

        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(lambda: self._browse_ramses_path(path_edit))
        daemon_lay.addWidget(btn_browse)

        lay.addWidget(daemon_group)

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
                ocio_in,
                rule_combo,
                port_edit,
                path_edit,
                dialog,
            )
        )
        btn_row.addWidget(btn_apply)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        dialog.exec()

    def _browse_ramses_path(self, path_edit: QLineEdit) -> None:
        """Browse for Ramses Client executable"""
        from PySide6.QtWidgets import QFileDialog
        import sys

        # Determine file filter based on platform
        if sys.platform == "win32":
            file_filter = "Executable (*.exe)"
        elif sys.platform == "darwin":
            file_filter = "Application (*.app)"
        else:
            file_filter = "All Files (*)"

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Ramses Client Executable",
            "",
            file_filter
        )

        if path:
            path_edit.setText(path)

    def _apply_options(
        self,
        chk_thumb,
        chk_proxy,
        chk_status,
        chk_fast,
        ocio_in,
        rule_combo,
        port_edit,
        path_edit,
        dialog,
    ):
        """Apply options from dialog"""
        self._chk_thumb.setChecked(chk_thumb.isChecked())
        self._chk_proxy.setChecked(chk_proxy.isChecked())
        self._chk_status.setChecked(chk_status.isChecked())
        self._chk_fast_verify.setChecked(chk_fast.isChecked())
        self._ocio_in.setCurrentText(ocio_in.currentText())
        self._rule_combo.setCurrentIndex(rule_combo.currentIndex())

        # Apply daemon settings
        from ramses.ram_settings import RamSettings
        ram_settings = RamSettings.instance()

        try:
            new_port = int(port_edit.text())
            if new_port != ram_settings.ramsesClientPort:
                ram_settings.ramsesClientPort = new_port
                ram_settings.save()
                self._log(f"Daemon port updated to {new_port}")
        except ValueError:
            self._log("Invalid port number - using default 18185")

        new_path = path_edit.text().strip()
        if new_path != ram_settings.ramsesClientPath:
            ram_settings.ramsesClientPath = new_path
            ram_settings.save()
            if new_path:
                self._log(f"Ramses client path updated to {new_path}")

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
        """Populate or update the table with current plans."""
        # CRITICAL: Disable sorting while we modify items to prevent row-jumping
        self._table.setSortingEnabled(False)
        
        # Block signals to prevent triggering itemSelectionChanged or itemChanged
        self._table.blockSignals(True)
        self._override_shot.blockSignals(True)
        self._override_seq.blockSignals(True)

        current_row_count = self._table.rowCount()
        target_row_count = len(self._plans)

        if current_row_count != target_row_count:
            self._table.setRowCount(target_row_count)

        # Clear selection only if we performed a structural change (add/remove)
        # to avoid losing selection during simple updates (e.g. checkbox toggle)
        if current_row_count != target_row_count:
            self._selected_plan = None
            self._override_shot.clear()
            self._override_seq.clear()
            self._override_shot.setEnabled(False)
            self._override_seq.setEnabled(False)

        for idx, plan in enumerate(self._plans):
            clip = plan.match.clip

            # --- Column 0: Checkbox ---
            chk_widget = self._table.cellWidget(idx, 0)
            if not chk_widget:
                # Create new
                chk = QCheckBox()
                chk.stateChanged.connect(self._on_checkbox_changed)
                chk_widget = QWidget()
                chk_widget.setStyleSheet("background: transparent;")
                chk_lay = QHBoxLayout(chk_widget)
                chk_lay.addWidget(chk)
                chk_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                chk_lay.setContentsMargins(0, 0, 0, 0)
                chk_lay.setSpacing(0)
                self._table.setCellWidget(idx, 0, chk_widget)
            else:
                # Update existing
                chk = chk_widget.findChild(QCheckBox)
            
            if chk:
                chk.blockSignals(True)
                chk.setChecked(plan.enabled)
                chk.blockSignals(False)

            # --- Column 1: Filename ---
            filename = f"{clip.base_name}.{clip.extension}"
            if clip.is_sequence:
                filename = f"{clip.base_name}.####.{clip.extension}"
            
            file_item = self._table.item(idx, 1)
            if not file_item:
                file_item = QTableWidgetItem()
                file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 1, file_item)
            
            if file_item.text() != filename:
                file_item.setText(filename)
            
            # Update data/color
            file_item.setData(Qt.ItemDataRole.UserRole, plan)
            if "COLLISION" in (plan.error or ""):
                file_item.setBackground(QColor(180, 50, 50, 150))
                file_item.setToolTip(plan.error)
            else:
                file_item.setBackground(QColor(0, 0, 0, 0)) # Clear background
                file_item.setToolTip(filename)

            # --- Column 2: Version ---
            ver_text = f"v{plan.version:03d}"
            ver_item = self._table.item(idx, 2)
            if not ver_item:
                ver_item = QTableWidgetItem()
                ver_item.setFlags(ver_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                ver_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(idx, 2, ver_item)
            
            if ver_item.text() != ver_text:
                ver_item.setText(ver_text)

            if plan.match.version and plan.match.version != plan.version:
                ver_item.setBackground(QColor(120, 100, 0, 100))
                ver_item.setToolTip(f"Mismatch: v{plan.match.version:03d} -> v{plan.version:03d}")
            else:
                ver_item.setBackground(QColor(0, 0, 0, 0))
                ver_item.setToolTip("")

            # --- Column 3: Shot ---
            shot_text = plan.shot_id or ""
            shot_item = self._table.item(idx, 3)
            if not shot_item:
                shot_item = QTableWidgetItem()
                self._table.setItem(idx, 3, shot_item)
            
            if shot_item.text() != shot_text:
                shot_item.setText(shot_text)
            
            if not plan.shot_id:
                shot_item.setForeground(QColor("#f44747"))
            else:
                shot_item.setForeground(QColor("#e0e0e0")) # Default text color

            # --- Column 4: Sequence ---
            seq_text = plan.sequence_id or "—"
            seq_item = self._table.item(idx, 4)
            if not seq_item:
                seq_item = QTableWidgetItem()
                seq_item.setFlags(seq_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 4, seq_item)
            
            if seq_item.text() != seq_text:
                seq_item.setText(seq_text)

            # --- Column 5: Frames ---
            if clip.is_sequence:
                fc = clip.frame_count
            else:
                fc = plan.media_info.frame_count if plan.media_info.frame_count > 0 else 1
            
            frames_text = str(fc)
            frames_item = self._table.item(idx, 5)
            if not frames_item:
                frames_item = QTableWidgetItem()
                frames_item.setFlags(frames_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 5, frames_item)

            if frames_item.text() != frames_text:
                frames_item.setText(frames_text)

            if clip.missing_frames:
                frames_item.setBackground(QColor(150, 50, 0, 150))
                frames_item.setToolTip(f"Gaps detected: {len(clip.missing_frames)} frames")
            else:
                frames_item.setBackground(QColor(0, 0, 0, 0))
                frames_item.setToolTip("")

            # --- Column 6: Resolution ---
            res_text = "—"
            is_res_mismatch = False
            if plan.media_info.width and plan.media_info.height:
                res_text = f"{plan.media_info.width}x{plan.media_info.height}"
                if self._engine._project_width > 0 and (
                    plan.media_info.width != self._engine._project_width
                    or plan.media_info.height != self._engine._project_height
                ):
                    is_res_mismatch = True

            res_item = self._table.item(idx, 6)
            if not res_item:
                res_item = QTableWidgetItem()
                res_item.setFlags(res_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 6, res_item)

            if res_item.text() != res_text:
                res_item.setText(res_text)

            if is_res_mismatch:
                res_item.setBackground(QColor(120, 100, 0, 100))
                res_item.setToolTip(f"Mismatch: Project is {self._engine._project_width}x{self._engine._project_height}")
            else:
                res_item.setBackground(QColor(0, 0, 0, 0))
                res_item.setToolTip("")

            # --- Column 7: FPS ---
            fps_text = f"{plan.media_info.fps:.3f}" if plan.media_info.fps > 0 else "—"
            is_fps_mismatch = False
            if self._engine._project_fps > 0 and plan.media_info.fps > 0:
                if abs(plan.media_info.fps - self._engine._project_fps) > 0.001:
                    is_fps_mismatch = True

            fps_item = self._table.item(idx, 7)
            if not fps_item:
                fps_item = QTableWidgetItem()
                fps_item.setFlags(fps_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 7, fps_item)
            
            if fps_item.text() != fps_text:
                fps_item.setText(fps_text)

            if is_fps_mismatch:
                fps_item.setBackground(QColor(120, 100, 0, 100))
                fps_item.setToolTip(f"Mismatch: Project is {self._engine._project_fps:.3f}")
            else:
                fps_item.setBackground(QColor(0, 0, 0, 0))
                fps_item.setToolTip("")

            # --- Column 8: Status ---
            status = "pending"
            status_msg = ""

            if plan.match.clip.missing_frames:
                status = "warning"
                status_msg = f"GAPS: {len(plan.match.clip.missing_frames)} missing frames"
            elif is_res_mismatch or is_fps_mismatch:
                status = "warning"
                status_msg = "Technical mismatch (Res/FPS)"
            elif plan.can_execute and not plan.error:
                status = "ready"
            elif plan.error:
                if "warning" in plan.error.lower():
                    status = "warning"
                else:
                    status = "error"
                    status_msg = plan.error
            elif plan.is_duplicate:
                status = "duplicate"

            # Always replace status widget as it's cheap and stateful logic is complex to update
            status_indicator = StatusIndicator(status)
            if status_msg:
                status_indicator.setToolTip(status_msg)

            status_container = QWidget()
            status_container.setStyleSheet("background: transparent;")
            status_layout = QHBoxLayout(status_container)
            status_layout.addWidget(status_indicator)
            status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setSpacing(0)

            self._table.setCellWidget(idx, 8, status_container)

        self._table.blockSignals(False)
        self._override_shot.blockSignals(False)
        self._override_seq.blockSignals(False)
        self._table.setSortingEnabled(True)

        self._update_filter_counts()
        self._update_summary()

    def _on_checkbox_changed(self, state: int) -> None:
        """Handle checkbox state changes"""
        # Find which row changed
        sender = self.sender()
        for row in range(self._table.rowCount()):
            chk_widget = self._table.cellWidget(row, 0)
            if chk_widget and chk_widget.findChild(QCheckBox) == sender:
                plan = self._get_plan_from_row(row)
                if plan:
                    plan.enabled = state == Qt.CheckState.Checked.value
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
                plan = self._get_plan_from_row(row)
                if plan:
                    plan.shot_id = shot_id
                    item = self._table.item(row, 3) # Shot column (was 2)
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
                plan = self._get_plan_from_row(row)
                if plan:
                    plan.sequence_id = seq_id
                    item = self._table.item(row, 4)  # Seq column (remains 4)
                    if item:
                        item.setText(seq_id or "—")

            self._update_summary()

    def _on_context_skip(self) -> None:
        """Skip selected clips (uncheck them)"""
        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        for row in selected_rows:
            plan = self._get_plan_from_row(row)
            if plan:
                plan.enabled = False
                chk_widget = self._table.cellWidget(row, 0)
                if chk_widget:
                    chk = chk_widget.findChild(QCheckBox)
                    if chk:
                        chk.setChecked(False)

        self._update_summary()

    # -- Helpers -------------------------------------------------------------

    def _log(self, msg: str) -> None:
        """Add syntax highlighting for log messages and append to log edit."""
        msg_upper = msg.upper()
        
        # 1. Error Check (Highest Priority)
        # We check errors first because a message like "Complete: 1 failed" 
        # should be red, even though it contains "Complete".
        if any(k in msg_upper for k in ["ERROR", "FAILED", "CRITICAL", "FAIL", "✖", ": FAILED"]):
            colored_msg = f'<span style="color: #f44747; font-weight: bold;">{msg}</span>'
            
        # 2. Success Check
        elif any(k in msg_upper for k in [
            "SUCCEEDED", "COMPLETE", "SUCCESS", "DONE", "✓", ": OK", 
            "MAPPED", "READY:", "MATCHED"
        ]):
            colored_msg = f'<span style="color: #27ae60;">{msg}</span>'
            
        # 3. Warning Check
        elif "WARNING" in msg_upper or "WARN" in msg_upper:
            colored_msg = f'<span style="color: #f39c12;">{msg}</span>'
            
        # 4. Default / Info
        else:
            colored_msg = msg

        self._log_edit.append(colored_msg)
        sb = self._log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _get_plan_from_row(self, row: int) -> IngestPlan | None:
        """Fetch the anchored IngestPlan object from a specific table row."""
        if row < 0 or row >= self._table.rowCount():
            return None
        # Filename column (index 1) has the anchored data
        item = self._table.item(row, 1)
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _resolve_all_paths(self) -> None:
        """Update target paths and version numbers for all plans."""
        if not self._plans:
            return

        from ramses_ingest.publisher import (
            resolve_paths,
            resolve_paths_from_daemon,
            check_for_path_collisions,
        )

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
        """Start background connection attempt."""
        if self._connection_worker and self._connection_worker.isRunning():
            return

        # UI Feedback: Connecting state
        self._status_label.setText("CONNECTING...")
        self._status_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        self._btn_reconnect.setVisible(False)
        self._btn_refresh.setEnabled(False)  # Disable while connecting

        # Start worker
        self._connection_worker = ConnectionWorker(self._engine, parent=self)
        self._connection_worker.finished.connect(self._on_connection_finished)
        self._connection_worker.start()

    def _on_connection_finished(self, ok: bool) -> None:
        """Handle connection result from worker."""
        # Re-enable refresh button regardless of outcome
        self._btn_refresh.setEnabled(True)

        if ok:
            self._reconnect_timer.stop()
            self._btn_reconnect.setVisible(False)
            self._btn_refresh.setVisible(True)

            self._status_label.setText("DAEMON ONLINE")
            self._status_label.setObjectName("statusConnected")
            pid = self._engine.project_id
            pname = self._engine.project_name
            self._project_label_display.setText(f"{pid} - {pname}")

            # Update Standards display
            fps = self._engine._project_fps
            w = self._engine._project_width
            h = self._engine._project_height
            self._standards_label.setText(f"STANDARD: {w}x{h} @ {fps:.3f} FPS")

            # Populate steps
            self._step_combo.blockSignals(True)
            self._step_combo.clear()
            for s in self._engine.steps:
                self._step_combo.addItem(s)
            
            # Select "PLATE" if it exists, otherwise select the current engine step
            if "PLATE" in self._engine.steps:
                self._step_combo.setCurrentText("PLATE")
            else:
                self._step_combo.setCurrentText(self._engine.step_id)
            
            # CRITICAL: Re-sync engine state with whatever was actually selected
            self._engine.step_id = self._step_combo.currentText()
            self._step_combo.blockSignals(False)
            
            # If we were already working, refresh paths now that we're connected
            if self._plans:
                self._resolve_all_paths()
                self._populate_table()
                
        else:
            self._status_label.setText("OFFLINE")
            self._status_label.setObjectName("statusDisconnected")
            self._project_label_display.setText("— (Connection Required)")
            self._btn_ingest.setToolTip("Ramses connection required to ingest.")
            
            self._btn_reconnect.setVisible(True)
            self._btn_refresh.setVisible(False) # Only show Refresh when connected (manual reload)
            
            if not self._reconnect_timer.isActive():
                self._reconnect_timer.start()

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
        new_shots = sum(1 for p in self._plans if p.is_new_shot and p.match.matched)

        enabled = self._get_enabled_plans()
        n_enabled = len(enabled)

        # Count status types
        ready_count = sum(1 for p in self._plans if p.can_execute and not p.error)
        warning_count = sum(1 for p in self._plans if p.can_execute and p.error and "warning" in p.error.lower())
        error_count = sum(1 for p in self._plans if not p.can_execute or (p.error and "error" in p.error.lower()))

        # Build summary with color coding
        summary_parts = [f"<b>{total} clips</b>"]

        if ready_count > 0:
            summary_parts.append(f"<span style='color: #27ae60;'>{ready_count} ready</span>")
        if warning_count > 0:
            summary_parts.append(f"<span style='color: #f39c12;'>{warning_count} warnings</span>")
        if error_count > 0:
            summary_parts.append(f"<span style='color: #f44747;'>{error_count} errors</span>")

        if new_shots > 0:
            summary_parts.append(f"{new_shots} new shots")

        self._summary_label.setText(" • ".join(summary_parts))

        # Set overall label color based on status
        if error_count > 0:
            label_color = "#f44747"
        elif warning_count > 0:
            label_color = "#f39c12"
        elif ready_count > 0:
            label_color = "#27ae60"
        else:
            label_color = "#888888"

        self._summary_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {label_color};")

        is_dry = self._chk_dry_run.isChecked()
        btn_text = "Simulate" if is_dry else "Ingest"
        self._btn_ingest.setText(f"{btn_text} {n_enabled}/{total}")

        # UI Polish: Apply specific colors for different states
        if is_dry:
            # Orange for Simulation
            self._btn_ingest.setStyleSheet(
                "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f39c12, stop:1 #d35400); color: white; border: none; font-weight: bold;"
            )
        else:
            # Standard Blue for Ingest (matching Ramses-Fusion accent)
            # We apply this specifically when enabled so it doesn't override the disabled look
            if (
                n_enabled > 0
                and self._engine.connected
                and bool(self._step_combo.currentText())
            ):
                self._btn_ingest.setStyleSheet(
                    "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #094771, stop:1 #06314d); color: white; border: none; font-weight: bold;"
                )
            else:
                self._btn_ingest.setStyleSheet("")  # Revert to stylesheet default (muted)

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

        try:
            mapper = EDLMapper(path)
        except Exception as exc:
            QMessageBox.critical(self, "EDL Error", f"Failed to parse EDL file:\n{exc}")
            self._log(f"  ERROR: Failed to parse EDL: {exc}")
            return

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
        self._btn_clear_log.setVisible(visible)
        self._log_toggle.setText("▲ Hide Log" if visible else "▼ Show Log")


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
