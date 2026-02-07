# Professional Architect Dialog Implementation
# Replace _setup_ui in NamingArchitectDialog class

def _setup_ui_professional(self) -> None:
    """Professional single-screen layout (no sidebars, no splitters)"""
    main_layout = QVBoxLayout(self)
    main_layout.setContentsMargins(15, 15, 15, 15)
    main_layout.setSpacing(12)

    # ═══════════════════════════════════════════════════════════════════════
    # HEADER - Presets Dropdown (Not Sidebar)
    # ═══════════════════════════════════════════════════════════════════════
    header = QHBoxLayout()
    header.addWidget(QLabel("Quick Start:"))

    self.preset_combo = QComboBox()
    self.preset_combo.addItem("— Build Custom Rule —")
    self.preset_combo.addItem("Standard Shot (SEQ_SHOT)")
    self.preset_combo.addItem("Shot & Version (SEQ_SHOT_v01)")
    self.preset_combo.addItem("Technicolor (PROJ_SEQ_SHOT)")
    self.preset_combo.addItem("Flat Delivery (SHOT only)")
    self.preset_combo.setMinimumWidth(240)
    self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
    header.addWidget(self.preset_combo)

    header.addStretch()

    self.btn_magic = QPushButton("✨ Magic Wand")
    self.btn_magic.setStyleSheet("background-color: #4a4a4a; color: #00bff3; font-weight: bold; padding: 8px 16px;")
    self.btn_magic.clicked.connect(self._on_magic_wand)
    self.btn_magic.setEnabled(False)
    self.btn_magic.setToolTip("Auto-detect pattern from sample filenames")
    header.addWidget(self.btn_magic)

    main_layout.addLayout(header)

    # ═══════════════════════════════════════════════════════════════════════
    # BLUEPRINT AREA - Large, Prominent (80px height)
    # ═══════════════════════════════════════════════════════════════════════
    lbl_blue = QLabel("PATTERN BLUEPRINT")
    lbl_blue.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
    main_layout.addWidget(lbl_blue)

    self.blueprint_container = QFrame()
    self.blueprint_container.setFixedHeight(80)  # Larger for easier drag-drop
    self.blueprint_container.setStyleSheet("""
        background-color: #1a1a1a;
        border: 2px dashed #444;
        border-radius: 6px;
    """)

    blueprint_lay = QHBoxLayout(self.blueprint_container)
    blueprint_lay.setContentsMargins(8, 8, 8, 8)

    self.drop_zone = TokenDropZone()
    self.drop_zone.changed.connect(self._on_rule_changed)
    self.drop_zone.token_clicked.connect(self._on_token_clicked)
    blueprint_lay.addWidget(self.drop_zone)

    main_layout.addWidget(self.blueprint_container)

    # ═══════════════════════════════════════════════════════════════════════
    # TOKEN PALETTE - Compact Dropdown (Not Buttons)
    # ═══════════════════════════════════════════════════════════════════════
    palette_row = QHBoxLayout()
    palette_row.addWidget(QLabel("Add Token:"))

    self.token_combo = QComboBox()
    self.token_combo.addItem("— Select Token —")
    self.token_combo.addItem("🎬 Sequence")
    self.token_combo.addItem("🎥 Shot")
    self.token_combo.addItem("📦 Version")
    self.token_combo.addItem("🔧 Step")
    self.token_combo.addItem("📁 Project")
    self.token_combo.addItem("━ Separator: _")
    self.token_combo.addItem("━ Separator: .")
    self.token_combo.addItem("━ Separator: -")
    self.token_combo.addItem("🌐 Wildcard")
    self.token_combo.addItem("⊘ Ignore")
    self.token_combo.currentIndexChanged.connect(self._on_token_selected)
    palette_row.addWidget(self.token_combo)

    palette_row.addSpacing(20)
    palette_row.addWidget(QLabel("Click token in blueprint to edit properties"))
    palette_row.addStretch()

    main_layout.addLayout(palette_row)

    # ═══════════════════════════════════════════════════════════════════════
    # MAIN AREA - Side-by-Side Samples | Results (Not Vertical Splitter)
    # ═══════════════════════════════════════════════════════════════════════
    main_area = QHBoxLayout()
    main_area.setSpacing(12)

    # ───────────────────────────────────────────────────────────────────────
    # LEFT: Sample Input (40%)
    # ───────────────────────────────────────────────────────────────────────
    left_panel = QWidget()
    left_lay = QVBoxLayout(left_panel)
    left_lay.setContentsMargins(0, 0, 0, 0)
    left_lay.setSpacing(6)

    lbl_samples = QLabel("SAMPLE FILENAMES")
    lbl_samples.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
    left_lay.addWidget(lbl_samples)

    self.sample_edit = QTextEdit()
    self.sample_edit.setPlaceholderText(
        "Paste sample filenames here:\n\n"
        "SEQ010_SH010_v001.exr\n"
        "SEQ020_SH030_v002.exr\n"
        "bad_file_01.mov"
    )
    self.sample_edit.setMinimumHeight(200)
    self.sample_edit.setStyleSheet("""
        QTextEdit {
            background-color: #1e1e1e;
            border: 1px solid #444;
            border-radius: 4px;
            padding: 8px;
            font-family: 'Consolas', monospace;
            font-size: 11px;
        }
    """)
    self.sample_edit.textChanged.connect(self._on_samples_changed)
    left_lay.addWidget(self.sample_edit)

    left_panel.setMaximumWidth(400)
    main_area.addWidget(left_panel)

    # ───────────────────────────────────────────────────────────────────────
    # RIGHT: Live Results (60%)
    # ───────────────────────────────────────────────────────────────────────
    right_panel = QWidget()
    right_lay = QVBoxLayout(right_panel)
    right_lay.setContentsMargins(0, 0, 0, 0)
    right_lay.setSpacing(6)

    # Header with stats
    result_header = QHBoxLayout()
    lbl_results = QLabel("LIVE SIMULATION")
    lbl_results.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
    result_header.addWidget(lbl_results)

    result_header.addStretch()

    self.match_stats = QLabel("0/0 matched (0%)")
    self.match_stats.setStyleSheet("color: #00bff3; font-size: 10px; font-weight: bold;")
    result_header.addWidget(self.match_stats)

    right_lay.addLayout(result_header)

    self.sim_table = SimulationTable()
    self.sim_table.setMinimumHeight(200)
    right_lay.addWidget(self.sim_table)

    main_area.addWidget(right_panel, 1)

    main_layout.addLayout(main_area, 1)

    # ═══════════════════════════════════════════════════════════════════════
    # FOOTER - Regex Display & Actions
    # ═══════════════════════════════════════════════════════════════════════

    # Regex display (collapsible)
    regex_container = QFrame()
    regex_container.setStyleSheet("background-color: #1e1e1e; border-radius: 4px; padding: 8px;")
    regex_lay = QVBoxLayout(regex_container)
    regex_lay.setContentsMargins(8, 8, 8, 8)
    regex_lay.setSpacing(4)

    regex_header = QHBoxLayout()
    self.regex_toggle = QPushButton("▼ Generated Regex")
    self.regex_toggle.setStyleSheet("text-align: left; background: transparent; border: none; color: #888;")
    self.regex_toggle.clicked.connect(self._toggle_regex)
    regex_header.addWidget(self.regex_toggle)
    regex_header.addStretch()

    btn_copy_regex = QPushButton("Copy")
    btn_copy_regex.setMaximumWidth(60)
    btn_copy_regex.clicked.connect(self._copy_regex)
    regex_header.addWidget(btn_copy_regex)

    regex_lay.addLayout(regex_header)

    self.regex_label = QLabel("—")
    self.regex_label.setStyleSheet("""
        font-family: 'Consolas', monospace;
        color: #4ec9b0;
        font-size: 10px;
        padding: 4px;
    """)
    self.regex_label.setWordWrap(True)
    self.regex_label.setVisible(False)  # Collapsed by default
    regex_lay.addWidget(self.regex_label)

    main_layout.addWidget(regex_container)

    # Action buttons
    btn_row = QHBoxLayout()
    btn_row.addStretch()

    btn_cancel = QPushButton("Cancel")
    btn_cancel.setMinimumWidth(100)
    btn_cancel.clicked.connect(self.reject)
    btn_row.addWidget(btn_cancel)

    btn_apply = QPushButton("Apply to Project")
    btn_apply.setMinimumWidth(140)
    btn_apply.setMinimumHeight(36)
    btn_apply.setStyleSheet("background-color: #00bff3; color: white; font-weight: bold;")
    btn_apply.clicked.connect(self.accept)
    btn_row.addWidget(btn_apply)

    main_layout.addLayout(btn_row)


