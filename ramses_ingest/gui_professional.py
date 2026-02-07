# Professional Master-Detail UI Implementation
# This file contains the improved _build_ui method for IngestWindow
# Copy this method to replace the existing _build_ui in gui.py

def _build_ui_professional(self) -> None:
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
    header.setStyleSheet("background-color: #1e1e1e; border-radius: 4px; padding: 6px;")
    header_lay = QHBoxLayout(header)
    header_lay.setContentsMargins(8, 4, 8, 4)
    header_lay.setSpacing(12)

    # Status orb
    self._status_orb = QFrame()
    self._status_orb.setObjectName("statusOrb")
    self._status_orb.setStyleSheet("background-color: #f44747; border: 1px solid rgba(255,255,255,0.1);")
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
    self._filter_ready.setStyleSheet("QPushButton { text-align: left; color: #4ec9b0; }")
    self._filter_ready.clicked.connect(lambda: self._apply_filter("ready"))
    left_lay.addWidget(self._filter_ready)

    self._filter_warning = QPushButton("● Warnings (0)")
    self._filter_warning.setCheckable(True)
    self._filter_warning.setStyleSheet("QPushButton { text-align: left; color: #f39c12; }")
    self._filter_warning.clicked.connect(lambda: self._apply_filter("warning"))
    left_lay.addWidget(self._filter_warning)

    self._filter_error = QPushButton("● Errors (0)")
    self._filter_error.setCheckable(True)
    self._filter_error.setStyleSheet("QPushButton { text-align: left; color: #f44747; }")
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
    self._table.setColumnCount(7)
    self._table.setHorizontalHeaderLabels([
        "", "Filename", "Shot", "Seq", "Frames", "Res", "Status"
    ])
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
    for col in [2, 3, 4, 5]:  # Shot, Seq, Frames, Res
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(col, 80)
    header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
    header.resizeSection(6, 55)  # Status (dot)

    # Set delegate for inline editing
    self._table.setItemDelegateForColumn(2, EditableDelegate(self._table))  # Shot column

    center_lay.addWidget(self._table, 1)

    main_splitter.addWidget(center_panel)

    # ───────────────────────────────────────────────────────────────────────
    # RIGHT PANEL: Detail Panel (20%)
    # ───────────────────────────────────────────────────────────────────────
    right_panel = QFrame()
    right_panel.setStyleSheet("background-color: #1a1a1a; border-radius: 4px;")
    right_panel.setMinimumWidth(180)
    right_panel.setMaximumWidth(260)
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

    right_lay.addStretch()

    main_splitter.addWidget(right_panel)

    # Set splitter proportions (20% | 60% | 20%)
    main_splitter.setSizes([200, 600, 200])

    root.addWidget(main_splitter, 1)

    # ═══════════════════════════════════════════════════════════════════════
    # BOTTOM ACTION BAR
    # ═══════════════════════════════════════════════════════════════════════
    action_bar = QFrame()
    action_bar.setStyleSheet("background-color: #1e1e1e; border-radius: 4px; padding: 6px;")
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
