# -*- coding: utf-8 -*-
"""Ramses Naming Architect — Visual rule-building engine.

This module converts a sequence of visual tokens into a valid NamingRule (regex).
It also provides the core simulation logic for the 'Live Lab'.
"""

from __future__ import annotations

import re
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QFont, QColor, QDrag, QAction
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
    QLineEdit,
    QScrollArea,
    QDialog,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMenu,
    QCheckBox,
    QSpinBox,
    QTextEdit,
    QApplication,
    QComboBox,
    QStackedWidget,
)
from PySide6.QtGui import QTextCharFormat, QTextCursor

from ramses_ingest.gui import STYLESHEET
from ramses_ingest.pattern_inference import (
    PatternInferenceEngine,
    Annotation,
    PatternCandidate,
    test_pattern,
)

if TYPE_CHECKING:
    from ramses_ingest.matcher import NamingRule


class TokenType(Enum):
    SEQUENCE = "sequence"
    SHOT = "shot"
    VERSION = "version"
    STEP = "step"
    PROJECT = "project"
    SEPARATOR = "separator"
    WILDCARD = "wildcard"
    IGNORE = "ignore"


@dataclass
class ArchitectToken:
    """A discrete block in the naming rule blueprint."""

    type: TokenType
    value: str = ""  # For separators or custom wildcards
    padding: int = 0  # For digits (e.g. 3 -> \d{3})
    prefix: str = ""  # e.g. "v" for version
    is_uppercase: bool = False
    is_required: bool = True

    def to_regex(self) -> str:
        """Convert this token into a Python Regex fragment."""
        if self.type == TokenType.SEPARATOR:
            return re.escape(self.value)

        # Build the capture group logic
        pattern = ""
        prefix_part = ""
        if self.type == TokenType.VERSION:
            if self.prefix:
                prefix_part = re.escape(self.prefix)
            pattern = r"\d+" if self.padding <= 0 else rf"\d{{{self.padding}}}"
        elif self.type == TokenType.SHOT or self.type == TokenType.SEQUENCE:
            # Common pattern: alphanumeric but must contain a digit
            pattern = r"[A-Za-z0-9]+"
        elif self.type == TokenType.WILDCARD:
            pattern = r".*?"
        elif self.type == TokenType.IGNORE:
            return r".*?"
        else:
            pattern = r"[A-Za-z0-9]+"

        if self.type in [
            TokenType.SEQUENCE,
            TokenType.SHOT,
            TokenType.VERSION,
            TokenType.STEP,
            TokenType.PROJECT,
        ]:
            return f"{prefix_part}(?P<{self.type.value}>{pattern})"

        return pattern


class TokenEngine:
    """Compiles a list of tokens into a functional NamingRule."""

    @staticmethod
    def compile(tokens: list[ArchitectToken]) -> str:
        """Generate a full regex pattern from tokens."""
        if not tokens:
            return ""

        parts = [t.to_regex() for t in tokens]
        # Anchor to start if requested (usually expected for filenames)
        return "^" + "".join(parts) + ".*$"

    @staticmethod
    def simulate(tokens: list[ArchitectToken], filename: str) -> dict[str, str]:
        """Simulate the rule against a filename and return matched groups."""
        pattern = TokenEngine.compile(tokens)
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            match = regex.match(filename)
            if match:
                return match.groupdict()
        except Exception:
            pass
        return {}

    @staticmethod
    def guess_tokens(samples: list[str]) -> list[ArchitectToken]:
        """Analyze samples and heuristically guess the best token blueprint."""
        if not samples:
            return []

        import os

        # 0. Clean samples: Filenames only + Strip common trailing frame numbers
        def _clean_for_guess(s: str) -> str:
            # Handle sequence frames: shot_010.0001.exr -> shot_010
            base = os.path.basename(s).rsplit(".", 1)[0]
            # Strip trailing frame numbers (e.g. shot_010.0001 -> shot_010)
            base = re.sub(r"[._]\d+$", "", base)
            return base

        filenames = [_clean_for_guess(s) for s in samples]
        if not filenames:
            return []

        first = filenames[0]

        # 1. Detect most likely separator
        seps = ["_", ".", "-"]
        sep_counts = {s: first.count(s) for s in seps}
        best_sep = (
            max(sep_counts, key=sep_counts.get) if any(sep_counts.values()) else "_"
        )

        # 2. Split samples by best separator
        parts_matrix = [s.rsplit(".", 1)[0].split(best_sep) for s in filenames]
        n_parts = len(parts_matrix[0])

        guessed_tokens = []
        assigned_types = set()

        for i in range(n_parts):
            column = [p[i] if i < len(p) else "" for p in parts_matrix]
            val = column[0]
            is_static = all(v == val for v in column)
            is_numeric = all(re.search(r"\d+", v) for v in column if v)

            ttype = TokenType.IGNORE
            padding = 0
            prefix = ""

            # Heuristics for VFX naming
            if not is_static:
                if is_numeric:
                    # Changing numbers are usually SHOTS
                    ttype = TokenType.SHOT
                    m = re.search(r"(\d+)", val)
                    padding = len(m.group(1)) if m else 0
                else:
                    ttype = TokenType.SHOT  # Fallback for alpha shots
            else:
                # Static parts
                if i == 0:
                    ttype = TokenType.SEQUENCE
                elif val.lower().startswith("v") and re.search(r"\d+", val):
                    ttype = TokenType.VERSION
                    prefix = val[0]
                    m = re.search(r"(\d+)", val)
                    padding = len(m.group(1)) if m else 0
                elif i == n_parts - 1 and is_numeric:
                    ttype = TokenType.VERSION
                else:
                    ttype = TokenType.IGNORE

            # Prevent duplicate core types in simple guess
            if ttype in [TokenType.SHOT, TokenType.SEQUENCE, TokenType.VERSION]:
                if ttype in assigned_types:
                    ttype = TokenType.IGNORE
                else:
                    assigned_types.add(ttype)

            guessed_tokens.append(
                ArchitectToken(type=ttype, padding=padding, prefix=prefix)
            )
            if i < n_parts - 1:
                guessed_tokens.append(
                    ArchitectToken(type=TokenType.SEPARATOR, value=best_sep)
                )

        return guessed_tokens


# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------


class VisualTokenWidget(QFrame):
    """A pill-shaped interactive token with professional pipeline styling."""

    clicked = Signal(ArchitectToken)
    deleted = Signal(object)

    def __init__(self, token: ArchitectToken, parent=None) -> None:
        super().__init__(parent)
        self.token = token
        self._drag_start_pos = None  # Initialize drag position
        self._setup_layout()
        self.update_visuals()

    def _setup_layout(self) -> None:
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)  # Tighter, professional height
        self.setMinimumWidth(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)  # Margin for the accent bar
        layout.setSpacing(8)

        # Color Accent Bar (Tier 1 Aesthetic)
        self.accent = QFrame()
        self.accent.setFixedWidth(4)
        self.accent.setStyleSheet(
            "border-top-left-radius: 4px; border-bottom-left-radius: 4px;"
        )
        layout.addWidget(self.accent)

        self.label = QLabel()
        self.label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.label.setStyleSheet("color: #eee; border: none; background: transparent;")
        layout.addWidget(self.label, 1)

    def update_visuals(self, has_collision: bool = False) -> None:
        """Apply a professional matte theme with color-coded accents."""
        colors = {
            TokenType.SEQUENCE: "#27ae60",  # Emerald
            TokenType.SHOT: "#00bff3",  # Standard Cyan
            TokenType.VERSION: "#f39c12",  # Amber
            TokenType.SEPARATOR: "#555555",  # Muted Gray
            TokenType.WILDCARD: "#8e44ad",  # Purple
            TokenType.IGNORE: "#333333",  # Dark
        }
        accent_color = colors.get(self.token.type, "#444")
        if has_collision:
            accent_color = "#f44747"  # Red collision

        self.accent.setStyleSheet(f"background-color: {accent_color};")

        text = self.token.type.name.capitalize()
        if self.token.type == TokenType.SEPARATOR:
            text = f"'{self.token.value or ' '}'"
        elif self.token.type == TokenType.VERSION and self.token.prefix:
            text = f"{self.token.prefix}Ver"
        self.label.setText(text.upper())

        border = "#f44747" if has_collision else "#333"
        bg = "#252526" if not has_collision else "#3d1c1c"

        self.setStyleSheet(f"""
            VisualTokenWidget {{
                background-color: {bg};
                border-radius: 4px;
                border: 1px solid {border};
            }}
            VisualTokenWidget:hover {{
                background-color: #2d2d30;
                border-color: #555;
            }}
        """)

    def enterEvent(self, event) -> None:
        # Subtle hover lift
        self.move(self.x(), self.y() - 2)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        # Reset hover lift
        self.move(self.x(), self.y() + 2)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self.clicked.emit(self.token)
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start_pos is None:  # Safety check
            return
        if (
            event.pos() - self._drag_start_pos
        ).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        # Store widget pointer for internal move
        mime.setData("application/x-ramses-token", str(id(self)).encode())
        drag.setMimeData(mime)

        # Create a preview of the token being dragged
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        drag.exec(Qt.DropAction.MoveAction)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_del = QAction("Remove Token", self)
        act_del.triggered.connect(lambda: self.deleted.emit(self))
        menu.addAction(act_del)
        menu.exec(self.mapToGlobal(pos))


class TokenDropZone(QFrame):
    """The assembly bar where tokens are placed and reordered."""

    changed = Signal()
    token_clicked = Signal(ArchitectToken)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(80)  # Stabilize height
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "background-color: #1a1a1a; border: 1px dashed #333; border-radius: 6px;"
        )

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 5, 10, 5)
        self.layout.setSpacing(8)
        self.layout.addStretch()

    def add_token(self, token: ArchitectToken) -> None:
        widget = VisualTokenWidget(token)
        widget.clicked.connect(self.token_clicked.emit)
        widget.deleted.connect(self._on_token_deleted)
        # Insert before the stretch
        self.layout.insertWidget(self.layout.count() - 1, widget)
        self._check_collisions()
        self.changed.emit()

    def _on_token_deleted(self, widget) -> None:
        widget.deleteLater()
        # Delay check to ensure widget is removed from layout
        from PySide6.QtCore import QTimer

        QTimer.singleShot(10, self._check_collisions)
        QTimer.singleShot(10, self.changed.emit)

    def _check_collisions(self) -> None:
        """Visual Shadow Rule: Warn if two dynamic tokens touch without a separator."""
        widgets = []
        for i in range(self.layout.count()):
            w = self.layout.itemAt(i).widget()
            if isinstance(w, VisualTokenWidget):
                widgets.append(w)

        for i in range(len(widgets)):
            w1 = widgets[i]
            clash = False

            # Check adjacency with next widget
            if i < len(widgets) - 1:
                w2 = widgets[i + 1]
                # If both are capture groups (not separators/ignore) they clash
                if w1.token.type not in [
                    TokenType.SEPARATOR,
                    TokenType.IGNORE,
                ] and w2.token.type not in [TokenType.SEPARATOR, TokenType.IGNORE]:
                    clash = True

            w1.update_visuals(has_collision=clash)
            if clash:
                w1.setToolTip(
                    "Collision Risk: Add a separator to prevent greedy matching."
                )
            else:
                w1.setToolTip("")

    def clear(self) -> None:
        """Remove all tokens from the drop zone immediately."""
        for i in reversed(range(self.layout.count())):
            item = self.layout.itemAt(i)
            w = item.widget()
            if w and isinstance(w, VisualTokenWidget):
                self.layout.removeWidget(w)
                w.deleteLater()
        self.changed.emit()

    def get_tokens(self) -> list[ArchitectToken]:
        tokens = []
        for i in range(self.layout.count()):
            w = self.layout.itemAt(i).widget()
            if isinstance(w, VisualTokenWidget):
                tokens.append(w.token)
        return tokens

    # --- Reordering Logic ---
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-ramses-token"):
            event.accept()

    def dropEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-ramses-token"):
            source_id = int(
                event.mimeData().data("application/x-ramses-token").data().decode()
            )

            # Find source widget
            source_widget = None
            for i in range(self.layout.count()):
                w = self.layout.itemAt(i).widget()
                if id(w) == source_id:
                    source_widget = w
                    break

            if not source_widget:
                return

            # Find target index based on mouse position
            drop_pos = event.position().x()
            target_idx = self.layout.count() - 1  # Default to before the stretch

            for i in range(self.layout.count()):
                w = self.layout.itemAt(i).widget()
                if w and w != source_widget and isinstance(w, VisualTokenWidget):
                    if drop_pos < w.geometry().center().x():
                        target_idx = i
                        break

            # Re-insert
            self.layout.removeWidget(source_widget)
            self.layout.insertWidget(target_idx, source_widget)
            self._check_collisions()
            self.changed.emit()
            event.accept()