# ═══════════════════════════════════════════════════════════════════════
# Supporting Methods (Add to NamingArchitectDialog)
# ═══════════════════════════════════════════════════════════════════════

def _on_preset_selected(self, index: int) -> None:
    """Apply preset from dropdown"""
    if index == 0:  # "Build Custom Rule"
        return

    presets = {
        1: [TokenType.SEQUENCE, "_", TokenType.SHOT],  # Standard Shot
        2: [TokenType.SEQUENCE, "_", TokenType.SHOT, "_", TokenType.VERSION],  # Shot & Version
        3: [TokenType.PROJECT, "_", TokenType.SEQUENCE, "_", TokenType.SHOT],  # Technicolor
        4: [TokenType.SHOT],  # Flat Delivery
    }

    pattern = presets.get(index, [])
    self._apply_preset(pattern)

    # Reset combo to default
    self.preset_combo.setCurrentIndex(0)


def _on_token_selected(self, index: int) -> None:
    """Add token from dropdown"""
    if index == 0:  # "Select Token"
        return

    token_map = {
        1: TokenType.SEQUENCE,
        2: TokenType.SHOT,
        3: TokenType.VERSION,
        4: TokenType.STEP,
        5: TokenType.PROJECT,
        6: ("_", TokenType.SEPARATOR),
        7: (".", TokenType.SEPARATOR),
        8: ("-", TokenType.SEPARATOR),
        9: TokenType.WILDCARD,
        10: TokenType.IGNORE,
    }

    selection = token_map.get(index)
    if isinstance(selection, tuple):
        # Separator with specific value
        value, ttype = selection
        self.drop_zone.add_token(ArchitectToken(type=ttype, value=value))
    else:
        # Regular token
        self.drop_zone.add_token(ArchitectToken(type=selection))

    # Reset combo
    self.token_combo.setCurrentIndex(0)
    self._on_rule_changed()


