# Professional UI Population Method
# Replace _populate_tree with this _populate_table method

def _populate_table(self) -> None:
    """Populate the table with current plans (replaces _populate_tree)"""
    self._table.setRowCount(0)
    self._table.setRowCount(len(self._plans))

    for idx, plan in enumerate(self._plans):
        clip = plan.match.clip

        # Column 0: Checkbox
        chk = QCheckBox()
        chk.setChecked(plan.can_execute)
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

        # Column 3: Sequence
        seq_item = QTableWidgetItem(plan.sequence_id or "—")
        seq_item.setFlags(seq_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(idx, 3, seq_item)

        # Column 4: Frames
        frames_text = f"{clip.frame_count}f" if clip.is_sequence else "1f"
        frames_item = QTableWidgetItem(frames_text)
        frames_item.setFlags(frames_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(idx, 4, frames_item)

        # Column 5: Resolution
        res_text = "—"
        if plan.media_info.width and plan.media_info.height:
            res_text = f"{plan.media_info.width}x{plan.media_info.height}"
        res_item = QTableWidgetItem(res_text)
        res_item.setFlags(res_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(idx, 5, res_item)

        # Column 6: Status (color dot)
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
        self._table.setCellWidget(idx, 6, status_indicator)

        # Set row height for better readability
        self._table.setRowHeight(idx, 28)

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
                self._plans[row].can_execute = (state == Qt.CheckState.Checked.value)
            break

    self._update_summary()


def _on_search_changed(self, text: str) -> None:
    """Filter table rows by search text"""
    self._apply_table_filters()


def _on_context_menu(self, pos) -> None:
    """Show context menu for selected clips"""
    menu = QMenu(self)

    # Get selected rows
    selected_rows = list(set(item.row() for item in self._table.selectedItems()))
    if not selected_rows:
        return

    # Actions
    act_override = QAction("Override Shot ID...", self)
    act_override.triggered.connect(self._on_context_override_shot)
    menu.addAction(act_override)

    act_skip = QAction("Skip Selected", self)
    act_skip.triggered.connect(self._on_context_skip)
    menu.addAction(act_skip)

    menu.addSeparator()

    act_remove = QAction("Remove from List", self)
    act_remove.triggered.connect(self._on_remove_selected)
    menu.addAction(act_remove)

    menu.exec(self._table.viewport().mapToGlobal(pos))


def _on_context_override_shot(self) -> None:
    """Override shot ID for selected clips"""
    from PySide6.QtWidgets import QInputDialog

    selected_rows = list(set(item.row() for item in self._table.selectedItems()))
    if not selected_rows:
        return

    shot_id, ok = QInputDialog.getText(
        self, "Override Shot ID",
        f"Enter shot ID for {len(selected_rows)} clip(s):"
    )

    if ok and shot_id:
        for row in selected_rows:
            if row < len(self._plans):
                self._plans[row].shot_id = shot_id
                self._table.item(row, 2).setText(shot_id)

        self._update_summary()


def _on_context_skip(self) -> None:
    """Skip selected clips (uncheck them)"""
    selected_rows = list(set(item.row() for item in self._table.selectedItems()))
    for row in selected_rows:
        if row < len(self._plans):
            self._plans[row].can_execute = False
            chk_widget = self._table.cellWidget(row, 0)
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk:
                    chk.setChecked(False)

    self._update_summary()


def _update_summary(self) -> None:
    """Update summary label and execute button"""
    if not self._plans:
        self._summary_label.setText("No delivery loaded.")
        self._btn_ingest.setEnabled(False)
        self._btn_ingest.setText("Execute")
        return

    total = len(self._plans)
    executable = sum(1 for p in self._plans if p.can_execute)
    matched = sum(1 for p in self._plans if p.match.matched)

    self._summary_label.setText(
        f"{total} clips loaded, {matched} matched, {executable} ready to ingest"
    )

    if executable > 0:
        self._btn_ingest.setEnabled(True)
        self._btn_ingest.setText(f"Execute ({executable})")
    else:
        self._btn_ingest.setEnabled(False)
        self._btn_ingest.setText("Execute")


# Also need to update the load methods to call _populate_table instead of _populate_tree
# Find and replace all instances of:
#   self._populate_tree()  →  self._populate_table()
