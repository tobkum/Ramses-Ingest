# -*- coding: utf-8 -*-
"""Smart Pattern Builder Dialog — Intelligent regex generation from annotations.

This dialog provides a user-friendly interface for generating naming rules
by annotating example filenames instead of building regex patterns manually.
"""

from __future__ import annotations

import re
import os
import time
from typing import Optional, Dict

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QSplitter,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
)

from ramses_ingest.gui import STYLESHEET
from ramses_ingest.pattern_inference import (
    PatternInferenceEngine,
    Annotation,
    PatternCandidate,
)

# Define colors for different annotation fields for visual feedback
ANNOTATION_COLORS = {
    "shot": QColor("#3a86ff"),
    "sequence": QColor("#ff006e"),
    "resource": QColor("#fb5607"),
    "version": QColor("#8338ec"),
    "date": QColor("#3a5a40"),
    "_ignore": QColor("#6c757d"),
    "default": QColor("#588157"),
}


class AnnotatableTextEdit(QTextEdit):
    """Text edit that allows user to select text and annotate it."""

    selection_changed = Signal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumHeight(60)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 2px solid #333;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', monospace;
                font-size: 13px;
                color: #e0e0e0;
            }
        """)

    def mouseReleaseEvent(self, event):
        """Emit annotation request when user selects text."""
        super().mouseReleaseEvent(event)
        cursor = self.textCursor()
        if cursor.hasSelection():
            selected_text = cursor.selectedText()
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            self.selection_changed.emit(selected_text, start, end)

    def highlight_annotations(self, annotations: Dict[str, list[Annotation]]):
        """Apply colored highlights for all current annotations."""
        cursor = self.textCursor()
        # Clear existing highlights
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.setCharFormat(QTextCharFormat())

        current_example_text = self.toPlainText()

        for field_name, ann_list in annotations.items():
            for annotation in ann_list:
                # Only highlight if it belongs to the currently displayed example
                if annotation.example != current_example_text:
                    continue

                color_key = "default"
                if field_name.startswith("_ignore"):
                    color_key = "_ignore"
                elif field_name in ANNOTATION_COLORS:
                    color_key = field_name
                
                color = ANNOTATION_COLORS[color_key]
                
                format = QTextCharFormat()
                format.setBackground(QBrush(color.lighter(120)))
                format.setForeground(QBrush(Qt.GlobalColor.white))
                format.setFontWeight(QFont.Weight.Bold)

                cursor.setPosition(annotation.start_pos)
                cursor.setPosition(annotation.end_pos, QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(format)
        
        self.setTextCursor(cursor)


class AnnotationsTable(QTableWidget):
    """Table to display and manage current annotations."""

    annotation_removed = Signal(str)  # field_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels(["Field", "Examples", ""])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(2, 40)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setMaximumHeight(150)
        self.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #2a2d2e;
                color: #ccc;
                padding: 4px;
                border: 1px solid #444;
            }
        """)

    def update_annotations(self, annotations: Dict[str, list[Annotation]]):
        """Refresh table with current annotations."""
        self.setRowCount(0)
        # Use first annotation's pos for sorting rows
        sorted_keys = sorted(annotations.keys(), key=lambda k: annotations[k][0].start_pos)
        for field_name in sorted_keys:
            ann_list = annotations[field_name]
            count = len(ann_list)
            # Display unique selections
            unique_selections = ", ".join(sorted(list(set(a.selected_text for a in ann_list))))
            display_val = f"({count}) {unique_selections}"
            self.add_annotation_row(field_name, display_val)

    def add_annotation_row(self, field_name: str, value: str):
        """Add a single row to the table."""
        row_position = self.rowCount()
        self.insertRow(row_position)

        display_name = "IGNORE" if field_name.startswith("_ignore") else field_name.upper()
        field_item = QTableWidgetItem(display_name)
        
        color_key = "default"
        if field_name.startswith("_ignore"):
            color_key = "_ignore"
        elif field_name in ANNOTATION_COLORS:
            color_key = field_name
        color = ANNOTATION_COLORS[color_key]
        
        field_item.setBackground(color.darker(150))
        field_item.setForeground(Qt.GlobalColor.white)
        self.setItem(row_position, 0, field_item)

        value_item = QTableWidgetItem(value)
        self.setItem(row_position, 1, value_item)

        remove_btn = QPushButton("❌")
        remove_btn.setToolTip("Remove this annotation")
        remove_btn.setFlat(True)
        remove_btn.clicked.connect(lambda: self.remove_annotation(field_name))
        self.setCellWidget(row_position, 2, remove_btn)

    def remove_annotation(self, field_name: str):
        """Emit signal to remove an annotation."""
        self.annotation_removed.emit(field_name)