class SimulationTable(QTableWidget):
    """The 'Live Lab' showing real-time match results with X-Ray highlighting."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["X-Ray Filename", "Sequence", "Shot", "Status"])

        hdr = self.horizontalHeader()
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)

        # Interactive Resizing (Tier 1 Logic)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Filename
        hdr.resizeSection(0, 300)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Seq
        hdr.resizeSection(1, 100)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Shot
        hdr.resizeSection(2, 100)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Status

        self.setStyleSheet(
            "background-color: #1a1a1a; color: #ccc; gridline-color: #333;"
        )
        self.verticalHeader().setVisible(False)

    def refresh(self, samples: list[str], tokens: list[ArchitectToken]) -> None:
        self.setRowCount(len(samples))

        # Color mapping for X-Ray (matching Token colors)
        colors = {
            "sequence": "#27ae60",
            "shot": "#2980b9",
            "version": "#f39c12",
            "step": "#e74c3c",
            "project": "#1abc9c",
        }

        pattern = TokenEngine.compile(tokens)
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except Exception:
            regex = None

        for row, original_path in enumerate(samples):
            # 1. Clean filename only
            filename = os.path.basename(original_path)

            # 2. Perform simulation
            res = {}
            if regex:
                match = regex.match(filename)
                if match:
                    res = match.groupdict()

            # 3. Build X-Ray HTML
            xray_html = filename
            if regex and res:
                match = regex.match(filename)
                spans = []
                for group_name, value in res.items():
                    try:
                        start, end = match.span(group_name)
                        if start != -1:
                            color = colors.get(group_name, "#ffffff")
                            spans.append((start, end, color))
                    except IndexError:
                        continue

                spans.sort(key=lambda x: x[0], reverse=True)

                temp_text = filename
                for start, end, color in spans:
                    snippet = temp_text[start:end]
                    if snippet:
                        temp_text = (
                            temp_text[:start]
                            + f'<span style="color:{color}; font-weight:bold;">{snippet}</span>'
                            + temp_text[end:]
                        )
                xray_html = temp_text

            # --- Table Items ---
            lbl = QLabel(
                f'<html><body style="font-family:Consolas, monospace; font-size:11px;">{xray_html}</body></html>'
            )
            lbl.setStyleSheet("padding-left: 5px; background: transparent;")
            self.setCellWidget(row, 0, lbl)

            it_seq = QTableWidgetItem(res.get("sequence", "—"))
            it_shot = QTableWidgetItem(res.get("shot", "—"))

            status = "MATCHED" if res.get("shot") else "FAILED"
            it_status = QTableWidgetItem(status)

            if status == "MATCHED":
                it_status.setForeground(QColor("#27ae60"))
            else:
                it_status.setForeground(QColor("#c0392b"))

            self.setItem(row, 1, it_seq)
            self.setItem(row, 2, it_shot)
            self.setItem(row, 3, it_status)


class TokenInspector(QFrame):
    """Side panel for editing token constraints (padding, prefix, etc.)."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._token: ArchitectToken | None = None
        self._setup_ui()
        self.setVisible(False)

    def _setup_ui(self) -> None:
        self.setFixedWidth(240)
        self.setStyleSheet(
            "background-color: #252526; border-left: 1px solid #333; padding: 10px;"
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(12)

        self.title = QLabel("TOKEN INSPECTOR")
        self.title.setStyleSheet("color: #888; font-weight: bold; font-size: 10px;")
        self.layout.addWidget(self.title)

        # --- Value (for Separators) ---
        self.val_box = QWidget()
        v_lay = QVBoxLayout(self.val_box)
        v_lay.setContentsMargins(0, 0, 0, 0)
        v_lay.addWidget(QLabel("Separator Value:"))
        self.edit_val = QLineEdit()
        self.edit_val.textChanged.connect(self._on_val_changed)
        v_lay.addWidget(self.edit_val)
        self.layout.addWidget(self.val_box)

        # --- Prefix (for Version) ---
        self.pre_box = QWidget()
        p_lay = QVBoxLayout(self.pre_box)
        p_lay.setContentsMargins(0, 0, 0, 0)
        p_lay.addWidget(QLabel("Prefix (e.g. 'v'):"))
        self.edit_pre = QLineEdit()
        self.edit_pre.textChanged.connect(self._on_pre_changed)
        p_lay.addWidget(self.edit_pre)
        self.layout.addWidget(self.pre_box)

        # --- Padding ---
        self.pad_box = QWidget()
        pd_lay = QVBoxLayout(self.pad_box)
        pd_lay.setContentsMargins(0, 0, 0, 0)
        pd_lay.addWidget(QLabel("Padding (digits):"))
        self.spin_pad = QSpinBox()
        self.spin_pad.setRange(0, 10)
        self.spin_pad.valueChanged.connect(self._on_pad_changed)
        pd_lay.addWidget(self.spin_pad)
        self.layout.addWidget(self.pad_box)

        self.layout.addStretch()

    def inspect(self, token: ArchitectToken) -> None:
        self._token = token
        self.setVisible(True)
        self.title.setText(f"INSPECTING: {token.type.name}")

        # Show/Hide relevant controls
        self.val_box.setVisible(token.type == TokenType.SEPARATOR)
        self.pre_box.setVisible(token.type == TokenType.VERSION)
        self.pad_box.setVisible(
            token.type in [TokenType.VERSION, TokenType.SHOT, TokenType.SEQUENCE]
        )

        # Block signals to prevent feedback loop
        self.edit_val.blockSignals(True)
        self.edit_pre.blockSignals(True)
        self.spin_pad.blockSignals(True)

        self.edit_val.setText(token.value)
        self.edit_pre.setText(token.prefix)
        self.spin_pad.setValue(token.padding)

        self.edit_val.blockSignals(False)
        self.edit_pre.blockSignals(False)
        self.spin_pad.blockSignals(False)

    def _on_val_changed(self, text: str) -> None:
        if self._token:
            self._token.value = text
            self.changed.emit()

    def _on_pre_changed(self, text: str) -> None:
        if self._token:
            self._token.prefix = text
            self.changed.emit()

    def _on_pad_changed(self, val: int) -> None:
        if self._token:
            self._token.padding = val
            self.changed.emit()


# ---------------------------------------------------------------------------
# Annotation Mode Widgets
# ---------------------------------------------------------------------------


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


class AnnotationChip(QFrame):
    """A small colored chip showing one annotation."""

    removed = Signal(str)  # field_name

    def __init__(self, field_name: str, selected_text: str, color: str, parent=None):
        super().__init__(parent)
        self.field_name = field_name
        self.selected_text = selected_text
        self.color = color
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(24)
        self.setStyleSheet(f"""
            AnnotationChip {{
                background-color: #252526;
                border-left: 3px solid {self.color};
                border-radius: 3px;
                padding: 2px 6px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        # Field name label
        field_label = QLabel(self.field_name.capitalize())
        field_label.setStyleSheet(f"color: {self.color}; font-weight: bold; font-size: 10px;")
        layout.addWidget(field_label)

        # Selected text
        text_label = QLabel(f'"{self.selected_text}"')
        text_label.setStyleSheet("color: #ccc; font-size: 10px;")
        layout.addWidget(text_label)

        # Remove button
        btn_remove = QPushButton("✕")
        btn_remove.setFixedSize(16, 16)
        btn_remove.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: none;
                font-size: 10px;
            }
            QPushButton:hover {
                color: #f44747;
            }
        """)
        btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_remove.clicked.connect(lambda: self.removed.emit(self.field_name))
        layout.addWidget(btn_remove)


class AnnotationSummaryStrip(QWidget):
    """Horizontal row of AnnotationChip widgets."""

    annotation_removed = Signal(str)  # field_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chips = {}  # field_name -> AnnotationChip
        self._setup_ui()

    def _setup_ui(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.layout.addWidget(QLabel("Annotations:"))
        self.layout.addStretch()

    def add_annotation(self, field_name: str, selected_text: str, color: str):
        """Add or update an annotation chip."""
        # Remove existing chip if present
        if field_name in self._chips:
            self.remove_annotation(field_name)

        # Create new chip
        chip = AnnotationChip(field_name, selected_text, color)
        chip.removed.connect(self._on_chip_removed)
        self._chips[field_name] = chip

        # Insert before stretch
        self.layout.insertWidget(self.layout.count() - 1, chip)

    def remove_annotation(self, field_name: str):
        """Remove an annotation chip."""
        if field_name in self._chips:
            chip = self._chips[field_name]
            self.layout.removeWidget(chip)
            chip.deleteLater()
            del self._chips[field_name]

    def _on_chip_removed(self, field_name: str):
        """Handle chip removal."""
        self.remove_annotation(field_name)
        self.annotation_removed.emit(field_name)

    def clear(self):
        """Remove all annotation chips."""
        for field_name in list(self._chips.keys()):
            self.remove_annotation(field_name)


class InlineCandidateList(QWidget):
    """Shows top pattern candidates inline."""

    candidate_selected = Signal(PatternCandidate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        self.title_label = QLabel("Best Patterns:")
        self.title_label.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
        main_layout.addWidget(self.title_label)

        # Scrollable area for candidates
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_content = QWidget()
        self.layout = QVBoxLayout(scroll_content)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def set_candidates(self, candidates: list[PatternCandidate], examples: list[str], field_names: list[str]):
        """Display top 3 candidates."""
        # Clear existing candidates from scroll layout
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not candidates:
            no_cand_label = QLabel("No patterns generated yet.")
            no_cand_label.setStyleSheet("color: #888; font-style: italic; font-size: 10px;")
            self.layout.addWidget(no_cand_label)
            return

        # Show top 3
        for cand in candidates[:3]:
            widget = self._create_candidate_widget(cand, examples, field_names)
            self.layout.addWidget(widget)

        # Add stretch at the end to push candidates to top
        self.layout.addStretch()

    def _create_candidate_widget(self, candidate: PatternCandidate, examples: list[str], field_names: list[str]) -> QFrame:
        """Create a candidate widget with extraction preview."""
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
            }
            QFrame:hover {
                background-color: #2d2d30;
                border-color: #00bff3;
            }
        """)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.mousePressEvent = lambda e: self.candidate_selected.emit(candidate)

        layout = QVBoxLayout(frame)
        layout.setSpacing(4)

        # Confidence
        conf_label = QLabel(f"{candidate.confidence:.0%}")
        conf_color = (
            "#4ec9b0" if candidate.confidence >= 0.7
            else "#f39c12" if candidate.confidence >= 0.5
            else "#f44747"
        )
        conf_label.setStyleSheet(f"color: {conf_color}; font-weight: bold; font-size: 11px;")
        layout.addWidget(conf_label)

        # Pattern
        pattern_label = QLabel(candidate.pattern)
        pattern_label.setStyleSheet("font-family: 'Consolas', monospace; color: #4ec9b0; font-size: 9px;")
        pattern_label.setWordWrap(True)
        layout.addWidget(pattern_label)

        # Description
        desc_label = QLabel(candidate.description)
        desc_label.setStyleSheet("color: #888; font-size: 9px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Preview of extractions (first 3 examples)
        if examples:
            preview_label = QLabel("Preview:")
            preview_label.setStyleSheet("color: #888; font-size: 9px; margin-top: 4px;")
            layout.addWidget(preview_label)

            for example in examples[:3]:
                filename = os.path.basename(example)
                display_name = filename[:35] + "..." if len(filename) > 35 else filename

                # Test pattern against this example
                match = re.search(candidate.pattern, filename)
                if match and field_names:
                    groups = match.groupdict()
                    # Build extraction display for all fields
                    extractions = []
                    for field in field_names:
                        if field in groups and groups[field]:
                            extractions.append(f"{field}={groups[field]}")

                    if extractions:
                        val_str = ", ".join(extractions)
                        val_color = "#4ec9b0"
                    else:
                        val_str = "None"
                        val_color = "#888"
                else:
                    val_str = "None"
                    val_color = "#888"

                ex_label = QLabel(f"  {display_name} → {val_str}")
                ex_label.setStyleSheet(
                    f"color: {val_color}; font-family: 'Consolas', monospace; font-size: 9px;"
                )
                layout.addWidget(ex_label)

        return frame


class AnnotationWorkspaceWidget(QWidget):
    """Composite widget for annotation mode."""

    pattern_selected = Signal(str)  # pattern

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = PatternInferenceEngine()
        self._annotations = {}  # field_name -> Annotation
        self._samples = []
        self._current_example = ""
        self._selected_text = ""
        self._selected_start = 0
        self._selected_end = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Example selector
        example_row = QHBoxLayout()
        example_row.addWidget(QLabel("SELECT EXAMPLE:"))
        self.example_combo = QComboBox()
        self.example_combo.setMinimumWidth(300)
        self.example_combo.currentTextChanged.connect(self._on_example_changed)
        example_row.addWidget(self.example_combo)
        example_row.addStretch()
        layout.addLayout(example_row)

        # Annotatable text edit
        self.text_edit = AnnotatableTextEdit()
        self.text_edit.annotation_requested.connect(self._on_annotation_requested)
        layout.addWidget(self.text_edit)

        # Field buttons
        button_row = QHBoxLayout()
        self.field_buttons = {}
        for field_name in ["shot", "sequence", "version", "resource"]:
            btn = QPushButton(field_name.capitalize())
            btn.setMinimumHeight(32)
            btn.setEnabled(False)
            btn.clicked.connect(lambda checked, f=field_name: self._on_field_button_clicked(f))
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #4a4a4a;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:disabled {
                    background-color: #2a2a2a;
                    color: #666;
                }
                QPushButton:hover:enabled {
                    background-color: #00677a;
                }
            """)
            self.field_buttons[field_name] = btn
            button_row.addWidget(btn)

        button_row.addStretch()

        # Clear button
        btn_clear = QPushButton("Clear Annotations")
        btn_clear.clicked.connect(self._on_clear_annotations)
        btn_clear.setStyleSheet("background-color: #6a3a3a; color: white;")
        button_row.addWidget(btn_clear)

        layout.addLayout(button_row)

        # Annotation summary
        self.summary_strip = AnnotationSummaryStrip()
        self.summary_strip.annotation_removed.connect(self._on_annotation_removed)
        layout.addWidget(self.summary_strip)

        # Candidate list (with fixed height to prevent resize jumps)
        self.candidate_list = InlineCandidateList()
        self.candidate_list.candidate_selected.connect(self._on_candidate_selected)
        self.candidate_list.setMinimumHeight(400)  # Prevent jarring resize
        self.candidate_list.setMaximumHeight(400)  # Keep it consistent
        layout.addWidget(self.candidate_list)

        layout.addStretch()

    def set_samples(self, samples: list[str]):
        """Populate the example combo with samples."""
        self._samples = samples
        self.example_combo.clear()
        if samples:
            self.example_combo.addItems([os.path.basename(s) for s in samples])

    def _on_example_changed(self, example: str):
        """Update the text edit when example changes."""
        if example and example != self._current_example:
            # Warn if annotations exist
            if self._annotations:
                from PySide6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self,
                    "Change Example",
                    "Changing examples will clear existing annotations. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    # Revert to current example
                    self.example_combo.setCurrentText(os.path.basename(self._current_example))
                    return
                self._clear_annotations()

            self._current_example = example
            self.text_edit.setPlainText(example)

    def _on_annotation_requested(self, selected_text: str, start: int, end: int):
        """Enable field buttons when text is selected."""
        self._selected_text = selected_text
        self._selected_start = start
        self._selected_end = end

        # Enable all field buttons
        for btn in self.field_buttons.values():
            btn.setEnabled(True)

    def _on_field_button_clicked(self, field_name: str):
        """Add annotation for the selected field."""
        if not self._selected_text:
            return

        # Create annotation
        annotation = Annotation(
            example=self._current_example,
            selected_text=self._selected_text,
            field_name=field_name,
            start_pos=self._selected_start,
            end_pos=self._selected_end
        )

        self._annotations[field_name] = annotation

        # Color mapping
        colors = {
            "sequence": "#27ae60",
            "shot": "#00bff3",
            "version": "#f39c12",
            "resource": "#8e44ad"
        }
        color = colors.get(field_name, "#888")

        # Add to summary strip
        self.summary_strip.add_annotation(field_name, self._selected_text, color)

        # Apply highlighting to text edit
        self._apply_highlights()

        # Generate patterns
        self._generate_patterns()

        # Disable field buttons until next selection
        for btn in self.field_buttons.values():
            btn.setEnabled(False)

    def _on_annotation_removed(self, field_name: str):
        """Remove annotation when chip is removed."""
        if field_name in self._annotations:
            del self._annotations[field_name]

        # Re-apply highlights
        self._apply_highlights()

        # Regenerate patterns
        if self._annotations:
            self._generate_patterns()
        else:
            self.candidate_list.set_candidates([], [], [])

    def _on_clear_annotations(self):
        """Clear all annotations."""
        self._clear_annotations()

    def _clear_annotations(self):
        """Clear all annotations and reset state."""
        self._annotations.clear()
        self.summary_strip.clear()
        self.text_edit.setPlainText(self._current_example)
        self.candidate_list.set_candidates([], [], [])

    def _apply_highlights(self):
        """Apply colored highlights to annotated text."""
        # Clear all formatting first
        cursor = QTextCursor(self.text_edit.document())
        cursor.select(QTextCursor.SelectionType.Document)
        default_format = QTextCharFormat()
        cursor.setCharFormat(default_format)

        # Apply highlights for each annotation
        colors = {
            "sequence": "#27ae60",
            "shot": "#00bff3",
            "version": "#f39c12",
            "resource": "#8e44ad"
        }

        for field_name, annotation in self._annotations.items():
            cursor = QTextCursor(self.text_edit.document())
            cursor.setPosition(annotation.start_pos)
            cursor.setPosition(annotation.end_pos, QTextCursor.MoveMode.KeepAnchor)

            fmt = QTextCharFormat()
            fmt.setBackground(QColor(colors.get(field_name, "#888")))
            fmt.setForeground(QColor("#000000"))
            cursor.setCharFormat(fmt)

    def _generate_patterns(self):
        """Generate pattern candidates from current annotations."""
        if not self._annotations:
            self.candidate_list.set_candidates([], [], [])
            return

        field_names = list(self._annotations.keys())

        if len(self._annotations) == 1:
            # Single field - use normal inference
            field_name = field_names[0]
            annotation = self._annotations[field_name]
            candidates = self._engine.infer_pattern([annotation], test_examples=self._samples)
        else:
            # Multiple fields - use combined inference
            try:
                candidates = self._engine.infer_combined_pattern(
                    self._annotations,
                    test_examples=self._samples
                )
            except ValueError as e:
                # Show error if annotations span different examples
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Pattern Error", str(e))
                return

        self.candidate_list.set_candidates(candidates, self._samples, field_names)

    def _on_candidate_selected(self, candidate: PatternCandidate):
        """Emit the selected pattern."""
        self.pattern_selected.emit(candidate.pattern)


class NamingArchitectDialog(QDialog):
    """The professional 'Slide-over' style rule builder."""

    def __init__(self, parent=None, existing_patterns: list[str] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ramses Naming Architect")
        self.resize(1100, 650)
        self.setStyleSheet(STYLESHEET)
        self._samples = []
        self._mode = "token"  # "token" or "annotate"
        self._smart_pattern: str | None = None  # Pattern from annotation workspace
        self._rule_name: str = ""  # User-provided name for the rule
        self._existing_patterns = existing_patterns or []  # For duplicate detection
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Professional single-screen layout (no sidebars, no splitters)"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # ═══════════════════════════════════════════════════════════════════════
        # HEADER - Mode Toggle + Quick Actions
        # ═══════════════════════════════════════════════════════════════════════
        header = QHBoxLayout()

        # Mode toggle buttons
        mode_label = QLabel("Build Mode:")
        mode_label.setStyleSheet("color: #888; font-weight: bold;")
        header.addWidget(mode_label)

        self.btn_token_mode = QPushButton("Token Mode")
        self.btn_token_mode.setCheckable(True)
        self.btn_token_mode.setChecked(True)
        self.btn_token_mode.setMinimumHeight(32)
        self.btn_token_mode.clicked.connect(lambda: self._on_mode_toggle("token"))
        header.addWidget(self.btn_token_mode)

        self.btn_annotate_mode = QPushButton("Annotate Mode")
        self.btn_annotate_mode.setCheckable(True)
        self.btn_annotate_mode.setChecked(False)
        self.btn_annotate_mode.setMinimumHeight(32)
        self.btn_annotate_mode.clicked.connect(lambda: self._on_mode_toggle("annotate"))
        header.addWidget(self.btn_annotate_mode)

        header.addSpacing(20)

        # Quick Start presets (token mode only)
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
        self.btn_magic.setStyleSheet(
            "background-color: #4a4a4a; color: white; font-weight: bold; padding: 8px 16px;"
        )
        self.btn_magic.clicked.connect(self._on_magic_wand)
        self.btn_magic.setEnabled(False)
        self.btn_magic.setToolTip("Auto-detect pattern from sample filenames")
        header.addWidget(self.btn_magic)

        main_layout.addLayout(header)

        # Update mode toggle styling
        self._update_mode_toggle_styling()

        # ═══════════════════════════════════════════════════════════════════════
        # WORKSPACE - Stacked Widget (Token Mode / Annotate Mode)
        # ═══════════════════════════════════════════════════════════════════════
        self.workspace_stack = QStackedWidget()

        # ───────────────────────────────────────────────────────────────────────
        # PAGE 0: TOKEN MODE
        # ───────────────────────────────────────────────────────────────────────
        token_page = QWidget()
        token_layout = QVBoxLayout(token_page)
        token_layout.setContentsMargins(0, 0, 0, 0)
        token_layout.setSpacing(8)

        # Blueprint label
        lbl_blue = QLabel("PATTERN BLUEPRINT")
        lbl_blue.setStyleSheet("color: #888; font-size: 10px; font-weight: bold;")
        token_layout.addWidget(lbl_blue)

        # Blueprint container
        self.blueprint_container = QFrame()
        self.blueprint_container.setFixedHeight(80)
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

        token_layout.addWidget(self.blueprint_container)

        # Token palette
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

        token_layout.addLayout(palette_row)

        self.workspace_stack.addWidget(token_page)

        # ───────────────────────────────────────────────────────────────────────
        # PAGE 1: ANNOTATE MODE
        # ───────────────────────────────────────────────────────────────────────
        self.annotate_workspace = AnnotationWorkspaceWidget()
        self.annotate_workspace.pattern_selected.connect(self._on_smart_pattern_selected)
        self.workspace_stack.addWidget(self.annotate_workspace)

        main_layout.addWidget(self.workspace_stack)

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
        self.match_stats.setStyleSheet(
            "color: #00bff3; font-size: 10px; font-weight: bold;"
        )
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
        regex_container.setStyleSheet(
            "background-color: #1e1e1e; border-radius: 4px; padding: 8px;"
        )
        regex_lay = QVBoxLayout(regex_container)
        regex_lay.setContentsMargins(8, 8, 8, 8)
        regex_lay.setSpacing(4)

        regex_header = QHBoxLayout()
        self.regex_toggle = QPushButton("▼ Generated Regex")
        self.regex_toggle.setStyleSheet(
            "text-align: left; background: transparent; border: none; color: #888;"
        )
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

        # Rule name input
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Rule Name (optional):"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., RO9S Project, ISIH Shots...")
        self.name_edit.setMaximumWidth(300)
        self.name_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
                color: #ccc;
            }
        """)
        name_row.addWidget(self.name_edit)
        name_row.addStretch()
        main_layout.addLayout(name_row)

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
        btn_apply.setStyleSheet(
            "background-color: #094771; color: white; font-weight: bold;"
        )
        btn_apply.clicked.connect(self._on_apply_clicked)
        btn_row.addWidget(btn_apply)

        main_layout.addLayout(btn_row)

    # ═══════════════════════════════════════════════════════════════════════
    # Professional UI Supporting Methods
    # ═══════════════════════════════════════════════════════════════════════

    def _on_preset_selected(self, index: int) -> None:
        """Apply preset from dropdown"""
        if index == 0:  # "Build Custom Rule"
            return

        presets = {
            1: [TokenType.SEQUENCE, "_", TokenType.SHOT],  # Standard Shot
            2: [
                TokenType.SEQUENCE,
                "_",
                TokenType.SHOT,
                "_",
                TokenType.VERSION,
            ],  # Shot & Version
            3: [
                TokenType.PROJECT,
                "_",
                TokenType.SEQUENCE,
                "_",
                TokenType.SHOT,
            ],  # Technicolor
            4: [TokenType.SHOT],  # Flat Delivery
        }

        pattern = presets.get(index, [])
        self._apply_preset(pattern)

        # Reset combo to default
        self.preset_combo.setCurrentIndex(0)

    def _update_mode_toggle_styling(self) -> None:
        """Update mode toggle button styling based on active mode."""
        active_style = """
            QPushButton {
                background-color: #094771;
                color: white;
                font-weight: bold;
                border: 2px solid #00bff3;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: #888;
                font-weight: normal;
                border: 1px solid #555;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                color: #aaa;
            }
        """

        if self._mode == "token":
            self.btn_token_mode.setStyleSheet(active_style)
            self.btn_annotate_mode.setStyleSheet(inactive_style)
            self.btn_token_mode.setChecked(True)
            self.btn_annotate_mode.setChecked(False)
        else:
            self.btn_token_mode.setStyleSheet(inactive_style)
            self.btn_annotate_mode.setStyleSheet(active_style)
            self.btn_token_mode.setChecked(False)
            self.btn_annotate_mode.setChecked(True)

    def _on_mode_toggle(self, mode: str) -> None:
        """Toggle between token mode and annotate mode."""
        if self._mode == mode:
            return  # Already in this mode

        self._mode = mode
        self._update_mode_toggle_styling()

        # Switch workspace stack
        if mode == "token":
            self.workspace_stack.setCurrentIndex(0)
            self._on_rule_changed()  # Refresh with token pattern
        else:  # annotate
            self.workspace_stack.setCurrentIndex(1)
            # Feed samples to annotation workspace
            self.annotate_workspace.set_samples(self._samples)

    def _on_smart_pattern_selected(self, pattern: str) -> None:
        """Handle pattern selected from annotation workspace."""
        self._smart_pattern = pattern
        self._mode = "annotate"  # Ensure mode is set to annotate

        # Update regex display
        self.regex_label.setText(pattern)
        self.regex_label.setVisible(True)
        self.regex_toggle.setText("▲ Generated Regex (Annotate Mode)")

        # Update simulation with the smart pattern
        self._refresh_simulation_with_pattern(pattern)

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
                self, "Edit Separator", "Separator character:", text=token.value
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
                self,
                "Version Prefix",
                "Select version prefix:",
                items,
                items.index(current),
                False,
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
        self.regex_toggle.setText(
            "▲ Generated Regex" if not is_visible else "▼ Generated Regex"
        )

    def _copy_regex(self) -> None:
        """Copy regex to clipboard"""
        from PySide6.QtWidgets import QApplication

        pattern = TokenEngine.compile(self.drop_zone.get_tokens())
        QApplication.clipboard().setText(pattern)

    def _on_samples_changed(self) -> None:
        """Update samples list and feed to both modes."""
        text = self.sample_edit.toPlainText()
        self._samples = [
            os.path.basename(line.strip()) for line in text.splitlines() if line.strip()
        ]
        self.btn_magic.setEnabled(len(self._samples) > 0)

        # Feed samples to annotation workspace
        self.annotate_workspace.set_samples(self._samples)

        # Update simulation based on current mode
        if self._mode == "annotate" and self._smart_pattern:
            self._refresh_simulation_with_pattern(self._smart_pattern)
        else:
            self._on_rule_changed()

    def _on_rule_changed(self) -> None:
        """Update regex display and simulation results"""
        self._mode = "token"
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

                color = (
                    "#4ec9b0" if pct >= 80 else "#f39c12" if pct >= 50 else "#f44747"
                )
                self.match_stats.setText(f"{matched}/{total} matched ({pct}%)")
                self.match_stats.setStyleSheet(
                    f"color: {color}; font-size: 10px; font-weight: bold;"
                )
            except re.error:
                # Invalid regex pattern
                self.match_stats.setText("Invalid pattern")
                self.match_stats.setStyleSheet(
                    "color: #f44747; font-size: 10px; font-weight: bold;"
                )
            except Exception as e:
                # Unexpected error (memory, encoding issues, etc.)
                self.match_stats.setText(f"Error: {type(e).__name__}")
                self.match_stats.setStyleSheet(
                    "color: #f44747; font-size: 10px; font-weight: bold;"
                )
        else:
            self.match_stats.setText("0/0 matched (0%)")

    def _apply_preset(self, pattern: list[TokenType | str]) -> None:
        """Apply a predefined pattern to the blueprint."""
        self.drop_zone.clear()
        for item in pattern:
            if isinstance(item, str):
                self.drop_zone.add_token(
                    ArchitectToken(type=TokenType.SEPARATOR, value=item)
                )
            else:
                self.drop_zone.add_token(ArchitectToken(type=item))
        self._on_rule_changed()

    def _on_magic_wand(self) -> None:
        """Heuristically guess tokens from samples and populate the drop zone."""
        if not self._samples:
            return

        guessed = TokenEngine.guess_tokens(self._samples)
        if guessed:
            self.drop_zone.clear()
            for t in guessed:
                self.drop_zone.add_token(t)
            self._on_rule_changed()

    def _refresh_simulation_with_pattern(self, pattern: str) -> None:
        """Refresh simulation table with a raw regex pattern."""
        if not self._samples:
            return

        try:
            regex = re.compile(pattern, re.IGNORECASE)
            matched = sum(1 for s in self._samples if regex.match(os.path.basename(s)))
            total = len(self._samples)
            pct = int(matched / total * 100) if total > 0 else 0

            color = "#4ec9b0" if pct >= 80 else "#f39c12" if pct >= 50 else "#f44747"
            self.match_stats.setText(f"{matched}/{total} matched ({pct}%)")
            self.match_stats.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: bold;"
            )

            # Update simulation table (it can handle raw regex)
            # We'll pass empty tokens, but override with raw pattern
            self.sim_table.setRowCount(len(self._samples))

            for row, full_path in enumerate(self._samples):
                filename = os.path.basename(full_path)
                match = regex.match(filename)
                res = match.groupdict() if match else {}

                # Filename
                lbl = QLabel(
                    f'<html><body style="font-family:Consolas, monospace; font-size:11px;">{filename}</body></html>'
                )
                lbl.setStyleSheet("padding-left: 5px; background: transparent;")
                self.sim_table.setCellWidget(row, 0, lbl)

                # Extracted values
                from PySide6.QtWidgets import QTableWidgetItem
                from PySide6.QtGui import QColor

                it_seq = QTableWidgetItem(res.get("sequence", "—"))
                it_shot = QTableWidgetItem(res.get("shot", "—"))

                status = "MATCHED" if res.get("shot") else "FAILED"
                it_status = QTableWidgetItem(status)

                if status == "MATCHED":
                    it_status.setForeground(QColor("#27ae60"))
                else:
                    it_status.setForeground(QColor("#c0392b"))

                self.sim_table.setItem(row, 1, it_seq)
                self.sim_table.setItem(row, 2, it_shot)
                self.sim_table.setItem(row, 3, it_status)

        except re.error:
            self.match_stats.setText("Invalid pattern")
            self.match_stats.setStyleSheet(
                "color: #f44747; font-size: 10px; font-weight: bold;"
            )

    def _on_apply_clicked(self) -> None:
        """Handle Apply button click with duplicate checking."""
        from PySide6.QtWidgets import QMessageBox

        # Get the pattern
        pattern = self.get_final_regex()

        if not pattern:
            QMessageBox.warning(
                self,
                "No Pattern",
                "Please create a pattern first (using tokens or annotations)."
            )
            return

        # Check for duplicate
        if pattern in self._existing_patterns:
            reply = QMessageBox.question(
                self,
                "Duplicate Pattern",
                f"This pattern already exists in your project:\n\n{pattern}\n\n"
                "Do you want to add it again anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # Store the rule name
        self._rule_name = self.name_edit.text().strip()

        # Accept the dialog
        self.accept()

    def get_final_regex(self) -> str:
        """Get the final regex pattern based on current mode."""
        # If annotate pattern was generated, use that; otherwise use tokens
        if self._mode == "annotate" and self._smart_pattern:
            return self._smart_pattern
        return TokenEngine.compile(self.drop_zone.get_tokens())

    def get_rule_name(self) -> str:
        """Get the user-provided rule name."""
        return self._rule_name
