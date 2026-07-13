# -*- coding: utf-8 -*-
"""PySide6 GUI for Ramses Ingest — dark professional theme matching Ramses-Fusion."""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QUrl, QTimer, QSize
from PySide6.QtGui import (
    QFont,
    QDragEnterEvent,
    QDropEvent,
    QColor,
    QPalette,
    QAction,
    QShortcut,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
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
from ramses_ingest.config import load_rules, save_rules, DEFAULT_RULES_PATH, USER_RULES_PATH
from ramses_ingest.prober import check_ffprobe, has_av

# Import reusable components
from ramses_ingest.gui_widgets import (
    GuiLogHandler,
    DropZone,
    EditableDelegate,
    RulesEditorDialog,
)

# Status column rendering: colored dot per status type. Plain table items are
# used (not cell widgets) so the dots travel with their rows when the user
# sorts the table — QTableWidget sorting moves items but NOT cell widgets.
STATUS_DOT_COLORS = {
    "ready": "#27ae60",
    "warning": "#f39c12",
    "error": "#f44747",
    "pending": "#666666",
    "duplicate": "#999999",
    "skipped": "#444444",
}


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

QLabel#statusConnecting {
    color: #f39c12;
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

logger = logging.getLogger("ramses_ingest")


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------


# Production colorspaces offered in the OCIO dropdown and the per-clip
# override. The chosen value is passed verbatim as the ffmpeg `ocio` filter's
# in_label, so every entry must be resolvable by the loaded OCIO config
# (recent ACES configs alias all of these). The override dialog is editable,
# so names from custom configs can be typed as well.
STANDARD_COLORSPACES = [
    "sRGB",
    "Linear",
    "Rec.709",
    "Rec.2020",
    "ACEScg",
    "ACES - ACEScct",
    "ACES - ACEScc",
    "ARRI LogC4",
    "ARRI LogC3 (EI800)",
    "LogC",
    "S-Log3",
    "V-Log",
    "Cineon",
    "Gamma 2.2",
    "Gamma 2.4",
]


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
        try:
            ok = self._engine.connect_ramses()
            self.finished.emit(ok)
        except Exception:
            self.finished.emit(False)


class ProjectReportWorker(QThread):
    """Builds the whole-project ingest report in a background thread.

    Walks every published version on disk and probes first frames, so it
    must not run on the UI thread."""

    progress = Signal(str)
    finished_report = Signal(str)  # HTML path, or "" when nothing was found

    def __init__(self, engine: IngestEngine, since: float | None = None, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._since = since

    def run(self) -> None:
        try:
            path = self._engine.generate_project_report(
                progress_callback=self.progress.emit, since=self._since
            )
            self.finished_report.emit(path or "")
        except Exception as exc:
            self.progress.emit(f"Project report failed: {exc}")
            self.finished_report.emit("")


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
        self._cancel_requested = False

    def cancel(self) -> None:
        """Request cooperative cancellation. Current items finish atomically."""
        self._cancel_requested = True

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
                cancel_check=lambda: self._cancel_requested,
            )
            self.finished_results.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------


class IngestWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ramses Ingest")
        self.resize(1400, 800)  # Increased from 1200x700

        # Check for ffprobe availability on startup
        if not check_ffprobe():
            QTimer.singleShot(500, self._show_ffprobe_warning)

        # Warm the upstream Ramses singletons on the main thread before any
        # QThread (ConnectionWorker) touches them: the library uses an
        # unsynchronised double-check-lock singleton pattern, so construction
        # must complete before concurrent access (same hardening as Hub/Out).
        try:
            from ramses import Ramses
            from ramses.ram_settings import RamSettings
            from ramses.daemon_interface import RamDaemonInterface
            RamSettings.instance()
            RamDaemonInterface.instance()
            Ramses.instance()
        except Exception as e:
            logger.warning("Could not warm Ramses singletons: %s", e)

        self._engine = IngestEngine()
        self._plans: list[IngestPlan] = []
        self._scan_worker: ScanWorker | None = None
        self._ingest_worker: IngestWorker | None = None
        self._connection_worker: ConnectionWorker | None = None
        self._report_worker: ProjectReportWorker | None = None
        self._current_filter_status = "all"  # For filter sidebar
        self._selected_plan: IngestPlan | None = None  # For detail panel
        self._last_dest_dirs: list[str] = []  # Publish dirs of the last ingest

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(5000)  # Check every 5 seconds
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

        # Maximize on startup
        self.showMaximized()

    def _show_ffprobe_warning(self) -> None:
        QMessageBox.warning(
            self,
            "FFmpeg Missing",
            "ffprobe could not be found in your system PATH.\n\n"
            "Metadata extraction (resolution, frame count) will be unavailable, "
            "and ingest may fail or produce incomplete data.\n\n"
            "Please install FFmpeg and restart the application.",
        )

    def _setup_logging(self) -> None:
        """Redirect ramses_ingest package logs to the GUI log panel."""
        handler = GuiLogHandler(self._log)
        # We use the global logger defined at module level (or from ramses_ingest)
        logging.getLogger("ramses_ingest").addHandler(handler)
        # Ensure we capture at least INFO level
        if logging.getLogger("ramses_ingest").level == logging.NOTSET:
            logging.getLogger("ramses_ingest").setLevel(logging.INFO)

    def _on_resolve_timeout(self) -> None:
        """Called after debounce period to resolve paths and update UI."""
        # Never mutate plans while worker threads are copying into their
        # target directories — a pending debounce from just before Execute
        # would otherwise clear/re-resolve paths mid-transfer.
        if self._ingest_worker and self._ingest_worker.isRunning():
            return
        self._resolve_all_paths()
        self._populate_table()

    def _set_ui_locked(self, locked: bool) -> None:
        """Locks every control that can mutate plans while an ingest runs.

        Worker threads read plan target paths during the transfer; edits from
        the main thread (checkboxes, shot overrides, step changes, removals)
        would re-resolve those paths mid-copy.
        """
        enabled = not locked
        self._table.setEnabled(enabled)
        self._drop_zone.setEnabled(enabled)
        self._drop_zone.setAcceptDrops(enabled)
        self._search_edit.setEnabled(enabled)
        self._step_combo.setEnabled(enabled)
        self._btn_clear.setEnabled(enabled)
        self._btn_options.setEnabled(enabled)
        self._chk_dry_run.setEnabled(enabled)
        # The project report walks the same _published folders the transfer
        # writes into — don't build one while an ingest is running.
        self._btn_project_report.setEnabled(enabled and self._engine.connected)
        for btn in (
            self._filter_all,
            self._filter_ready,
            self._filter_warning,
            self._filter_error,
        ):
            btn.setEnabled(enabled)
        for chk in (self._chk_sequences, self._chk_movies):
            chk.setEnabled(enabled)

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
        self._project_label_display.setStyleSheet(
            "color: #ffffff; font-weight: 800; font-size: 13px;"
        )
        header_lay.addWidget(self._project_label_display)

        # Step
        header_lay.addWidget(QLabel("Step:"))
        self._step_combo = QComboBox()
        self._step_combo.setMinimumWidth(100)
        self._step_combo.addItem("PLATE")
        self._step_combo.setToolTip(
            "Pipeline step the footage is ingested into.\n"
            "Steps come from the Ramses project (Shot Production type) —\n"
            "create them in the Ramses Client; Ingest never creates steps."
        )
        self._step_combo.currentTextChanged.connect(self._on_step_changed)
        header_lay.addWidget(self._step_combo)

        header_lay.addSpacing(10)

        # Standards
        self._standards_label = QLabel("—")
        self._standards_label.setStyleSheet(
            "color: #888; font-family: 'Consolas', monospace; font-size: 10px;"
        )
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
        self._search_edit.setClearButtonEnabled(True)
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
        self._chk_sequences.setToolTip("Show image sequences (EXR, DPX, ...)")
        self._chk_sequences.stateChanged.connect(self._on_type_filter_changed)
        left_lay.addWidget(self._chk_sequences)

        self._chk_movies = QCheckBox("Movies")
        self._chk_movies.setChecked(True)
        self._chk_movies.setToolTip("Show movie files (MOV, MP4, MXF, ...)")
        self._chk_movies.stateChanged.connect(self._on_type_filter_changed)
        left_lay.addWidget(self._chk_movies)

        left_lay.addStretch()

        # Advanced options button (moved here)
        self._btn_options = QPushButton("⚙ Options...")
        self._btn_options.clicked.connect(self._show_advanced_options)
        left_lay.addWidget(self._btn_options)

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
        self._table.setColumnCount(12)
        self._table.setHorizontalHeaderLabels(
            [
                "",
                "Filename",
                "Ver",
                "Shot",
                "Seq",
                "Resource",
                "Frames",
                "Res",
                "FPS",
                "PAR",
                "Colorspace",
                "Status",
            ]
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

        # Set column widths (balanced to use full width)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 34)  # Checkbox
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )  # Filename stretches
        for col in [2, 3, 4, 5, 6, 7, 8, 9, 10]:  # Ver, Shot, Seq, Resource, Frames, Res, FPS, PAR, Colorspace
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(
                col, 65 if col in [2, 8, 9] else (90 if col == 10 else 88)
            )  # 65px for Ver/FPS/PAR, 90px for Colorspace, 88px for others
        header.setSectionResizeMode(11, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(11, 70)  # Status - wider to prevent header cut-off

        # Set delegate for inline editing
        delegate = EditableDelegate(self._table)
        self._table.setItemDelegateForColumn(3, delegate)  # Shot column
        self._table.setItemDelegateForColumn(5, delegate)  # Resource column

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
        self._detail_widget.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        right_lay.addWidget(self._detail_widget)

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
        self._summary_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #888888;"
        )
        action_bar_lay.addWidget(self._summary_label)

        action_bar_lay.addStretch()

        self._btn_project_report = QPushButton("Project Report")
        self._btn_project_report.setToolTip(
            "Build one client-ready report of ALL footage currently ingested\n"
            "in this project — across every ingest session. Reflects the\n"
            "current on-disk state (reverted versions don't appear)."
        )
        self._btn_project_report.setEnabled(False)
        self._btn_project_report.clicked.connect(self._on_project_report)
        action_bar_lay.addWidget(self._btn_project_report)

        self._btn_open_dest = QPushButton("Open Destination")
        self._btn_open_dest.setToolTip(
            "Open the ingested files in the file manager\n"
            "(the common parent folder when several shots were ingested)"
        )
        self._btn_open_dest.clicked.connect(self._on_open_destination)
        self._btn_open_dest.setVisible(False)
        action_bar_lay.addWidget(self._btn_open_dest)

        self._btn_view_report = QPushButton("View Report")
        self._btn_view_report.setToolTip(
            "Open the HTML ingest manifest: per-clip results, warnings,\n"
            "thumbnails and checksum verification details"
        )
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
        credit_label = QLabel(
            '<a href="https://www.overmind-studios.de/" style="color: #666666; text-decoration: none;">Made by Overmind Studios</a>'
        )
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
        self._log_edit.setStyleSheet(
            "QTextEdit { font-family: 'Consolas', monospace; font-size: 11px; }"
        )
        root.addWidget(self._log_edit)

        # Keyboard shortcuts
        self._setup_shortcuts()

        # Initialize naming rule combo
        self._rule_combo = QComboBox()
        self._rule_combo.addItem("Auto-detect")
        self._populate_rule_combo()
        self._rule_combo.currentIndexChanged.connect(
            lambda _: self._rematch_all_clips()
        )

        # Initialize options checkboxes
        self._chk_thumb = QCheckBox()
        self._chk_thumb.setChecked(True)
        self._chk_proxy = QCheckBox()
        self._chk_proxy.setChecked(False)
        self._chk_status = QCheckBox()
        self._chk_status.setChecked(True)
        self._chk_fast_verify = QCheckBox()
        self._chk_fast_verify.setChecked(True)
        self._ocio_in = QComboBox()
        # Expanded list of production-standard colorspaces
        self._populate_ocio_dropdown(self._ocio_in)
        self._btn_edl = QPushButton("Load EDL...")

    # -- Professional UI Methods ---------------------------------------------

    def _populate_ocio_dropdown(self, combo: QComboBox, detected_colorspace: str = "") -> None:
        """Populate OCIO dropdown with standard colorspaces plus detected value

        Args:
            combo: The QComboBox to populate
            detected_colorspace: Optional colorspace detected from file metadata
        """
        # Single source of truth shared with the per-clip override dialog
        standard_colorspaces = STANDARD_COLORSPACES

        # Build final list
        items = []

        # If we have a detected colorspace, add it first with indicator
        if detected_colorspace:
            # Normalize the detected colorspace (remove common prefixes/suffixes)
            normalized = detected_colorspace.strip()

            # Check if it's already in our standard list (case-insensitive)
            is_standard = any(cs.lower() == normalized.lower() for cs in standard_colorspaces)

            if is_standard:
                # Use the standard name but mark it as auto-detected
                standard_match = next(cs for cs in standard_colorspaces if cs.lower() == normalized.lower())
                items.append(f"[Auto] {standard_match}")
            else:
                # Custom/unknown colorspace - add it with auto indicator
                items.append(f"[Auto] {normalized}")

            items.append("---")  # Separator

        # Add all standard colorspaces
        items.extend(standard_colorspaces)

        # Update combo box
        current_text = combo.currentText()
        combo.clear()
        combo.addItems(items)

        # Try to restore previous selection if it exists
        if current_text:
            idx = combo.findText(current_text)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif detected_colorspace:
                # Set to auto-detected value
                combo.setCurrentIndex(0)

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
        # Ignore Return while an inline cell editor is open — the user is
        # committing a shot/resource edit, not asking to start the ingest.
        focus = QApplication.focusWidget()
        if focus is not None and focus is not self._table and self._table.isAncestorOf(focus):
            return
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
        search_text = self._search_edit.text().lower()

        for row in range(self._table.rowCount()):
            show = True

            # 1. Status filter
            if self._current_filter_status != "all":
                # Status type is stored on the status item (column 11)
                status_item = self._table.item(row, 11)
                if status_item:
                    status_type = status_item.data(Qt.ItemDataRole.UserRole)
                    if status_type and self._current_filter_status != status_type:
                        show = False

            # 2. Type filter
            if show:
                # Check if it's a sequence or movie
                plan = self._get_plan_from_row(row)
                if plan:
                    is_sequence = plan.match.clip.is_sequence
                    if is_sequence and not self._chk_sequences.isChecked():
                        show = False
                    elif not is_sequence and not self._chk_movies.isChecked():
                        show = False

            # 3. Search filter
            if show and search_text:
                shot_item = self._table.item(row, 3)  # Shot column
                seq_item = self._table.item(row, 4)  # Seq column
                res_item = self._table.item(row, 5)  # Resource column
                file_item = self._table.item(row, 1)  # Filename column

                match = False
                if shot_item and search_text in shot_item.text().lower():
                    match = True
                elif seq_item and search_text in seq_item.text().lower():
                    match = True
                elif res_item and search_text in res_item.text().lower():
                    match = True
                elif file_item and search_text in file_item.text().lower():
                    match = True

                if not match:
                    show = False

            self._table.setRowHidden(row, not show)

    def _on_selection_changed(self) -> None:
        """Update detail panel when selection changes"""
        selected = self._table.selectedItems()
        if not selected:
            self._detail_widget.clear()
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
        details.append(f"<b>Resource:</b> {plan.resource or '—'}")

        # Proper frame count for movies
        fc_raw = (
            plan.match.clip.frame_count
            if plan.match.clip.is_sequence
            else plan.media_info.frame_count
        )
        fc = fc_raw or 0
        if not plan.match.clip.is_sequence and fc <= 0:
            fc = 1  # Fallback

        details.append(f"<b>Frames:</b> {fc}")

        if plan.media_info.width and plan.media_info.height:
            res_val = f"{plan.media_info.width}x{plan.media_info.height}"

            if (self._engine._project_width or 0) > 0 and (
                plan.media_info.width != self._engine._project_width
                or plan.media_info.height != self._engine._project_height
            ):
                res_val = f"<b style='color:#f44747'>{res_val} (Project: {self._engine._project_width}x{self._engine._project_height})</b>"

            details.append(f"<b>Resolution:</b> {res_val}")

        if plan.media_info.fps:
            fps_val = f"{plan.media_info.fps:.3f}"

            if (
                (self._engine._project_fps or 0.0) > 0
                and abs(plan.media_info.fps - (self._engine._project_fps or 0.0)) > 0.001
            ):
                fps_val = f"<b style='color:#f44747'>{fps_val} (Project: {self._engine._project_fps or 0.0:.3f})</b>"

            details.append(f"<b>FPS:</b> {fps_val}")

        par_val = f"{plan.media_info.pixel_aspect_ratio:.3f}"
        if abs(plan.media_info.pixel_aspect_ratio - (self._engine._project_par or 1.0)) > 0.001:
            par_val = f"<b style='color:#f44747'>{par_val} (Project: {self._engine._project_par or 1.0:.3f})</b>"
        details.append(f"<b>Pixel Aspect:</b> {par_val}")

        if plan.media_info.codec:
            details.append(f"<b>Codec:</b> {plan.media_info.codec}")
        if plan.media_info.color_space:
            details.append(f"<b>Colorspace:</b> {plan.media_info.color_space}")

        if plan.error:
            details.append(f"<br><b style='color:#f44747'>Error:</b> {plan.error}")

        for warning in plan.warnings:
            details.append(f"<br><b style='color:#f39c12'>Warning:</b> {warning}")

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

        # Update OCIO dropdown with detected colorspace
        detected_cs = plan.media_info.color_space if plan.media_info else ""
        self._populate_ocio_dropdown(self._ocio_in, detected_cs)

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle inline edits and checkbox toggles in the table"""
        if item.column() == 0:  # Enable/skip checkbox
            plan = self._get_plan_from_row(item.row())
            if plan:
                plan.enabled = item.checkState() == Qt.CheckState.Checked
                # Debounce the expensive re-resolution (collisions, duplicates,
                # version numbers hit the filesystem); the timeout repopulates
                # the table, which also refreshes dimming and status dots.
                self._resolve_timer.start()
            return

        if item.column() == 3:  # Shot column
            row = item.row()
            plan = self._get_plan_from_row(row)
            if plan:
                plan.shot_id = item.text()
                # Debounce the expensive resolution/update cycle
                self._resolve_timer.start()

        elif item.column() == 5:  # Resource column
            row = item.row()
            plan = self._get_plan_from_row(row)
            if plan:
                plan.resource = item.text()
                # Debounce the expensive resolution/update cycle
                self._resolve_timer.start()

    def _on_remove_selected(self, _=None) -> None:
        """Remove selected clips from table"""
        # The Delete key reaches the window even with the table disabled;
        # never remove plans while worker threads are transferring them.
        if self._ingest_worker and self._ingest_worker.isRunning():
            return
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

    def _show_advanced_options(self, _=None) -> None:
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
        # Populate with same colorspaces as main dropdown
        detected_cs = ""
        if self._selected_plan and self._selected_plan.media_info:
            detected_cs = self._selected_plan.media_info.color_space
        self._populate_ocio_dropdown(ocio_in, detected_cs)
        ocio_in.setCurrentText(self._ocio_in.currentText())
        ocio_in.currentTextChanged.connect(self._on_ocio_in_changed)
        ocio_lay.addWidget(ocio_in)

        lay.addWidget(ocio_group)

        lay.addSpacing(10)

        # Naming rules
        rule_group = QGroupBox("Naming Rules")
        rule_lay = QVBoxLayout(rule_group)

        rule_combo = QComboBox()
        self._populate_rule_combo(rule_combo)
        rule_combo.setCurrentIndex(self._rule_combo.currentIndex())
        rule_lay.addWidget(rule_combo)

        rule_btns = QHBoxLayout()
        btn_architect = QPushButton("Architect...")
        btn_architect.setToolTip(
            "Visual rule builder: pick the shot/sequence parts of a sample\n"
            "filename and generate a matching rule automatically"
        )

        def _launch_and_refresh():
            self._on_launch_smart_pattern()
            self._populate_rule_combo(rule_combo)
            rule_combo.setCurrentIndex(self._rule_combo.currentIndex())

        btn_architect.clicked.connect(_launch_and_refresh)
        rule_btns.addWidget(btn_architect)

        btn_edl = QPushButton("Load EDL...")
        btn_edl.setToolTip(
            "Map clip names to shot IDs from a CMX 3600 EDL and validate\n"
            "frame ranges against its comments"
        )
        btn_edl.clicked.connect(self._on_load_edl)
        rule_btns.addWidget(btn_edl)

        btn_edit = QPushButton("Edit Rules...")
        btn_edit.setToolTip("Edit the naming rules (regex) by hand")
        btn_edit.clicked.connect(self._on_edit_rules)
        rule_btns.addWidget(btn_edit)

        btn_reset = QPushButton("Reset to Default")
        btn_reset.clicked.connect(self._on_reset_rules)
        btn_reset.setToolTip("Restore the default built-in naming rules")
        rule_btns.addWidget(btn_reset)

        rule_lay.addLayout(rule_btns)

        lay.addWidget(rule_group)

        lay.addSpacing(10)

        # Studio Branding Group
        studio_group = QGroupBox("Studio Branding")
        studio_lay = QVBoxLayout(studio_group)
        
        studio_lay.addWidget(QLabel("Studio Logo Image:"))
        logo_row = QHBoxLayout()
        logo_path_edit = QLineEdit(self._engine.studio_logo)
        logo_path_edit.setPlaceholderText("Path to logo image (PNG/JPG)...")
        logo_row.addWidget(logo_path_edit)
        
        btn_logo_browse = QPushButton("Browse...")
        btn_logo_browse.clicked.connect(lambda: self._browse_studio_logo(logo_path_edit))
        logo_row.addWidget(btn_logo_browse)
        studio_lay.addLayout(logo_row)
        
        lay.addWidget(studio_group)

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
                logo_path_edit,
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
            self, "Select Ramses Client Executable", "", file_filter
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
        logo_path_edit,
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

        # Apply studio branding
        new_logo = logo_path_edit.text().strip()
        if new_logo != self._engine.studio_logo:
            self._engine.studio_logo = new_logo
            save_rules(
                self._engine.rules,
                studio_name=self._engine.studio_name,
                studio_logo=new_logo,
            )

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

        # Re-match clips with potentially new rules/settings
        self._rematch_all_clips()

        self._update_summary()
        dialog.accept()

    def _rematch_all_clips(self) -> None:
        """Re-run matching on all loaded clips using current engine rules."""
        if not self._plans:
            return

        # Extract clips from current plans (deduplicated by first file)
        clips = []
        seen = set()
        for p in self._plans:
            if p.match.clip.first_file not in seen:
                clips.append(p.match.clip)
                seen.add(p.match.clip.first_file)

        # Re-match
        from ramses_ingest.matcher import match_clips
        from ramses_ingest.publisher import build_plans

        # Determine rules to use based on combo box selection
        # Index 0 is "Auto-detect" (all rules)
        # Index 1 is Rule 1 (self._engine.rules[0])
        selected_idx = self._rule_combo.currentIndex()
        if selected_idx > 0:
            rule_idx = selected_idx - 1
            if 0 <= rule_idx < len(self._engine.rules):
                rules_to_use = [self._engine.rules[rule_idx]]
            else:
                rules_to_use = self._engine.rules
        else:
            rules_to_use = self._engine.rules

        matches = match_clips(clips, rules_to_use)

        # Reuse media info from existing plans
        media_infos = {p.match.clip.first_file: p.media_info for p in self._plans}

        # Re-build plans
        new_plans = build_plans(
            matches,
            media_infos,
            project_id=self._engine.project_id or "PROJ",
            project_name=self._engine.project_name
            or self._engine.project_id
            or "Project",
            step_id=self._engine.step_id,
            existing_sequences=self._engine.existing_sequences,
            existing_shots=self._engine.existing_shots,
        )

        # Re-resolve paths and check for collisions
        self._plans = new_plans
        self._resolve_all_paths()
        self._populate_table()

    def _update_filter_counts(self) -> None:
        """Update the count badges on filter buttons"""
        if not hasattr(self, "_plans"):
            return

        total = len(self._plans)
        ready = 0
        warning = 0
        error = 0

        for plan in self._plans:
            status, _ = self._get_plan_status(plan)
            if status == "ready":
                ready += 1
            elif status == "warning":
                warning += 1
            elif status == "error":
                error += 1

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

        current_row_count = self._table.rowCount()
        target_row_count = len(self._plans)

        if current_row_count != target_row_count:
            self._table.setRowCount(target_row_count)

        # Clear selection only if we performed a structural change (add/remove)
        # to avoid losing selection during simple updates (e.g. checkbox toggle)
        if current_row_count != target_row_count:
            self._selected_plan = None

        for idx, plan in enumerate(self._plans):
            clip = plan.match.clip

            # --- Column 0: Checkbox (checkable item — travels with row sorting) ---
            chk_item = self._table.item(idx, 0)
            if not chk_item:
                chk_item = QTableWidgetItem()
                chk_item.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                chk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(idx, 0, chk_item)
            chk_item.setCheckState(
                Qt.CheckState.Checked if plan.enabled else Qt.CheckState.Unchecked
            )

            # --- Column 1: Filename ---
            filename = f"{clip.base_name}.{clip.extension}"
            if clip.is_sequence:
                filename = f"{clip.base_name}{clip.separator}####.{clip.extension}"

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
                file_item.setBackground(QColor(0, 0, 0, 0))  # Clear background
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
                ver_item.setToolTip(
                    f"Mismatch: v{plan.match.version:03d} -> v{plan.version:03d}"
                )
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
                shot_item.setForeground(QColor("#e0e0e0"))  # Default text color

            # --- Column 4: Sequence ---
            seq_text = plan.sequence_id or "—"
            seq_item = self._table.item(idx, 4)
            if not seq_item:
                seq_item = QTableWidgetItem()
                seq_item.setFlags(seq_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 4, seq_item)

            if seq_item.text() != seq_text:
                seq_item.setText(seq_text)

            # --- Column 5: Resource ---
            res_val = plan.resource or ""
            res_item = self._table.item(idx, 5)
            if not res_item:
                res_item = QTableWidgetItem()
                self._table.setItem(idx, 5, res_item)

            if res_item.text() != res_val:
                res_item.setText(res_val)

            # --- Column 6: Frames ---
            if clip.is_sequence:
                fc = clip.frame_count
            else:
                # Proper frame count for movies (handle potential None)
                m_fc = plan.media_info.frame_count or 0
                fc = m_fc if m_fc > 0 else 1

            frames_text = str(fc)
            frames_item = self._table.item(idx, 6)
            if not frames_item:
                frames_item = QTableWidgetItem()
                frames_item.setFlags(frames_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 6, frames_item)

            if frames_item.text() != frames_text:
                frames_item.setText(frames_text)

            if clip.missing_frames:
                frames_item.setBackground(QColor(150, 50, 0, 150))
                frames_item.setToolTip(
                    f"Gaps detected: {len(clip.missing_frames)} frames"
                )
            else:
                frames_item.setBackground(QColor(0, 0, 0, 0))
                frames_item.setToolTip("")

            # --- Column 7: Resolution ---
            res_text = "—"
            is_res_mismatch = False
            if plan.media_info.width and plan.media_info.height:
                res_text = f"{plan.media_info.width}x{plan.media_info.height}"
                if (self._engine._project_width or 0) > 0 and (
                    plan.media_info.width != self._engine._project_width
                    or plan.media_info.height != self._engine._project_height
                ):
                    is_res_mismatch = True

            res_item = self._table.item(idx, 7)
            if not res_item:
                res_item = QTableWidgetItem()
                res_item.setFlags(res_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 7, res_item)

            if res_item.text() != res_text:
                res_item.setText(res_text)

            if is_res_mismatch:
                res_item.setBackground(QColor(120, 100, 0, 100))
                res_item.setToolTip(
                    f"Mismatch: Project is {self._engine._project_width}x{self._engine._project_height}"
                )
            else:
                res_item.setBackground(QColor(0, 0, 0, 0))
                res_item.setToolTip("")

            # --- Column 8: FPS ---
            fps_text = f"{plan.media_info.fps:.3f}" if plan.media_info.fps > 0 else "—"
            is_fps_mismatch = False
            if (self._engine._project_fps or 0.0) > 0 and plan.media_info.fps > 0:
                if abs(plan.media_info.fps - (self._engine._project_fps or 0.0)) > 0.001:
                    is_fps_mismatch = True

            fps_item = self._table.item(idx, 8)
            if not fps_item:
                fps_item = QTableWidgetItem()
                fps_item.setFlags(fps_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 8, fps_item)

            if fps_item.text() != fps_text:
                fps_item.setText(fps_text)

            if is_fps_mismatch:
                fps_item.setBackground(QColor(120, 100, 0, 100))
                fps_item.setToolTip(
                    f"Mismatch: Project is {self._engine._project_fps or 0.0:.3f}"
                )
            else:
                fps_item.setBackground(QColor(0, 0, 0, 0))
                fps_item.setToolTip("")

            # --- Column 9: PAR ---
            par_val = plan.media_info.pixel_aspect_ratio if plan.media_info else 1.0
            par_text = f"{par_val:.2f}"
            is_par_mismatch = False
            if abs(par_val - (self._engine._project_par or 1.0)) > 0.001:
                is_par_mismatch = True

            par_item = self._table.item(idx, 9)
            if not par_item:
                par_item = QTableWidgetItem()
                par_item.setFlags(par_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 9, par_item)

            if par_item.text() != par_text:
                par_item.setText(par_text)

            if is_par_mismatch:
                par_item.setBackground(QColor(120, 100, 0, 100))
                par_item.setToolTip(
                    f"Mismatch: Project is {self._engine._project_par or 1.0:.2f}"
                )
            else:
                par_item.setBackground(QColor(0, 0, 0, 0))
                par_item.setToolTip("")

            # --- Column 10: Colorspace ---
            # Show override if set, otherwise detected colorspace
            if plan.colorspace_override:
                colorspace = f"[Override] {plan.colorspace_override}"
                colorspace_color = QColor("#00bff3")  # Blue for override
            else:
                colorspace = plan.media_info.color_space if plan.media_info else ""
                if not colorspace:
                    colorspace = "—"
                colorspace_color = QColor("#e0e0e0")  # Default text color

            cs_item = self._table.item(idx, 10)
            if not cs_item:
                cs_item = QTableWidgetItem()
                cs_item.setFlags(cs_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(idx, 10, cs_item)

            if cs_item.text() != colorspace:
                cs_item.setText(colorspace)
            cs_item.setForeground(colorspace_color)

            # --- Column 11: Status (plain item — travels with row sorting) ---
            status, status_msg = self._get_plan_status(plan)
            status_item = self._table.item(idx, 11)
            if not status_item:
                status_item = QTableWidgetItem()
                status_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(idx, 11, status_item)
            status_item.setText("○" if status == "skipped" else "●")
            status_item.setForeground(
                QColor(STATUS_DOT_COLORS.get(status, "#666666"))
            )
            status_item.setToolTip(status_msg or status.title())
            status_item.setData(Qt.ItemDataRole.UserRole, status)

            # --- Row dimming: single source of truth for enabled/disabled look ---
            default_fg = QColor("#e0e0e0")
            dim_fg = QColor(120, 120, 120)
            row_fg = default_fg if plan.enabled else dim_fg
            for col in (1, 2, 4, 5, 6, 7, 8, 9):
                it = self._table.item(idx, col)
                if it:
                    it.setForeground(row_fg)
            if not plan.enabled:
                # Shot (3) and Colorspace (10) set their own colors above;
                # override them for skipped rows.
                for col in (3, 10):
                    it = self._table.item(idx, col)
                    if it:
                        it.setForeground(dim_fg)

        self._table.blockSignals(False)
        self._table.setSortingEnabled(True)

        # 5. Visual Reconciliation (HERO FIX for Ghost Collisions)
        # Ensure that ALL rows correctly reflect their error states after the batch update.
        # This clears stale red backgrounds from rows that were previously colliding.
        for row in range(self._table.rowCount()):
            p = self._get_plan_from_row(row)
            if not p:
                continue

            f_item = self._table.item(row, 1)
            if f_item:
                if "COLLISION" in (p.error or ""):
                    f_item.setBackground(QColor(180, 50, 50, 150))
                    f_item.setToolTip(p.error)
                elif p.is_duplicate:
                    f_item.setBackground(QColor(100, 100, 100, 100))
                    f_item.setToolTip(p.error)
                else:
                    f_item.setBackground(QColor(0, 0, 0, 0))
                    # Restore standard filename tooltip
                    clip = p.match.clip
                    fname = (
                        f"{clip.base_name}{clip.separator}####.{clip.extension}"
                        if clip.is_sequence
                        else f"{clip.base_name}.{clip.extension}"
                    )
                    f_item.setToolTip(fname)

        self._update_filter_counts()
        self._update_summary()

    def _get_plan_status(self, plan: IngestPlan) -> tuple[str, str]:
        """Determine the status type and message for a plan.

        Precedence: skipped > blocking error > duplicate > warnings > ready.
        A plan whose status is "warning" WILL still be ingested; anything with
        "error"/"duplicate" is blocked (mirrors ``IngestPlan.can_execute``).
        """
        # 0. Skipped (Disabled)
        if not plan.enabled:
            return "skipped", "Skipped by user"

        # 1. Blocking errors (plan.error always blocks execution)
        if plan.error:
            return "error", plan.error

        # 2. Duplicate (blocks execution)
        if plan.is_duplicate:
            return "duplicate", f"Duplicate of v{plan.duplicate_version:03d}"

        # 3. Non-blocking warnings — HERO ONLY for technical mismatches:
        # resources (auxiliary) are allowed to deviate from project specs.
        warning_msgs = list(plan.warnings)

        if plan.match.clip.missing_frames:
            warning_msgs.insert(
                0, f"GAPS: {len(plan.match.clip.missing_frames)} missing frames"
            )

        if not plan.resource:
            if (self._engine._project_width or 0) > 0 and plan.media_info.width > 0:
                if (
                    plan.media_info.width != self._engine._project_width
                    or plan.media_info.height != self._engine._project_height
                ):
                    warning_msgs.append("Technical mismatch (Resolution)")

            if (self._engine._project_fps or 0.0) > 0 and plan.media_info.fps > 0:
                if abs(plan.media_info.fps - (self._engine._project_fps or 0.0)) > 0.001:
                    warning_msgs.append("Technical mismatch (FPS)")

        if warning_msgs:
            return "warning", " | ".join(warning_msgs)

        # 4. Ready (Success)
        if plan.can_execute:
            return "ready", ""

        return "pending", ""

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
                    item = self._table.item(row, 3)  # Shot column (was 2)
                    if item:
                        item.setText(shot_id)

            self._update_summary()

    def _on_context_filename_as_shot(self) -> None:
        """Set each selected clip's filename stem as its shot ID"""
        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        if not selected_rows:
            return

        for row in selected_rows:
            plan = self._get_plan_from_row(row)
            if plan:
                shot_id = plan.match.clip.base_name
                plan.shot_id = shot_id
                item = self._table.item(row, 3)  # Shot column
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

    def _on_context_override_res(self) -> None:
        """Override resource for selected clips"""
        from PySide6.QtWidgets import QInputDialog

        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        if not selected_rows:
            return

        res, ok = QInputDialog.getText(
            self,
            "Override Resource",
            f"Enter resource for {len(selected_rows)} clip(s) (e.g. PLATE, BG):",
        )

        if ok:
            for row in selected_rows:
                plan = self._get_plan_from_row(row)
                if plan:
                    plan.resource = res

            # Re-resolve paths (this triggers re-calc and table refresh for collision status)
            self._on_resolve_timeout()

    def _on_context_override_colorspace(self) -> None:
        """Override colorspace for selected clips"""
        from PySide6.QtWidgets import QInputDialog

        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        if not selected_rows:
            return

        # Same list as the Options dropdown (single source of truth)
        colorspace_list = list(STANDARD_COLORSPACES)

        # Get current colorspace from first selected clip (if any)
        first_plan = self._get_plan_from_row(selected_rows[0])
        current_cs = ""
        if first_plan:
            current_cs = (
                first_plan.colorspace_override
                or (first_plan.media_info.color_space if first_plan.media_info else "")
                or "sRGB"
            )

        # Editable: OCIO configs differ, so any colorspace name from the
        # studio's config may be typed — the curated list is a starting point.
        colorspace, ok = QInputDialog.getItem(
            self,
            "Override Colorspace",
            f"Select colorspace for {len(selected_rows)} clip(s)\n"
            "(must exist in the loaded OCIO config):",
            colorspace_list,
            colorspace_list.index(current_cs) if current_cs in colorspace_list else 0,
            editable=True,
        )

        if ok and colorspace:
            for row in selected_rows:
                plan = self._get_plan_from_row(row)
                if plan:
                    plan.colorspace_override = colorspace
                    # Update Colorspace column (10) with override indicator
                    item = self._table.item(row, 10)
                    if item:
                        item.setText(f"[Override] {colorspace}")
                        item.setForeground(QColor("#00bff3"))  # Blue to indicate override

            self._update_summary()

    def _on_context_override_fps(self) -> None:
        """Batch-override the framerate for the selected clips.

        Image sequences carry no embedded framerate, so the probed fps is 0
        and the shot duration written to Ramses would fall back to a default.
        The override becomes the source of truth for validation, DB duration
        (frames / fps) and the report.
        """
        from PySide6.QtWidgets import QInputDialog

        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        if not selected_rows:
            return

        # Sensible starting value: first clip's fps, else the project standard
        first_plan = self._get_plan_from_row(selected_rows[0])
        current = 0.0
        if first_plan and first_plan.media_info:
            current = first_plan.media_info.fps or 0.0
        if not current:
            current = self._engine._project_fps or 25.0

        fps, ok = QInputDialog.getDouble(
            self,
            "Override FPS",
            f"Framerate for {len(selected_rows)} clip(s):",
            value=current,
            minValue=1.0,
            maxValue=240.0,
            decimals=3,
        )
        if not ok or fps <= 0:
            return

        for row in selected_rows:
            plan = self._get_plan_from_row(row)
            if plan and plan.media_info:
                # Stash the probed value once so Clear Overrides can restore it
                if not hasattr(plan, "_probed_fps"):
                    plan._probed_fps = plan.media_info.fps
                plan.media_info.fps = fps
                # Reports mark operator-set values so the client can flag them
                plan.fps_is_manual = True

        self._log(f"FPS override: {fps:g} fps applied to {len(selected_rows)} clip(s).")
        # Re-validate + repopulate (mismatch highlighting, summary, dots)
        self._on_resolve_timeout()

    def _on_context_clear_overrides(self) -> None:
        """Clear all overrides for selected clips (reset to auto-detected values)"""
        selected_rows = list(set(item.row() for item in self._table.selectedItems()))
        if not selected_rows:
            return

        for row in selected_rows:
            plan = self._get_plan_from_row(row)
            if plan:
                # Clear colorspace override
                plan.colorspace_override = ""

                # Restore the probed framerate if an FPS override was applied
                if hasattr(plan, "_probed_fps") and plan.media_info:
                    plan.media_info.fps = plan._probed_fps
                    del plan._probed_fps
                if hasattr(plan, "fps_is_manual"):
                    del plan.fps_is_manual

                # Restore shot/seq/resource from original pattern match
                if plan.match and plan.match.matched:
                    # Re-extract shot and sequence from the original match result
                    plan.shot_id = plan.match.shot_id or ""
                    plan.sequence_id = plan.match.sequence_id or ""
                    # Resource from original match
                    plan.resource = plan.match.resource or ""

        # Re-resolve paths (recalculates collisions and target paths)
        self._resolve_all_paths()
        # Refresh table to show restored values
        self._populate_table()
        self._update_summary()

    def _set_selected_enabled(self, enabled: bool) -> None:
        """Enable/skip the selected clips and schedule a debounced refresh.

        The refresh (``_on_resolve_timeout``) re-resolves collisions/duplicates
        and repopulates the table, which also updates dimming, status dots,
        summary, and filter counts — the single source of visual truth.
        """
        selected_rows = set(item.row() for item in self._table.selectedItems())
        if not selected_rows:
            return

        self._table.blockSignals(True)
        try:
            for row in selected_rows:
                plan = self._get_plan_from_row(row)
                if not plan:
                    continue
                plan.enabled = enabled
                chk_item = self._table.item(row, 0)
                if chk_item:
                    chk_item.setCheckState(
                        Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked
                    )
        finally:
            self._table.blockSignals(False)

        self._resolve_timer.start()

    def _on_context_enable(self) -> None:
        """Enable selected clips (check them)."""
        self._set_selected_enabled(True)

    def _on_context_skip(self) -> None:
        """Skip selected clips (uncheck them)."""
        self._set_selected_enabled(False)

    # -- Helpers -------------------------------------------------------------

    def _log(self, msg: str) -> None:
        """Add syntax highlighting for log messages and append to log edit."""
        msg_upper = msg.upper()

        # 1. Error Check (Highest Priority)
        # We check errors first because a message like "Complete: 1 failed"
        # should be red, even though it contains "Complete".
        has_error = any(
            k in msg_upper
            for k in ["ERROR", "FAILED", "CRITICAL", "FAIL", "✖", ": FAILED"]
        )

        # Exception: "0 FAILED" or "0 FAIL" usually means success in a summary context
        if has_error and ("0 FAILED" in msg_upper or "0 FAIL" in msg_upper):
            # Only downgrade if it doesn't contain actual ERROR or CRITICAL labels elsewhere
            if not any(
                k in msg_upper for k in ["ERROR", "CRITICAL", "✖", "INGEST ERROR"]
            ):
                has_error = False

        if has_error:
            colored_msg = (
                f'<span style="color: #f44747; font-weight: bold;">{msg}</span>'
            )

        # 2. Success Check
        elif any(
            k in msg_upper
            for k in [
                "SUCCEEDED",
                "COMPLETE",
                "SUCCESS",
                "DONE",
                "✓",
                ": OK",
                "MAPPED",
                "READY:",
                "MATCHED",
            ]
        ):
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
            check_for_duplicates,
        )

        # 0. RESET: Clear old paths and transient errors before re-calculating
        for p in self._plans:
            p.target_publish_dir = ""
            p.target_preview_dir = ""
            # Clear collision and duplicate errors (they will be re-evaluated)
            if "COLLISION" in (p.error or "") or "Duplicate" in (p.error or ""):
                p.error = ""
            p.is_duplicate = False

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

        # 4. Re-check for duplicates (Resource-aware now)
        check_for_duplicates(self._plans)

    def _try_connect(self, _=None) -> None:
        """Start background connection attempt."""
        if self._connection_worker and self._connection_worker.isRunning():
            return

        # UI Feedback: Connecting state
        self._status_label.setText("CONNECTING...")
        self._status_label.setObjectName("statusConnecting")
        self._status_label.setStyleSheet(
            ""
        )  # Clear inline style to let objectName take over
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

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
            self._status_label.setStyleSheet("")  # Clear any inline styles
            pid = self._engine.project_id
            pname = self._engine.project_name
            self._project_label_display.setText(f"{pid} - {pname}")

            # Update Standards display
            fps = self._engine._project_fps or 0.0
            w = self._engine._project_width or 0
            h = self._engine._project_height or 0
            par = self._engine._project_par
            self._standards_label.setText(f"PROJECT SETTINGS: {w}x{h} @ {fps:.3f} FPS | PAR: {par}")

            # Populate steps
            self._step_combo.blockSignals(True)
            self._step_combo.clear()
            for s in self._engine.steps:
                self._step_combo.addItem(s)

            # engine.connect() already normalized step_id case-insensitively
            # (prefers the plate step, keeps a still-valid previous choice)
            self._step_combo.setCurrentText(self._engine.step_id)

            # CRITICAL: Re-sync engine state with whatever was actually selected
            self._engine.step_id = self._step_combo.currentText()
            self._step_combo.blockSignals(False)

            # Project report needs a connected project to walk
            self._btn_project_report.setEnabled(True)

            # If we were already working, refresh paths now that we're connected
            if self._plans:
                self._resolve_all_paths()
                self._populate_table()

        else:
            self._status_label.setText("OFFLINE")
            self._status_label.setObjectName("statusDisconnected")
            self._status_label.setStyleSheet("")  # Clear any inline styles
            self._project_label_display.setText("— (Connection Required)")
            self._btn_ingest.setToolTip("Ramses connection required to ingest.")
            self._btn_project_report.setEnabled(False)

            self._btn_reconnect.setVisible(True)
            self._btn_refresh.setVisible(
                False
            )  # Only show Refresh when connected (manual reload)

            if not self._reconnect_timer.isActive():
                self._reconnect_timer.start()

        # Re-polish to apply dynamic objectName change
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        self._update_summary()

    def _populate_rule_combo(self, combo: QComboBox | None = None) -> None:
        target = combo or self._rule_combo
        was_blocked = target.blockSignals(True)
        target.clear()
        target.addItem("Auto-detect")

        from ramses_ingest.matcher import BUILTIN_RULES

        builtin_patterns = {r.pattern for r in BUILTIN_RULES}

        rules = self._engine.rules
        for i, rule in enumerate(rules):
            label = rule.pattern
            if len(label) > 50:
                label = label[:50] + "..."

            prefix = "Default" if rule.pattern in builtin_patterns else "Custom"
            target.addItem(f"{prefix} {i + 1}: {label}")

        target.blockSignals(was_blocked)

    def _update_summary(self) -> None:
        if not self._plans:
            self._summary_label.setText("No delivery loaded.")
            self._btn_ingest.setText("Ingest 0/0")
            self._btn_ingest.setEnabled(False)
            return

        total = len(self._plans)
        new_shots = sum(1 for p in self._plans if p.is_new_shot and p.match.matched)

        # Count enabled items
        enabled_plans = [p for p in self._plans if p.enabled]
        n_enabled = len(enabled_plans)
        n_skipped = total - n_enabled

        # Count status types (only for enabled plans). Derived from
        # _get_plan_status so summary, filter counts, and status dots always
        # agree. "warning" plans still execute; "error"/"duplicate" are blocked.
        ready_count = warning_count = error_count = 0
        for p in enabled_plans:
            status, _ = self._get_plan_status(p)
            if status == "ready":
                ready_count += 1
            elif status == "warning":
                warning_count += 1
            elif status in ("error", "duplicate"):
                error_count += 1

        # Build summary with color coding
        summary_parts = [f"<b>{total} clips</b>"]

        if n_skipped > 0:
            summary_parts.append(
                f"<span style='color: #888;'>({n_enabled} selected)</span>"
            )

        if ready_count > 0:
            summary_parts.append(
                f"<span style='color: #27ae60;'>{ready_count} ready</span>"
            )
        if warning_count > 0:
            summary_parts.append(
                f"<span style='color: #f39c12;'>{warning_count} warnings</span>"
            )
        if error_count > 0:
            summary_parts.append(
                f"<span style='color: #f44747;'>{error_count} errors</span>"
            )

        if new_shots > 0:
            summary_parts.append(f"{new_shots} new shots")

        self._summary_label.setText(" • ".join(summary_parts))

        # Set overall label color based on status of ENABLED items
        if error_count > 0:
            label_color = "#f44747"
        elif warning_count > 0:
            label_color = "#f39c12"
        elif ready_count > 0:
            label_color = "#27ae60"
        else:
            label_color = "#888888"

        self._summary_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {label_color};"
        )

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
                self._btn_ingest.setStyleSheet(
                    ""
                )  # Revert to stylesheet default (muted)

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

    def _on_studio_changed(self, text: str) -> None:
        """Update engine and persist studio name and logo to config."""
        self._engine.studio_name = text
        save_rules(self._engine.rules, studio_name=text, studio_logo=self._engine.studio_logo)

    def _browse_studio_logo(self, path_edit: QLineEdit) -> None:
        """Browse for studio logo image file."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Studio Logo", "", 
            "Images (*.png *.jpg *.jpeg *.png *.bmp);;All Files (*)"
        )
        if path:
            path_edit.setText(path)

    def _on_open_destination(self, _=None) -> None:
        """Open the last ingest's destination in the file manager.

        One shot ingested → open its publish folder directly; several →
        open the deepest common parent so everything is one click away.
        """
        if not self._last_dest_dirs:
            return
        if len(self._last_dest_dirs) == 1:
            target = self._last_dest_dirs[0]
        else:
            try:
                target = os.path.commonpath(self._last_dest_dirs)
            except ValueError:
                # Different drives — fall back to the first destination
                target = self._last_dest_dirs[0]
        if os.path.isdir(target):
            self._open_folder(target)

    def _on_view_report(self, _=None) -> None:
        """Open the last generated HTML report in the system browser."""
        if self._engine.last_report_path and os.path.exists(
            self._engine.last_report_path
        ):
            import webbrowser

            webbrowser.open(f"file:///{os.path.abspath(self._engine.last_report_path)}")

    def _on_project_report(self, _=None) -> None:
        """Build the whole-project ingest report in the background.

        When a previous project report exists, offers a delta report covering
        only footage ingested since then — for later deliveries the client
        gets just the new files instead of the full report again.
        """
        if self._report_worker and self._report_worker.isRunning():
            return

        since = None
        last_ts = self._engine.last_project_report_time()
        if last_ts:
            import time as _time
            last_str = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(last_ts))
            box = QMessageBox(self)
            box.setWindowTitle("Project Report")
            box.setText(
                f"A project report was last generated on {last_str}.\n\n"
                "Full report of everything ingested, or only footage\n"
                "ingested since then (for a new delivery)?"
            )
            btn_full = box.addButton("Full Report", QMessageBox.ButtonRole.AcceptRole)
            btn_new = box.addButton(f"New since {last_str}", QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked is btn_new:
                since = last_ts
            elif clicked is not btn_full:
                return  # cancelled

        self._btn_project_report.setEnabled(False)
        self._btn_project_report.setText("Building...")
        self._log("Building project ingest report...")
        self._report_worker = ProjectReportWorker(self._engine, since=since, parent=self)
        self._report_worker.progress.connect(self._log)
        self._report_worker.finished_report.connect(self._on_project_report_done)
        self._report_worker.start()

    def _on_project_report_done(self, path: str) -> None:
        self._btn_project_report.setText("Project Report")
        self._btn_project_report.setEnabled(self._engine.connected)
        if path and os.path.exists(path):
            self._log(f"Project report: {path}")
            import webbrowser

            webbrowser.open(f"file:///{os.path.abspath(path)}")
        else:
            QMessageBox.information(
                self,
                "Project Report",
                "No ingested versions were found in this project\n"
                "(or nothing new since the last report).",
            )

    def keyPressEvent(self, event) -> None:
        """Handle Delete key for batch removal."""
        if event.key() == Qt.Key.Key_Delete:
            self._on_remove_selected()
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

        act_filename_as_shot = QAction("Set Filename as Shot ID", self)
        act_filename_as_shot.triggered.connect(self._on_context_filename_as_shot)
        menu.addAction(act_filename_as_shot)

        act_override_seq = QAction("Override Sequence ID...", self)
        act_override_seq.triggered.connect(self._on_context_override_seq)
        menu.addAction(act_override_seq)

        act_override_res = QAction("Override Resource...", self)
        act_override_res.triggered.connect(self._on_context_override_res)
        menu.addAction(act_override_res)

        act_override_cs = QAction("Override Colorspace...", self)
        act_override_cs.triggered.connect(self._on_context_override_colorspace)
        menu.addAction(act_override_cs)

        act_override_fps = QAction("Override FPS...", self)
        act_override_fps.triggered.connect(self._on_context_override_fps)
        menu.addAction(act_override_fps)

        menu.addSeparator()

        act_clear_overrides = QAction("Clear Overrides", self)
        act_clear_overrides.triggered.connect(self._on_context_clear_overrides)
        menu.addAction(act_clear_overrides)

        menu.addSeparator()

        act_enable = QAction("Enable Selected", self)
        act_enable.triggered.connect(self._on_context_enable)
        menu.addAction(act_enable)

        act_skip = QAction("Skip Selected", self)
        act_skip.triggered.connect(self._on_context_skip)
        menu.addAction(act_skip)

        menu.addSeparator()

        # Single selection actions
        if len(selected_rows) == 1:
            row = selected_rows[0]
            plan = self._get_plan_from_row(row)
            if plan:

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
        # Deduplicate: only add clips that aren't already in the list
        existing_paths = {p.match.clip.first_file for p in self._plans}

        to_add = []
        skipped = 0
        for p in plans:
            if p.match.clip.first_file not in existing_paths:
                to_add.append(p)
                existing_paths.add(p.match.clip.first_file)
            else:
                skipped += 1

        if to_add:
            self._plans.extend(to_add)
            self._populate_table()

        self._drop_zone._label.setText("Drop Footage Here\nAccepts folders and files")

        msg = f"Scan complete: {len(to_add)} new clip(s) detected."
        if skipped > 0:
            msg += f" ({skipped} duplicates skipped)"
        self._log(msg)

    def _on_scan_error(self, msg: str) -> None:
        self._log(f"ERROR: {msg}")
        self._drop_zone._label.setText("Drop Footage Here\nAccepts folders and files")

    def _on_clear(self, _=None) -> None:
        self._plans.clear()
        self._table.setRowCount(0)
        self._update_summary()
        self._log_edit.clear()
        self._progress.setVisible(False)
        self._last_dest_dirs = []
        self._btn_open_dest.setVisible(False)

    def _on_cancel(self, _=None) -> None:
        if self._ingest_worker and self._ingest_worker.isRunning():
            self._ingest_worker.cancel()
            self._btn_cancel.setEnabled(False)
            self._log("Cancel requested — finishing current items before stopping...")

    def _on_ingest(self, _=None) -> None:
        enabled = self._get_enabled_plans()
        if not enabled:
            return

        # Freeze plan-mutating UI for the duration of the ingest: worker
        # threads read the plans' target paths while copying.
        self._resolve_timer.stop()
        self._set_ui_locked(True)

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
        self._progress.setVisible(False)
        self._set_ui_locked(False)

        if self._engine.last_report_path:
            self._btn_view_report.setVisible(True)

        # Offer to jump straight to the ingested files
        self._last_dest_dirs = sorted({
            r.published_path for r in results
            if r.success and r.published_path and os.path.isdir(r.published_path)
        })
        self._btn_open_dest.setVisible(bool(self._last_dest_dirs))

        ok = sum(1 for r in results if r.success)
        cancelled = sum(1 for r in results if not r.success and r.error == "Cancelled")
        fail = len(results) - ok - cancelled
        if cancelled:
            self._log(f"Ingest cancelled: {ok} succeeded, {fail} failed, {cancelled} not started.")
        else:
            self._log(f"Ingest complete: {ok} succeeded, {fail} failed.")

    def _on_ingest_error(self, msg: str) -> None:
        self._btn_cancel.setVisible(False)
        self._btn_ingest.setEnabled(True)
        self._progress.setVisible(False)
        self._set_ui_locked(False)
        self._log(f"INGEST ERROR: {msg}")

    def _on_edit_rules(self, _=None) -> None:
        # Seed the user config from the currently-loaded rules on first use so
        # the editor always has something meaningful to display.
        if not os.path.isfile(USER_RULES_PATH):
            try:
                save_rules(
                    self._engine.rules,
                    studio_name=self._engine.studio_name,
                    studio_logo=self._engine.studio_logo,
                )
            except Exception:
                pass
        dlg = RulesEditorDialog(USER_RULES_PATH, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Load updated rules from disk first
            rules, studio, logo = load_rules()
            self._engine.rules = rules
            self._engine.studio_name = studio
            self._engine.studio_logo = logo
            self._studio_edit.setText(studio)

            # Then refresh the UI with the updated rules
            self._populate_rule_combo()
            self._log("Rules and Studio branding reloaded.")

    def _on_reset_rules(self, _=None) -> None:
        """Reset rules to the built-in defaults."""
        from PySide6.QtWidgets import QMessageBox
        from ramses_ingest.matcher import BUILTIN_RULES

        reply = QMessageBox.question(
            self,
            "Reset to Default Rules",
            "This will restore the default built-in naming rules and discard all custom rules.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Reset to built-in rules
            self._engine.rules = BUILTIN_RULES.copy()
            self._engine.studio_name = "Ramses Studio"
            self._studio_edit.setText(self._engine.studio_name)

            # Persist to user config (overwrites any accumulated custom rules)
            save_rules(
                self._engine.rules,
                studio_name=self._engine.studio_name,
            )

            # Refresh UI
            self._populate_rule_combo()
            self._log("Rules reset to default built-in patterns.")

    def _on_launch_smart_pattern(self, _=None) -> None:
        """Launch the smart pattern builder and apply the result."""
        from ramses_ingest.smart_pattern_dialog import SmartPatternDialog
        from ramses_ingest.matcher import NamingRule

        dlg = SmartPatternDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            regex = dlg.get_final_regex()

            if regex:
                existing_patterns = {r.pattern for r in self._engine.rules}
                if regex in existing_patterns:
                    self._log("Pattern already exists in rules — not added again.")
                else:
                    # Add to engine's rules and persist
                    new_rule = NamingRule(pattern=regex, name="New Smart Rule")
                    current_rules = self._engine.rules
                    current_rules.insert(0, new_rule)
                    self._engine.rules = current_rules
                    try:
                        save_rules(
                            self._engine.rules,
                            studio_name=self._engine.studio_name,
                        )
                        self._log("Added new naming rule from Smart Pattern builder.")
                    except Exception as e:
                        self._log(f"Warning: Could not save rules to config: {e}")

                    # Refresh UI
                    self._populate_rule_combo()
                    self._rule_combo.setCurrentIndex(1)  # Select the newly created rule
                    self._log(f"New rule created: {regex}")
            else:
                self._log("Smart Pattern builder returned empty rule - skipping.")

    def _on_load_edl(self, _=None) -> None:
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
            # Newly matched plans have no target paths yet — resolve them now,
            # otherwise execution fails with "No target publish directory".
            self._resolve_all_paths()
            self._populate_table()
        else:
            self._log("  No matches found in EDL.")

    def closeEvent(self, event) -> None:
        """Cancel and join background workers before the window is destroyed."""
        if self._ingest_worker and self._ingest_worker.isRunning():
            self._ingest_worker.cancel()
            if not self._ingest_worker.wait(5000):
                try:
                    self._ingest_worker.finished_results.disconnect()
                    self._ingest_worker.progress.disconnect()
                    self._ingest_worker.step_done.disconnect()
                    self._ingest_worker.error.disconnect()
                except RuntimeError:
                    pass
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.quit()
            if not self._scan_worker.wait(2000):
                try:
                    self._scan_worker.finished_plans.disconnect()
                    self._scan_worker.error.disconnect()
                except RuntimeError:
                    pass
        if self._connection_worker and self._connection_worker.isRunning():
            self._connection_worker.quit()
            if not self._connection_worker.wait(2000):
                try:
                    self._connection_worker.finished.disconnect()
                except RuntimeError:
                    pass
        super().closeEvent(event)

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
