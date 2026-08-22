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
    QGridLayout,
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
        # Background/hover/description colors come from the app-wide theme
        # QSS (ui/theme.py) so they track light/dark toggles; only the
        # per-category accent is set here.
        self.setStyleSheet(
            f"QFrame#PtrackScriptTile {{"
            f"  border-left: 3px solid {col};"
            f"  border-radius: 6px;"
            f"  padding: 2px;"
            f"}}"
        )

        ## A GRID, not an HBox wrapping a nested VBox. A QBoxLayout sizes a
        ## nested layout on its CROSS axis from that layout's sizeHint and
        ## centres it, ignoring height-for-width however the labels are
        ## configured — which clipped the wrapped description top and bottom.
        ## A grid gives each row the height its own cell actually needs.
        lay = QGridLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setHorizontalSpacing(10)
        lay.setVerticalSpacing(2)

        ico = QLabel()
        ico.setPixmap(icon(action.icon_name, category=action.category).pixmap(22, 22))
        ico.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(ico, 0, 0, 2, 1, Qt.AlignmentFlag.AlignTop)

        title = QLabel(action.title)
        title.setStyleSheet("font-weight: 600;")
        title.setWordWrap(True)
        desc = QLabel(action.description)
        desc.setObjectName("PtrackScriptTileDesc")
        desc.setWordWrap(True)
        for label in (title, desc):
            ## A word-wrapped QLabel implements heightForWidth, but its
            ## DEFAULT size policy leaves the flag off, so enclosing layouts
            ## never ask — they lay it out at a one-line-ish sizeHint and the
            ## wrapped text is clipped.
            policy = label.sizePolicy()
            policy.setHeightForWidth(True)
            label.setSizePolicy(policy)
        lay.addWidget(title, 0, 1)
        lay.addWidget(desc, 1, 1)
        lay.setColumnStretch(1, 1)
        self._title_lbl = title
        self._desc_lbl = desc

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_to_contents()

    def _fit_to_contents(self) -> None:
        """Give each label the height its wrapped text needs, then make the
        tile tall enough to hold both.

        Qt will not do this for us. A word-wrapped QLabel knows its
        ``heightForWidth``, but neither a QBoxLayout (which sizes a nested
        layout from its cross-axis sizeHint and centres it) nor a QGridLayout
        row reliably applies that when assigning geometry — the description
        was laid out at a one-line-ish sizeHint and clipped top and bottom.
        Measuring each label at the width it actually got, and pinning both
        it and the tile, sidesteps the layout's opinion entirely.
        """
        lay = self.layout()
        if lay is None:
            return
        lay.activate()                       # so the widths below are current
        if self.contentsRect().width() <= 0:
            return
        for label in (self._title_lbl, self._desc_lbl):
            width = label.width()
            if width <= 0:
                continue
            need = label.heightForWidth(width)
            if need > 0 and label.height() != need:
                label.setFixedHeight(need)
        margins = lay.contentsMargins()
        # The QSS border and padding live outside contentsRect, so the layout
        # gets less room than the tile is tall; carry that difference over.
        overhead = self.height() - self.contentsRect().height()
        needed = (margins.top() + margins.bottom() + lay.verticalSpacing()
                  + self._title_lbl.height() + self._desc_lbl.height()
                  + overhead)
        height = max(56, needed)
        if height != self.height():
            self.setFixedHeight(height)

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
        self._experiment_type: str | None = None
        self._actions: dict[str, Action] = ACTIONS
        self._build_tiles()

    def set_actions(self, actions: dict[str, Action]) -> None:
        """Swap the registry the palette shows (project vs experiment level)
        and rebuild the tiles."""
        if actions is self._actions:
            return
        self._actions = actions
        for tile in self._tiles:
            tile.setParent(None)
        for _cat, header in self._section_headers:
            header.setParent(None)
        self._tiles.clear()
        self._section_headers.clear()
        # Drop the trailing stretch added by the previous build.
        while self._list_layout.count():
            item = self._list_layout.takeAt(self._list_layout.count() - 1)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._build_tiles()
        self._apply_filter(self._search.text())

    def set_experiment_type(self, exp_type: str | None) -> None:
        """Limit the visible tiles to actions applicable to *exp_type*."""
        self._experiment_type = exp_type
        # Re-apply current filter (search + type) on the existing tiles.
        self._apply_filter(self._search.text())

    def _build_tiles(self) -> None:
        # Group actions by category, preserving the order categories appear
        # in the Category enum.
        by_cat: dict[Category, list[Action]] = defaultdict(list)
        for action in self._actions.values():
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
                # Vertical size is pinned by the tile's resizeEvent.
                tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self._list_layout.addWidget(tile)
                self._tiles.append(tile)
        self._list_layout.addStretch(1)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        any_visible: dict[Category, bool] = defaultdict(bool)
        for tile in self._tiles:
            action: Action = tile._action  # noqa: SLF001
            applies = action.applies_to(self._experiment_type)
            text_match = (
                not needle
                or needle in action.title.lower()
                or needle in action.description.lower()
                or needle in action.key.lower()
            )
            visible = applies and text_match
            tile.setVisible(visible)
            if visible:
                any_visible[action.category] = True
        for cat, header in self._section_headers:
            header.setVisible(any_visible.get(cat, False))
