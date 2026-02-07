# -*- coding: utf-8 -*-
"""Ramses Naming Architect — Visual rule-building engine.

This module converts a sequence of visual tokens into a valid NamingRule (regex).
It also provides the core simulation logic for the 'Live Lab'.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QFont, QColor, QDrag, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QScrollArea, QDialog,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QMenu, QCheckBox, QSpinBox, QTextEdit
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
    padding: int = 0 # For digits (e.g. 3 -> \d{3})
    prefix: str = "" # e.g. "v" for version
    is_uppercase: bool = False
    is_required: bool = True

    def to_regex(self) -> str:
        """Convert this token into a Python Regex fragment."""
        if self.type == TokenType.SEPARATOR:
            return re.escape(self.value)
        
        # Build the capture group logic
        pattern = ""
        if self.type == TokenType.VERSION:
            if self.prefix:
                pattern += re.escape(self.prefix)
            pattern += r"\d+" if self.padding <= 0 else fr"\d{{{self.padding}}}"
        elif self.type == TokenType.SHOT or self.type == TokenType.SEQUENCE:
            # Common pattern: alphanumeric but must contain a digit
            pattern = r"[A-Za-z0-9]+"
        elif self.type == TokenType.WILDCARD:
            pattern = r".*?"
        elif self.type == TokenType.IGNORE:
            return r".*?"
        else:
            pattern = r"[A-Za-z0-9]+"

        if self.type in [TokenType.SEQUENCE, TokenType.SHOT, TokenType.VERSION, TokenType.STEP, TokenType.PROJECT]:
            return f"(?P<{self.type.value}>{pattern})"
        
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
        best_sep = max(sep_counts, key=sep_counts.get) if any(sep_counts.values()) else "_"
        
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
                    ttype = TokenType.SHOT # Fallback for alpha shots
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

            guessed_tokens.append(ArchitectToken(type=ttype, padding=padding, prefix=prefix))
            if i < n_parts - 1:
                guessed_tokens.append(ArchitectToken(type=TokenType.SEPARATOR, value=best_sep))

        return guessed_tokens


# ---------------------------------------------------------------------------
# UI Components
# ---------------------------------------------------------------------------

class VisualTokenWidget(QFrame):
    """A pill-shaped interactive token in the rule builder."""
    
    clicked = Signal(ArchitectToken)
    deleted = Signal(object)

    def __init__(self, token: ArchitectToken, parent=None) -> None:
        super().__init__(parent)
        self.token = token
        self._setup_layout()
        self.apply_base_style()

    def _setup_layout(self) -> None:
        """Create the layout and internal widgets once."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        
        label_text = self.token.type.name.capitalize()
        if self.token.type == TokenType.SEPARATOR:
            label_text = f"'{self.token.value}'"
        
        self.label = QLabel(label_text)
        self.label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        layout.addWidget(self.label)

    def apply_base_style(self, border_color: str = "rgba(255,255,255,0.1)") -> None:
        """Apply the visual theme without re-creating layout."""
        colors = {
            TokenType.SEQUENCE: "#27ae60",
            TokenType.SHOT: "#2980b9",
            TokenType.VERSION: "#f39c12",
            TokenType.SEPARATOR: "#7f8c8d",
            TokenType.WILDCARD: "#8e44ad",
            TokenType.IGNORE: "#34495e",
        }
        bg = colors.get(self.token.type, "#333")
        
        self.setStyleSheet(f"""
            VisualTokenWidget {{
                background-color: {bg};
                border-radius: 12px;
                border: 1px solid {border_color};
                color: white;
            }}
            VisualTokenWidget:hover {{
                border: 1px solid white;
            }}
        """)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self.clicked.emit(self.token)
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
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
        self.setMinimumHeight(80) # Stabilize height
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("background-color: #1a1a1a; border: 1px dashed #333; border-radius: 6px;")
        
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
                w2 = widgets[i+1]
                # If both are capture groups (not separators/ignore) they clash
                if (w1.token.type not in [TokenType.SEPARATOR, TokenType.IGNORE] and 
                    w2.token.type not in [TokenType.SEPARATOR, TokenType.IGNORE]):
                    clash = True
            
            if clash:
                w1.setStyleSheet(w1.styleSheet() + "VisualTokenWidget { border: 2px solid #f44747; }")
                w1.setToolTip("Collision Risk: Add a separator to prevent greedy matching.")
            else:
                # Reset to normal using the new styling method
                w1.apply_base_style() 
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
            source_id = int(event.mimeData().data("application/x-ramses-token").data().decode())
            
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
            target_idx = self.layout.count() - 1 # Default to before the stretch
            
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
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setStyleSheet("background-color: #1a1a1a; color: #ccc; gridline-color: #333;")
        self.verticalHeader().setVisible(False)

    def refresh(self, samples: list[str], tokens: list[ArchitectToken]) -> None:
        self.setRowCount(len(samples))
        import os
        
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
                            temp_text[:start] + 
                            f'<span style="color:{color}; font-weight:bold;">{snippet}</span>' + 
                            temp_text[end:]
                        )
                xray_html = temp_text

            # --- Table Items ---
            lbl = QLabel(f'<html><body style="font-family:Consolas, monospace; font-size:11px;">{xray_html}</body></html>')
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
        self.setStyleSheet("background-color: #252526; border-left: 1px solid #333; padding: 10px;")
        
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
        self.pad_box.setVisible(token.type in [TokenType.VERSION, TokenType.SHOT, TokenType.SEQUENCE])
        
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