def _on_token_clicked(self, token: ArchitectToken) -> None:
    """Show inline editor for token (not sidebar)"""
    from PySide6.QtWidgets import QInputDialog

    if token.type == TokenType.SEPARATOR:
        value, ok = QInputDialog.getText(
            self, "Edit Separator",
            "Separator character:",
            text=token.value
        )
        if ok:
            token.value = value
            self._on_rule_changed()

    elif token.type == TokenType.VERSION:
        items = ["No prefix", "v (lowercase)", "V (uppercase)"]
        current = items[0]
        if token.prefix == "v":
            current = items[1]
        elif token.prefix == "V":
            current = items[2]

        item, ok = QInputDialog.getItem(
            self, "Version Prefix",
            "Select version prefix:",
            items, items.index(current), False
        )
        if ok:
            if item == items[1]:
                token.prefix = "v"
            elif item == items[2]:
                token.prefix = "V"
            else:
                token.prefix = ""
            self._on_rule_changed()


def _toggle_regex(self) -> None:
    """Toggle regex display visibility"""
    is_visible = self.regex_label.isVisible()
    self.regex_label.setVisible(not is_visible)
    self.regex_toggle.setText("▲ Generated Regex" if not is_visible else "▼ Generated Regex")


def _copy_regex(self) -> None:
    """Copy regex to clipboard"""
    from PySide6.QtWidgets import QApplication
    pattern = TokenEngine.compile(self.drop_zone.get_tokens())
    QApplication.clipboard().setText(pattern)


def _on_samples_changed(self) -> None:
    """Update samples list and enable Magic Wand"""
    text = self.sample_edit.toPlainText()
    self._samples = [line.strip() for line in text.splitlines() if line.strip()]
    self.btn_magic.setEnabled(len(self._samples) > 0)
    self._on_rule_changed()


def _on_rule_changed(self) -> None:
    """Update regex display and simulation results"""
    tokens = self.drop_zone.get_tokens()
    pattern = TokenEngine.compile(tokens)

    self.regex_label.setText(f"{pattern}")
    self.sim_table.refresh(self._samples, tokens)

    # Update match stats
    if self._samples:
        import re
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            matched = sum(1 for s in self._samples if regex.match(s))
            total = len(self._samples)
            pct = int(matched / total * 100) if total > 0 else 0

            color = "#4ec9b0" if pct >= 80 else "#f39c12" if pct >= 50 else "#f44747"
            self.match_stats.setText(f"{matched}/{total} matched ({pct}%)")
            self.match_stats.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: bold;")
        except:
            self.match_stats.setText("Invalid pattern")
            self.match_stats.setStyleSheet("color: #f44747; font-size: 10px; font-weight: bold;")
    else:
        self.match_stats.setText("0/0 matched (0%)")
