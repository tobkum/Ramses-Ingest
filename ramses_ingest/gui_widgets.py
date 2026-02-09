# -*- coding: utf-8 -*-
"""Reusable GUI components for Ramses Ingest."""

from __future__ import annotations

import os
import logging
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QProgressBar, QPushButton, QStyledItemDelegate, QLineEdit,
    QDialog, QTextEdit, QMessageBox, QSizePolicy
)

from ramses_ingest.config import load_rules, save_rules

# ---------------------------------------------------------------------------
# Logging Handler
# ---------------------------------------------------------------------------

class GuiLogHandler(logging.Handler):
    """Custom logging handler that redirects logs to a callback method."""

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
# Status Indicator
# ---------------------------------------------------------------------------

class StatusIndicator(QLabel):
    """Color-coded status dot (● instead of text)"""

    def __init__(self, status: str = "pending", parent=None):
        super().__init__(parent)
        self.status_type = status
        self.set_status(status)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(0, 0, 0, 0)

    def set_status(self, status: str):
        """Update status color: ready=green, warning=yellow, error=red, pending=gray"""
        self.status_type = status
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


# ---------------------------------------------------------------------------
# Table Delegate
# ---------------------------------------------------------------------------

class EditableDelegate(QStyledItemDelegate):
    """Delegate for inline editing of table cells"""

    def createEditor(self, parent, option, index):
        """Create editor for shot ID override"""
        if index.column() == 3:  # Shot column
            editor = QLineEdit(parent)
            editor.setStyleSheet("background: #2d2d30; border: 1px solid #094771;")
            return editor
        return super().createEditor(parent, option, index)


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
        # Set font specifically for code editing
        font = self._editor.font()
        font.setFamily("Consolas")
        font.setStyleHint(font.StyleHint.Monospace)
        self._editor.setFont(font)
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