class ResultsPreviewTable(QTableWidget):
    """Table to show live preview of pattern extraction."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QTableWidget {
                background-color: #252526;
                border: 1px solid #444;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
             QHeaderView::section {
                background-color: #2a2d2e;
                color: #ccc;
                padding: 4px;
                border: 1px solid #444;
            }
        """)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def update_preview(self, pattern: str, fields: list[str], examples: list[str]):
        """Re-run the regex and update the table with results."""
        self.setRowCount(0)
        
        display_fields = [f for f in fields if not f.startswith('_ignore')]
        self.setColumnCount(len(display_fields) + 1)
        self.setHorizontalHeaderLabels(["Source Example"] + [f.upper() for f in display_fields])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        if not pattern:
            return
            
        try:
            compiled_regex = re.compile(pattern)
        except re.error:
            self.setRowCount(0)
            return

        for example in examples:
            row_pos = self.rowCount()
            self.insertRow(row_pos)
            self.setItem(row_pos, 0, QTableWidgetItem(example))

            match = compiled_regex.search(example)
            for col_idx, field in enumerate(display_fields, 1):
                value = ""
                item = QTableWidgetItem()
                if match and field in match.groupdict() and match.group(field) is not None:
                    value = match.group(field)
                    item.setForeground(QColor("#4ec9b0")) # Success color
                else:
                    item.setForeground(QColor("#888")) # Fail/empty color
                item.setText(value)
                self.setItem(row_pos, col_idx, item)


