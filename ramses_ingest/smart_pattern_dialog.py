# -*- coding: utf-8 -*-
"""Smart Pattern Builder Dialog — Intelligent regex generation from annotations.

This dialog provides a user-friendly interface for generating naming rules
by annotating example filenames instead of building regex patterns manually.
"""

from __future__ import annotations

import re
import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QDialog,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QSplitter,
    QButtonGroup,
    QRadioButton,
    QGroupBox,
)

from ramses_ingest.gui import STYLESHEET
from ramses_ingest.pattern_inference import (
    PatternInferenceEngine,
    Annotation,
    PatternCandidate,
    test_pattern,
)


class AnnotatableTextEdit(QTextEdit):
    """Text edit that allows user to select text and annotate it."""

    annotation_requested = Signal(str, int, int)  # selected_text, start_pos, end_pos

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumHeight(60)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 2px solid #00bff3;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                color: #ffffff;
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
            self.annotation_requested.emit(selected_text, start, end)


class PatternCandidateWidget(QFrame):
    """Widget showing a single pattern candidate with live preview."""

    selected = Signal(PatternCandidate)

    def __init__(
        self,
        candidate: PatternCandidate,
        examples: list[str],
        field_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.candidate = candidate
        self.examples = examples
        self.field_name = field_name
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            PatternCandidateWidget {
                background-color: #252526;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
            }
            PatternCandidateWidget:hover {
                background-color: #2d2d30;
                border-color: #00bff3;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Header: Confidence + Flexibility
        header = QHBoxLayout()

        conf_label = QLabel(f"Confidence: {self.candidate.confidence:.0%}")
        conf_color = (
            "#4ec9b0"
            if self.candidate.confidence >= 0.7
            else "#f39c12"
            if self.candidate.confidence >= 0.5
            else "#f44747"
        )
        conf_label.setStyleSheet(f"color: {conf_color}; font-weight: bold;")
        header.addWidget(conf_label)

        header.addStretch()

        flex_label = QLabel(self.candidate.flexibility.value.upper())
        flex_label.setStyleSheet("color: #888; font-size: 10px;")
        header.addWidget(flex_label)

        layout.addLayout(header)

        # Pattern
        pattern_label = QLabel(f"Pattern: {self.candidate.pattern}")
        pattern_label.setStyleSheet(
            "font-family: 'Consolas', monospace; color: #4ec9b0; font-size: 10px;"
        )
        pattern_label.setWordWrap(True)
        layout.addWidget(pattern_label)

        # Description
        desc_label = QLabel(self.candidate.description)
        desc_label.setStyleSheet("color: #ccc; font-size: 10px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Preview of extractions (first 3 examples)
        preview_label = QLabel("Preview:")
        preview_label.setStyleSheet("color: #888; font-size: 9px; margin-top: 4px;")
        layout.addWidget(preview_label)

        import os

        extractions = test_pattern(
            self.candidate.pattern, self.examples[:3], self.field_name
        )
        for example, value in zip(self.examples[:3], extractions):
            # Show only filename, not full path
            filename = os.path.basename(example)
            display_name = filename[:40] + "..." if len(filename) > 40 else filename

            val_str = f"'{value}'" if value else "None"
            val_color = "#4ec9b0" if value else "#888"
            ex_label = QLabel(f"  {display_name} → {val_str}")
            ex_label.setStyleSheet(
                f"color: {val_color}; font-family: 'Consolas', monospace; font-size: 9px;"
            )
            layout.addWidget(ex_label)

    def mousePressEvent(self, event):
        """Emit selected signal when clicked."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.candidate)
            # Visual feedback
            self.setStyleSheet("""
                PatternCandidateWidget {
                    background-color: #094771;
                    border: 2px solid #00bff3;
                    border-radius: 4px;
                    padding: 8px;
                }
            """)


class SmartPatternDialog(QDialog):
    """Smart Pattern Builder - Generate naming rules from annotated examples."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Smart Pattern Builder")
        self.resize(1200, 700)
        self.setStyleSheet(STYLESHEET)

        self._engine = PatternInferenceEngine()
        self._samples = []
        self._annotations = []
        self._selected_pattern: Optional[str] = None

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # ═══════════════════════════════════════════════════════════════════════
        # HEADER
        # ═══════════════════════════════════════════════════════════════════════
        header = QLabel("Smart Pattern Builder")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #00bff3;")
        main_layout.addWidget(header)

        desc = QLabel(
            "Annotate example filenames to automatically generate naming rules. "
            "Select text in an example, then click what it represents (Shot, Sequence, etc.)."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; margin-bottom: 8px;")
        main_layout.addWidget(desc)

        # ═══════════════════════════════════════════════════════════════════════
        # MAIN AREA - Splitter
        # ═══════════════════════════════════════════════════════════════════════
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ───────────────────────────────────────────────────────────────────────
        # LEFT: Examples + Annotation
        # ───────────────────────────────────────────────────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Sample input
        samples_label = QLabel("SAMPLE FILENAMES")
        samples_label.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
        left_layout.addWidget(samples_label)

        self.sample_edit = QTextEdit()
        self.sample_edit.setPlaceholderText(
            "Paste example filenames (one per line):\n\n"
            "A077C013_230614_RO9S.mov\n"
            "A081C011_230615_RO9S_1.mov\n"
            "ISIH_A1_030.mov"
        )
        self.sample_edit.setMaximumHeight(150)
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
        left_layout.addWidget(self.sample_edit)

        # Example selection
        select_label = QLabel("SELECT EXAMPLE TO ANNOTATE")
        select_label.setStyleSheet(
            "color: #888; font-size: 10px; font-weight: bold; margin-top: 12px;"
        )
        left_layout.addWidget(select_label)

        self.example_list = QListWidget()
        self.example_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QListWidget::item:selected {
                background-color: #094771;
            }
        """)
        self.example_list.itemClicked.connect(self._on_example_selected)
        left_layout.addWidget(self.example_list)

        # Annotation area
        annot_label = QLabel("ANNOTATE SELECTED TEXT")
        annot_label.setStyleSheet(
            "color: #888; font-size: 10px; font-weight: bold; margin-top: 12px;"
        )
        left_layout.addWidget(annot_label)

        self.annotate_edit = AnnotatableTextEdit()
        self.annotate_edit.annotation_requested.connect(self._on_text_selected)
        left_layout.addWidget(self.annotate_edit)

        # Annotation buttons
        btn_group_frame = QGroupBox("This represents:")
        btn_group_frame.setStyleSheet("QGroupBox { color: #888; font-size: 10px; }")
        btn_layout = QHBoxLayout(btn_group_frame)

        self.btn_shot = QPushButton("📷 Shot")
        self.btn_shot.clicked.connect(lambda: self._annotate_field("shot"))
        self.btn_shot.setEnabled(False)
        btn_layout.addWidget(self.btn_shot)

        self.btn_sequence = QPushButton("🎬 Sequence")
        self.btn_sequence.clicked.connect(lambda: self._annotate_field("sequence"))
        self.btn_sequence.setEnabled(False)
        btn_layout.addWidget(self.btn_sequence)

        self.btn_resource = QPushButton("📦 Resource")
        self.btn_resource.clicked.connect(lambda: self._annotate_field("resource"))
        self.btn_resource.setEnabled(False)
        btn_layout.addWidget(self.btn_resource)

        left_layout.addWidget(btn_group_frame)

        splitter.addWidget(left_panel)

        # ───────────────────────────────────────────────────────────────────────
        # RIGHT: Pattern Candidates
        # ───────────────────────────────────────────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        cand_label = QLabel("PATTERN CANDIDATES")
        cand_label.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
        right_layout.addWidget(cand_label)

        self.candidate_scroll = QWidget()
        self.candidate_layout = QVBoxLayout(self.candidate_scroll)
        self.candidate_layout.setSpacing(8)
        self.candidate_layout.addStretch()

        from PySide6.QtWidgets import QScrollArea

        scroll = QScrollArea()
        scroll.setWidget(self.candidate_scroll)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        right_layout.addWidget(scroll)

        splitter.addWidget(right_panel)
        splitter.setSizes([400, 800])

        main_layout.addWidget(splitter, 1)

        # ═══════════════════════════════════════════════════════════════════════
        # FOOTER
        # ═══════════════════════════════════════════════════════════════════════
        footer = QHBoxLayout()

        btn_reset = QPushButton("Reset")
        btn_reset.setToolTip("Clear all samples and annotations")
        btn_reset.clicked.connect(self._on_reset)
        footer.addWidget(btn_reset)

        footer.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumWidth(100)
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        self.btn_apply = QPushButton("Apply Pattern")
        self.btn_apply.setMinimumWidth(140)
        self.btn_apply.setEnabled(False)
        self.btn_apply.setStyleSheet(
            "background-color: #094771; color: white; font-weight: bold;"
        )
        self.btn_apply.clicked.connect(self.accept)
        footer.addWidget(self.btn_apply)

        main_layout.addLayout(footer)

    def _on_samples_changed(self):
        """Update sample list when user pastes examples."""
        text = self.sample_edit.toPlainText()
        self._samples = [
            os.path.basename(line.strip()) for line in text.splitlines() if line.strip()
        ]

        self.example_list.clear()
        for sample in self._samples:
            item = QListWidgetItem(sample)
            self.example_list.addItem(item)

    def _on_example_selected(self, item: QListWidgetItem):
        """Load selected example into annotation editor."""
        self.annotate_edit.setPlainText(item.text())
        self._current_example = item.text()
        self._current_selection = None

    def _on_text_selected(self, selected_text: str, start_pos: int, end_pos: int):
        """Enable annotation buttons when text is selected."""
        self._current_selection = (selected_text, start_pos, end_pos)
        self.btn_shot.setEnabled(True)
        self.btn_sequence.setEnabled(True)
        self.btn_resource.setEnabled(True)

    def _annotate_field(self, field_name: str):
        """Process annotation and generate pattern candidates."""
        if not hasattr(self, "_current_example") or not hasattr(
            self, "_current_selection"
        ):
            return

        selected_text, start_pos, end_pos = self._current_selection

        # Create annotation
        annotation = Annotation(
            example=self._current_example,
            selected_text=selected_text,
            field_name=field_name,
            start_pos=start_pos,
            end_pos=end_pos,
        )

        self._annotations.append(annotation)

        # Generate pattern candidates
        candidates = self._engine.infer_pattern(
            [annotation], test_examples=self._samples
        )

        # Clear previous candidates
        for i in reversed(range(self.candidate_layout.count())):
            item = self.candidate_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()

        # Display top 5 candidates
        for candidate in candidates[:5]:
            widget = PatternCandidateWidget(candidate, self._samples, field_name)
            widget.selected.connect(self._on_candidate_selected)
            self.candidate_layout.insertWidget(
                self.candidate_layout.count() - 1, widget
            )

        # Disable annotation buttons after use
        self.btn_shot.setEnabled(False)
        self.btn_sequence.setEnabled(False)
        self.btn_resource.setEnabled(False)

    def _on_candidate_selected(self, candidate: PatternCandidate):
        """User selected a pattern candidate."""
        self._selected_pattern = candidate.pattern
        self.btn_apply.setEnabled(True)

    def get_final_regex(self) -> str:
        """Return the selected pattern."""
        return self._selected_pattern or ""

    def _on_reset(self):
        """Reset the dialog to initial state."""
        self._annotations = []
        self._selected_pattern = None
        self.btn_apply.setEnabled(False)

        # Clear candidates
        for i in reversed(range(self.candidate_layout.count())):
            item = self.candidate_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()

        self.sample_edit.clear()
        self.annotate_edit.clear()

        self.btn_shot.setEnabled(False)
        self.btn_sequence.setEnabled(False)
        self.btn_resource.setEnabled(False)