class NamingArchitectDialog(QDialog):
    """The professional 'Slide-over' style rule builder."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ramses Naming Architect")
        self.resize(1100, 650)
        self._samples = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar: Vendor Presets ---
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(180)
        self.sidebar.setStyleSheet("background-color: #252526; border-right: 1px solid #333;")
        side_lay = QVBoxLayout(self.sidebar)
        
        lbl_side = QLabel("VENDOR PRESETS")
        lbl_side.setStyleSheet("color: #888; font-weight: bold; font-size: 10px; margin-bottom: 5px;")
        side_lay.addWidget(lbl_side)
        
        presets = [
            ("Standard Shot", [TokenType.SEQUENCE, "_", TokenType.SHOT]),
            ("Shot & Version", [TokenType.SEQUENCE, "_", TokenType.SHOT, "_", TokenType.VERSION]),
            ("Technicolor", [TokenType.PROJECT, "_", TokenType.SEQUENCE, "_", TokenType.SHOT]),
            ("Flat Delivery", [TokenType.SHOT]),
        ]
        
        for name, pattern in presets:
            btn = QPushButton(name)
            btn.setStyleSheet("text-align: left; padding: 8px; border: none; background: transparent;")
            # Use default value in lambda to capture current pattern
            btn.clicked.connect(lambda checked=False, p=pattern: self._apply_preset(p))
            side_lay.addWidget(btn)
        
        side_lay.addStretch()
        main_layout.addWidget(self.sidebar)

        # --- Content Area ---
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        main_layout.addWidget(content, 1)

        # 1. Blueprint Area (with Inspector side-panel)
        lbl_blue = QLabel("interactive rule blueprint")
        lbl_blue.setStyleSheet("color: #888; text-transform: uppercase; font-size: 10px; font-weight: bold;")
        layout.addWidget(lbl_blue)
        
        blueprint_cont = QHBoxLayout()
        self.drop_zone = TokenDropZone()
        self.drop_zone.changed.connect(self._on_rule_changed)
        blueprint_cont.addWidget(self.drop_zone, 1)
        
        self.inspector = TokenInspector()
        self.inspector.changed.connect(self._on_rule_changed)
        self.drop_zone.token_clicked.connect(self.inspector.inspect)
        blueprint_cont.addWidget(self.inspector)
        
        layout.addLayout(blueprint_cont)

        # Token Ribbon (Available Tokens)
        ribbon = QHBoxLayout()
        for ttype in [TokenType.SEQUENCE, TokenType.SHOT, TokenType.VERSION, TokenType.IGNORE]:
            btn = QPushButton(f"+ {ttype.name}")
            btn.clicked.connect(lambda checked=False, tt=ttype: self._add_token(tt))
            ribbon.addWidget(btn)
        
        btn_sep = QPushButton("+ Separator")
        btn_sep.clicked.connect(self._add_separator)
        ribbon.addWidget(btn_sep)
        
        ribbon.addSpacing(20)
        self.btn_magic = QPushButton("✨ Magic Wand")
        self.btn_magic.setStyleSheet("background-color: #4a4a4a; color: #4ec9b0; font-weight: bold;")
        self.btn_magic.clicked.connect(self._on_magic_wand)
        self.btn_magic.setEnabled(False)
        ribbon.addWidget(self.btn_magic)
        
        ribbon.addStretch()
        layout.addLayout(ribbon)

        # 2. Main Lab Area
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Top: Sample Input
        input_box = QWidget()
        in_lay = QVBoxLayout(input_box)
        in_lay.setContentsMargins(0, 10, 0, 0)
        lbl_in = QLabel("Sample Filenames (Paste one per line)")
        lbl_in.setStyleSheet("color: #888; font-size: 11px;")
        in_lay.addWidget(lbl_in)
        
        self.sample_edit = QTextEdit()
        self.sample_edit.setPlaceholderText("shot_010_v001.exr\nshot_020_v001.exr...")
        self.sample_edit.textChanged.connect(self._on_samples_changed)
        in_lay.addWidget(self.sample_edit)
        splitter.addWidget(input_box)

        # Bottom: Results
        res_box = QWidget()
        res_lay = QVBoxLayout(res_box)
        res_lay.setContentsMargins(0, 10, 0, 0)
        lbl_res = QLabel("Live Simulation Lab")
        lbl_res.setStyleSheet("color: #888; font-size: 11px;")
        res_lay.addWidget(lbl_res)
        
        self.sim_table = SimulationTable()
        res_lay.addWidget(self.sim_table)
        splitter.addWidget(res_box)
        
        layout.addWidget(splitter, 1)

        # 3. Footer Area (Developer View)
        self.regex_label = QLabel("Generated Regex: —")
        self.regex_label.setStyleSheet("font-family: 'Consolas'; color: #555; font-size: 11px;")
        layout.addWidget(self.regex_label)

        # Action Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        
        btn_apply = QPushButton("Apply to Project")
        btn_apply.setStyleSheet("background-color: #0e639c; color: white; font-weight: bold;")
        btn_apply.clicked.connect(self.accept)
        btns.addWidget(btn_apply)
        layout.addLayout(btns)

    def _apply_preset(self, pattern: list[TokenType | str]) -> None:
        """Apply a predefined pattern to the blueprint."""
        self.drop_zone.clear()
        for item in pattern:
            if isinstance(item, str):
                self.drop_zone.add_token(ArchitectToken(type=TokenType.SEPARATOR, value=item))
            else:
                self.drop_zone.add_token(ArchitectToken(type=item))
        self._on_rule_changed()

    def _add_token(self, ttype: TokenType) -> None:
        self.drop_zone.add_token(ArchitectToken(type=ttype))

    def _add_separator(self) -> None:
        # For now, just add an underscore as default
        self.drop_zone.add_token(ArchitectToken(type=TokenType.SEPARATOR, value="_"))

    def _on_samples_changed(self) -> None:
        text = self.sample_edit.toPlainText()
        self._samples = [line.strip() for line in text.splitlines() if line.strip()]
        self.btn_magic.setEnabled(len(self._samples) > 0)
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

    def _on_rule_changed(self) -> None:
        tokens = self.drop_zone.get_tokens()
        pattern = TokenEngine.compile(tokens)
        self.regex_label.setText(f"Generated Regex: {pattern}")
        self.sim_table.refresh(self._samples, tokens)

    def get_final_regex(self) -> str:
        return TokenEngine.compile(self.drop_zone.get_tokens())