class SmartPatternDialog(QDialog):
    """Smart Pattern Builder - Generate naming rules from annotated examples."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Smart Pattern Builder")
        self.resize(1400, 800)
        self.setStyleSheet(STYLESHEET)

        self._engine = PatternInferenceEngine()
        self._samples: list[str] = []
        self._negative_samples: list[str] = []
        self._current_example: Optional[str] = None
        self._current_annotations: Dict[str, Annotation] = {}
        self._current_selection: Optional[tuple] = None
        self._selected_pattern: Optional[str] = None

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        header = QLabel("Smart Pattern Builder")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #00bff3;")
        main_layout.addWidget(header)

        desc = QLabel(
            "Annotate positive examples to build a pattern. Use negative examples to refine it."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; margin-bottom: 8px;")
        main_layout.addWidget(desc)

        # Main content area
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ───────────────────────────────────────────────────────────────────────
        # LEFT: Examples & Annotation Controls
        # ───────────────────────────────────────────────────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)
        
        # --- Positive Samples ---
        samples_label = QLabel("POSITIVE EXAMPLES (filenames that SHOULD match)")
        samples_label.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
        left_layout.addWidget(samples_label)

        self.sample_edit = QTextEdit()
        self.sample_edit.setPlaceholderText("e.g.,\nISIH_A1_030_v01.mov\nISIH_B4_090_v02.mov")
        self.sample_edit.textChanged.connect(self._on_samples_changed)
        left_layout.addWidget(self.sample_edit)

        # --- Negative Samples ---
        neg_samples_label = QLabel("NEGATIVE EXAMPLES (filenames that should NOT match)")
        neg_samples_label.setStyleSheet("color: #888; font-size: 10px; font-weight: bold; margin-top: 10px;")
        left_layout.addWidget(neg_samples_label)
        
        self.negative_sample_edit = QTextEdit()
        self.negative_sample_edit.setPlaceholderText("e.g.,\nproject_notes.txt\n.DS_Store")
        self.negative_sample_edit.textChanged.connect(self._on_negative_samples_changed)
        self.negative_sample_edit.setMaximumHeight(100)
        left_layout.addWidget(self.negative_sample_edit)

        # --- Annotation Controls ---
        select_label = QLabel("ANNOTATE AN EXAMPLE")
        select_label.setStyleSheet("color: #888; font-size: 10px; font-weight: bold; margin-top: 10px;")
        left_layout.addWidget(select_label)

        self.example_list = QListWidget()
        self.example_list.itemClicked.connect(self._on_example_selected)
        self.example_list.setMaximumHeight(120)
        left_layout.addWidget(self.example_list)

        self.annotate_edit = AnnotatableTextEdit()
        self.annotate_edit.selection_changed.connect(self._on_text_selected)
        left_layout.addWidget(self.annotate_edit)

        btn_group_frame = QGroupBox("This selection represents:")
        btn_layout = QHBoxLayout(btn_group_frame)
        self.btn_shot = self._create_annotation_button("📷 Shot", "shot", btn_layout)
        self.btn_sequence = self._create_annotation_button("🎬 Sequence", "sequence", btn_layout)
        self.btn_resource = self._create_annotation_button("📦 Resource", "resource", btn_layout)
        self.btn_version = self._create_annotation_button("🏷️ Version", "version", btn_layout)
        btn_layout.addStretch()
        self.btn_ignore = self._create_annotation_button("🚫 Ignore", "_ignore", btn_layout)
        self.btn_ignore.setStyleSheet("background-color: #4a4a4a;")

        self._toggle_annotation_buttons(False)
        left_layout.addWidget(btn_group_frame)
        main_splitter.addWidget(left_panel)

        # ───────────────────────────────────────────────────────────────────────
        # RIGHT: Current Annotations & Live Preview
        # ───────────────────────────────────────────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)

        table_label = QLabel("CURRENT ANNOTATIONS")
        table_label.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
        right_layout.addWidget(table_label)
        self.annotations_table = AnnotationsTable()
        self.annotations_table.annotation_removed.connect(self._remove_annotation)
        right_layout.addWidget(self.annotations_table)

        cand_label = QLabel("LIVE PREVIEW & RESULTS")
        cand_label.setStyleSheet("color: #888; font-size: 10px; font-weight: bold; margin-top: 10px;")
        right_layout.addWidget(cand_label)

        self.pattern_label = QLabel("Pattern: (no pattern generated yet)")
        self.pattern_label.setStyleSheet("font-family: 'Consolas', monospace; color: #4ec9b0; font-size: 11px;")
        self.pattern_label.setWordWrap(True)
        right_layout.addWidget(self.pattern_label)

        self.results_table = ResultsPreviewTable()
        right_layout.addWidget(self.results_table)
        
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([600, 800])
        main_layout.addWidget(main_splitter)

        # Footer
        footer = self._create_footer()
        main_layout.addLayout(footer)

    def _create_annotation_button(self, text, field_name, layout):
        button = QPushButton(text)
        button.clicked.connect(lambda: self._add_annotation(field_name))
        layout.addWidget(button)
        return button

    def _create_footer(self):
        footer = QHBoxLayout()
        btn_reset = QPushButton("Reset")
        btn_reset.setToolTip("Clear all samples and annotations")
        btn_reset.clicked.connect(self._on_reset)
        footer.addWidget(btn_reset)
        footer.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)
        self.btn_apply = QPushButton("Apply Pattern")
        self.btn_apply.setEnabled(False)
        self.btn_apply.setStyleSheet("background-color: #094771; color: white; font-weight: bold;")
        self.btn_apply.clicked.connect(self.accept)
        footer.addWidget(self.btn_apply)
        return footer

    def _on_samples_changed(self):
        text = self.sample_edit.toPlainText()
        # Strip paths from samples so we only deal with filenames
        self._samples = [os.path.basename(line.strip()) for line in text.splitlines() if line.strip()]
        
        # Update the text edit if it contains full paths to keep it clean
        stripped_text = "\n".join(self._samples)
        if text.strip() != stripped_text:
            self.sample_edit.blockSignals(True)
            self.sample_edit.setPlainText(stripped_text)
            self.sample_edit.blockSignals(False)

        self.example_list.clear()
        self.example_list.addItems(self._samples)
        
        if self._samples and self.example_list.currentRow() == -1:
            self.example_list.setCurrentRow(0)
            self._on_example_selected(self.example_list.item(0))
        self._update_pattern_and_preview()

    def _on_negative_samples_changed(self):
        text = self.negative_sample_edit.toPlainText()
        # Strip paths from negative samples
        self._negative_samples = [os.path.basename(line.strip()) for line in text.splitlines() if line.strip()]
        
        # Update the text edit if it contains full paths
        stripped_text = "\n".join(self._negative_samples)
        if text.strip() != stripped_text:
            self.negative_sample_edit.blockSignals(True)
            self.negative_sample_edit.setPlainText(stripped_text)
            self.negative_sample_edit.blockSignals(False)

        self._update_pattern_and_preview()

    def _on_example_selected(self, item: QListWidgetItem):
        if not item or item.text() == self._current_example: return
        self._current_example = item.text()
        # NOTE: We NO LONGER reset _current_annotations here.
        # This allows training the engine across multiple examples.
        
        self._current_selection = None
        self._selected_pattern = None

        self.annotate_edit.setPlainText(self._current_example)
        self.annotate_edit.highlight_annotations(self._current_annotations)
        self.annotations_table.update_annotations(self._current_annotations)
        self._toggle_annotation_buttons(False)
        self._update_pattern_and_preview()

    def _on_text_selected(self, selected_text: str, start_pos: int, end_pos: int):
        if self._current_example:
            self._current_selection = (selected_text, start_pos, end_pos)
            self._toggle_annotation_buttons(True)

    def _toggle_annotation_buttons(self, enabled: bool):
        self.btn_shot.setEnabled(enabled)
        self.btn_sequence.setEnabled(enabled)
        self.btn_resource.setEnabled(enabled)
        self.btn_version.setEnabled(enabled)
        self.btn_ignore.setEnabled(enabled)

    def _add_annotation(self, field_name: str):
        if not self._current_example or not self._current_selection:
            return

        selected_text, start_pos, end_pos = self._current_selection

        # Check for overlaps within the SAME example
        for ann_list in self._current_annotations.values():
            for ann in ann_list:
                if ann.example == self._current_example:
                    if max(ann.start_pos, start_pos) < min(ann.end_pos, end_pos):
                        print(f"Warning: Annotation for '{selected_text}' overlaps with existing annotation in this example.")
                        return

        field_key = f"_ignore_{int(time.time() * 1000)}" if field_name == "_ignore" else field_name
            
        annotation = Annotation(
            example=self._current_example,
            selected_text=selected_text,
            field_name=field_key,
            start_pos=start_pos,
            end_pos=end_pos,
        )
        
        if field_key not in self._current_annotations:
            self._current_annotations[field_key] = []
        
        # Prevent duplicate annotations for the same text in the same example
        is_duplicate = any(
            a.example == annotation.example and 
            a.start_pos == annotation.start_pos and 
            a.end_pos == annotation.end_pos 
            for a in self._current_annotations[field_key]
        )
        
        if not is_duplicate:
            self._current_annotations[field_key].append(annotation)
        
        self.annotations_table.update_annotations(self._current_annotations)
        self.annotate_edit.highlight_annotations(self._current_annotations)
        self._toggle_annotation_buttons(False)
        self._current_selection = None
        
        self._update_pattern_and_preview()

    def _remove_annotation(self, field_name: str):
        if field_name in self._current_annotations:
            # If multiple examples exist, maybe we should remove only for current example?
            # For simplicity, if they click X in table, remove ALL for that field.
            del self._current_annotations[field_name]
            self.annotations_table.update_annotations(self._current_annotations)
            self.annotate_edit.highlight_annotations(self._current_annotations)
            self._update_pattern_and_preview()

    def _update_pattern_and_preview(self):
        if not self._current_annotations:
            self._selected_pattern = None
            self.pattern_label.setText("Pattern: (add annotations to generate)")
            self.results_table.update_preview("", [], self._samples)
            self.btn_apply.setEnabled(False)
            return

        try:
            candidates = self._engine.infer_combined_pattern(
                self._current_annotations,
                test_examples=self._samples,
                negative_examples=self._negative_samples
            )
        except ValueError as e:
            print(f"Error inferring pattern: {e}")
            self._selected_pattern = None
            candidates = []

        if candidates:
            best_candidate = candidates[0]
            self._selected_pattern = best_candidate.pattern
            self.pattern_label.setText(f"Pattern: {self._selected_pattern}")
            
            sorted_fields = sorted(list(self._current_annotations.keys()))
            
            self.results_table.update_preview(
                self._selected_pattern,
                sorted_fields,
                self._samples
            )
            self.btn_apply.setEnabled(True)
        else:
            self._selected_pattern = None
            self.pattern_label.setText("Pattern: (could not generate a valid pattern)")
            self.results_table.update_preview("", [], self._samples)
            self.btn_apply.setEnabled(False)

    def get_final_regex(self) -> str:
        return self._selected_pattern or ""

    def _on_reset(self):
        self.sample_edit.clear()
        self.negative_sample_edit.clear()
        self.annotate_edit.clear()
        self.annotations_table.setRowCount(0)
        self.results_table.setRowCount(0)
        
        self._samples = []
        self._negative_samples = []
        self._current_example = None
        self._current_annotations = {}
        self._current_selection = None
        self._selected_pattern = None
        
        self.pattern_label.setText("Pattern: (no pattern generated yet)")
        self.btn_apply.setEnabled(False)
        self._toggle_annotation_buttons(False)
