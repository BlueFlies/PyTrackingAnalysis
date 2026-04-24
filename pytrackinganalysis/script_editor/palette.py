"""Script-editor palette: a searchable, category-grouped action library.

Renders the registered actions as clickable tiles. Double-clicking a tile
(or pressing Enter while it's selected) emits :pyattr:`actionActivated`
with the action key; the parent window appends a new step to the canvas.
"""

from __future__ import annotations

from collections import defaultdict

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..ui import Category, category_color, icon
from .actions import ACTIONS, Action


class _ActionTile(QFrame):
    """A single clickable tile representing one action."""

    activated = pyqtSignal(str)

    def __init__(self, action: Action, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._action = action
        self.setObjectName("PtrackScriptTile")
        self.setMinimumHeight(56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        col = category_color(action.category)
        self.setStyleSheet(
            f"QFrame#PtrackScriptTile {{"
            f"  border-left: 3px solid {col};"
            f"  border-radius: 6px;"
            f"  padding: 2px;"
            f"  background: palette(base);"
            f"}}"
            f"QFrame#PtrackScriptTile:hover {{ background: palette(midlight); }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)

        ico = QLabel()
        ico.setPixmap(icon(action.icon_name, category=action.category).pixmap(22, 22))
        ico.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(ico)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel(action.title)
        title.setStyleSheet("font-weight: 600;")
        title.setWordWrap(True)
        desc = QLabel(action.description)
        desc.setStyleSheet("color: palette(mid); font-size: 9pt;")
        desc.setWordWrap(True)
        text_col.addWidget(title)
        text_col.addWidget(desc)
        lay.addLayout(text_col, 1)

    def mouseDoubleClickEvent(self, _event) -> None:  # noqa: N802
        self.activated.emit(self._action.key)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit(self._action.key)
            return
        super().keyPressEvent(event)


class Palette(QWidget):
    """Left pane: search box + list of tiles, grouped by category."""

    actionActivated = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search actions…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        outer.addWidget(self._search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        host = QWidget()
        self._list_layout = QVBoxLayout(host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        self._tiles: list[_ActionTile] = []
        self._section_headers: list[tuple[Category, QLabel]] = []
        self._build_tiles()

    def _build_tiles(self) -> None:
        # Group actions by category, preserving the order categories appear
        # in the Category enum.
        by_cat: dict[Category, list[Action]] = defaultdict(list)
        for action in ACTIONS.values():
            by_cat[action.category].append(action)

        for cat in Category:
            group = by_cat.get(cat)
            if not group:
                continue
            header = QLabel(cat.value.upper())
            header.setStyleSheet(
                f"color: {category_color(cat)}; "
                f"font-weight: 700; font-size: 10pt; "
                f"letter-spacing: 0.08em; padding-top: 6px;"
            )
            self._section_headers.append((cat, header))
            self._list_layout.addWidget(header)
            for action in group:
                tile = _ActionTile(action)
                tile.activated.connect(self.actionActivated.emit)
                tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self._list_layout.addWidget(tile)
                self._tiles.append(tile)
        self._list_layout.addStretch(1)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        any_visible: dict[Category, bool] = defaultdict(bool)
        for tile in self._tiles:
            action: Action = tile._action  # noqa: SLF001
            match = (
                not needle
                or needle in action.title.lower()
                or needle in action.description.lower()
                or needle in action.key.lower()
            )
            tile.setVisible(match)
            if match:
                any_visible[action.category] = True
        for cat, header in self._section_headers:
            header.setVisible(any_visible.get(cat, False))
