# Professional UI Supporting Methods
# Add these methods to the IngestWindow class

def _setup_shortcuts(self) -> None:
    """Setup keyboard shortcuts for professional workflow"""
    from PySide6.QtGui import QShortcut, QKeySequence

    # Ctrl+F = Focus search
    QShortcut(QKeySequence("Ctrl+F"), self, lambda: self._search_edit.setFocus())

    # Enter = Execute (if enabled)
    QShortcut(QKeySequence(Qt.Key.Key_Return), self, self._on_shortcut_execute)

    # Escape = Clear selection
    QShortcut(QKeySequence(Qt.Key.Key_Escape), self, lambda: self._table.clearSelection())

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


def _apply_table_filters(self) -> None:
    """Apply all active filters to table rows"""
    for row in range(self._table.rowCount()):
        show = True

        # Status filter
        if self._current_filter_status != "all":
            # Check status column
            status_item = self._table.cellWidget(row, 6)  # Status column
            if status_item and hasattr(status_item, 'toolTip'):
                status = status_item.toolTip().lower()
                if self._current_filter_status not in status:
                    show = False

        # Type filter
        if show:
            # Check if it's a sequence or movie
            frames_item = self._table.item(row, 4)  # Frames column
            if frames_item:
                frames_text = frames_item.text()
                is_sequence = "f" in frames_text and int(frames_text.replace("f", "")) > 1

                if is_sequence and not self._chk_sequences.isChecked():
                    show = False
                elif not is_sequence and not self._chk_movies.isChecked():
                    show = False

        # Search filter
        if show and self._search_edit.text():
            search = self._search_edit.text().lower()
            shot_item = self._table.item(row, 2)  # Shot column
            seq_item = self._table.item(row, 3)   # Seq column
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
    details.append(f"<b>Clip:</b> {plan.match.clip.base_name}.{plan.match.clip.extension}")
    details.append(f"<b>Shot:</b> {plan.shot_id or '—'}")
    details.append(f"<b>Sequence:</b> {plan.sequence_id or '—'}")
    details.append(f"<b>Frames:</b> {plan.match.clip.frame_count if plan.match.clip.is_sequence else 1}")

    if plan.media_info.width and plan.media_info.height:
        details.append(f"<b>Resolution:</b> {plan.media_info.width}x{plan.media_info.height}")
    if plan.media_info.fps:
        details.append(f"<b>FPS:</b> {plan.media_info.fps:.2f}")
    if plan.media_info.codec:
        details.append(f"<b>Codec:</b> {plan.media_info.codec}")
    if plan.media_info.color_space:
        details.append(f"<b>Colorspace:</b> {plan.media_info.color_space}")

    if plan.error:
        details.append(f"<br><b style='color:#f44747'>Error:</b> {plan.error}")

    if plan.match.clip.missing_frames:
        details.append(f"<br><b style='color:#f39c12'>Missing Frames:</b> {len(plan.match.clip.missing_frames)}")

    self._detail_widget.setHtml("<br>".join(details))

    # Enable override
    self._override_shot.setEnabled(True)
    if plan.shot_id:
        self._override_shot.setText(plan.shot_id)


def _on_override_changed(self, text: str) -> None:
    """Apply shot ID override to selected plan"""
    if self._selected_plan_idx >= 0 and self._selected_plan_idx < len(self._plans):
        plan = self._plans[self._selected_plan_idx]
        plan.shot_id = text
        # Update table
        self._table.item(self._selected_plan_idx, 2).setText(text)
        self._update_summary()


def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
    """Handle inline edits in table"""
    if item.column() == 2:  # Shot column
        row = item.row()
        if row < len(self._plans):
            self._plans[row].shot_id = item.text()
            self._update_summary()


def _on_remove_selected(self) -> None:
    """Remove selected clips from table"""
    selected_rows = sorted(set(item.row() for item in self._table.selectedItems()), reverse=True)
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
    self._chk_thumb = QCheckBox("Generate thumbnails")
    self._chk_thumb.setChecked(True)
    lay.addWidget(self._chk_thumb)

    # Proxies
    self._chk_proxy = QCheckBox("Generate video proxies")
    self._chk_proxy.setChecked(False)
    lay.addWidget(self._chk_proxy)

    # Status update
    self._chk_status = QCheckBox("Set step status to OK on success")
    self._chk_status.setChecked(True)
    lay.addWidget(self._chk_status)

    lay.addSpacing(10)

    # OCIO
    ocio_group = QGroupBox("Color Management (OCIO)")
    ocio_lay = QVBoxLayout(ocio_group)

    ocio_lay.addWidget(QLabel("Source Colorspace:"))
    self._ocio_in = QComboBox()
    self._ocio_in.addItems(["sRGB", "Linear", "Rec.709", "LogC", "S-Log3", "V-Log"])
    self._ocio_in.currentTextChanged.connect(self._on_ocio_in_changed)
    ocio_lay.addWidget(self._ocio_in)

    lay.addWidget(ocio_group)

    lay.addSpacing(10)

    # Naming rules
    rule_group = QGroupBox("Naming Rules")
    rule_lay = QVBoxLayout(rule_group)

    self._rule_combo = QComboBox()
    self._rule_combo.addItem("Auto-detect")
    self._populate_rule_combo()
    rule_lay.addWidget(self._rule_combo)

    rule_btns = QHBoxLayout()
    btn_architect = QPushButton("Architect...")
    btn_architect.clicked.connect(self._on_launch_architect)
    rule_btns.addWidget(btn_architect)

    self._btn_edl = QPushButton("Load EDL...")
    self._btn_edl.clicked.connect(self._on_load_edl)
    rule_btns.addWidget(self._btn_edl)

    btn_edit = QPushButton("Edit Rules...")
    btn_edit.clicked.connect(self._on_edit_rules)
    rule_btns.addWidget(btn_edit)

    rule_lay.addLayout(rule_btns)

    lay.addWidget(rule_group)

    lay.addStretch()

    # Buttons
    btn_row = QHBoxLayout()
    btn_close = QPushButton("Close")
    btn_close.clicked.connect(dialog.accept)
    btn_row.addStretch()
    btn_row.addWidget(btn_close)
    lay.addLayout(btn_row)

    dialog.exec()


def _update_filter_counts(self) -> None:
    """Update the count badges on filter buttons"""
    if not hasattr(self, '_plans'):
        return

    total = len(self._plans)
    ready = sum(1 for p in self._plans if p.can_execute and not p.error)
    warning = sum(1 for p in self._plans if p.can_execute and p.error and "warning" in p.error.lower())
    error = sum(1 for p in self._plans if not p.can_execute or (p.error and "error" in p.error.lower()))

    self._filter_all.setText(f"● All ({total})")
    self._filter_ready.setText(f"● Ready ({ready})")
    self._filter_warning.setText(f"● Warnings ({warning})")
    self._filter_error.setText(f"● Errors ({error})")
