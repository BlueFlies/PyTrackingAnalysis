"""Tile strip widgets for the Analysis Hub (ADR-0007).

A :class:`StatusTile` is a compact, clickable live-status chip in the strip
across the top of the Hub; all of a tile's controls live in its
:class:`TilePanel` — an anchored overlay that drops down under the tile,
hosting the full existing Card widgets. Panels are persistent hidden children
of the Hub's central widget (state survives open/close; ``findChildren``
keeps working for tests), one open at a time, closed by Esc, click-away, or
a background task starting.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..ui import Category, category_color, icon


class StatusTile(QFrame):
    """One strip tile: icon + title row and up to three live summary lines.

    Tiles never hide or move (ADR-0007): an inapplicable tile is *dimmed*
    but stays clickable — its panel holds the control that fixes the
    missing state.
    """

    clicked = pyqtSignal(str)

    #: Hard cap so a chatty summary can never widen the strip.
    _MAX_LINE_CHARS = 26

    def __init__(self, key: str, title: str, icon_name: str,
                 category: Category, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._category = category
        self._dimmed = False
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(196, 84)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(6)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(icon(icon_name).pixmap(QSize(16, 16)))
        head.addWidget(icon_lbl)
        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setStyleSheet(
            f"color: {category_color(category)}; font-weight: 700; "
            "font-size: 9pt; letter-spacing: 0.06em;")
        head.addWidget(self._title_lbl)
        head.addStretch(1)
        lay.addLayout(head)

        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet("font-size: 9pt;")
        self._summary_lbl.setTextFormat(Qt.TextFormat.PlainText)
        lay.addWidget(self._summary_lbl, 1,
                      Qt.AlignmentFlag.AlignTop)
        self._restyle()

    # ------------------------------------------------------------------

    def set_summary(self, lines: list[str]) -> None:
        clipped = []
        for line in lines[:2]:
            line = str(line)
            if len(line) > self._MAX_LINE_CHARS:
                line = line[: self._MAX_LINE_CHARS - 1] + "…"
            clipped.append(line)
        self._summary_lbl.setText("\n".join(clipped))

    def summary_text(self) -> str:
        return self._summary_lbl.text()

    def set_dimmed(self, dimmed: bool) -> None:
        if dimmed != self._dimmed:
            self._dimmed = dimmed
            self._restyle()

    def is_dimmed(self) -> bool:
        return self._dimmed

    def set_active(self, active: bool) -> None:
        if active != self._active:
            self._active = active
            self._restyle()

    def _restyle(self) -> None:
        color = category_color(self._category)
        border = f"2px solid {color}" if self._active \
            else "1px solid palette(mid)"
        text = "palette(mid)" if self._dimmed else "palette(text)"
        self.setStyleSheet(
            "StatusTile { background: palette(base); "
            f"border: {border}; border-radius: 8px; }} "
            f"QLabel {{ color: {text}; background: transparent; "
            "border: none; }")
        # The title keeps its category color even when dimmed-ish.
        self._title_lbl.setStyleSheet(
            f"color: {color}; font-weight: 700; font-size: 9pt; "
            "letter-spacing: 0.06em;"
            + ("opacity: 0.5;" if self._dimmed else ""))

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class TilePanel(QFrame):
    """The anchored overlay under a tile: a framed, scrollable host for the
    full Card widgets. Created once, shown/hidden — never destroyed."""

    def __init__(self, key: str, width: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._panel_width = width
        self.setObjectName("TilePanel")
        self.setStyleSheet(
            "QFrame#TilePanel { background: palette(window); "
            "border: 1px solid palette(mid); border-radius: 10px; }")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        self._content_lay = QVBoxLayout(host)
        self._content_lay.setContentsMargins(8, 8, 8, 8)
        self._content_lay.setSpacing(12)
        self._scroll.setWidget(host)
        outer.addWidget(self._scroll)
        self.hide()

    def add_card(self, card: QWidget) -> None:
        """Reparent an existing Card into this panel (its handlers, child
        widgets, and findChildren-visibility all come along)."""
        self._content_lay.addWidget(card)
        card.setVisible(True)

    def finish(self) -> None:
        self._content_lay.addStretch(1)

    def open_at(self, x: int, y: int, max_bottom: int) -> None:
        """Show anchored at (*x*, *y*) in parent coordinates, clamped so the
        panel never runs past *max_bottom* or the parent's right edge."""
        parent = self.parentWidget()
        width = min(self._panel_width, parent.width() - 16)
        hint = self._scroll.widget().sizeHint().height() + 24
        height = max(120, min(hint, max_bottom - y - 8))
        x = max(8, min(x, parent.width() - width - 8))
        self.setGeometry(x, y, width, height)
        self.raise_()
        self.show()


class ClickAwayFilter(QObject):
    """App-level filter that ONLY forwards GUI-thread mouse presses.

    Installing a QWidget itself as an application event filter is fatal:
    application filters run in the receiving object's thread, so worker-
    thread events would call into GUI-widget machinery off-thread (observed
    as a hard Qt abort). This plain QObject early-outs on everything except
    a main-thread MouseButtonPress and never swallows the event."""

    def __init__(self, owner) -> None:
        super().__init__(owner)   # parented: auto-removed when owner dies
        self._owner = owner

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt override)
        try:
            if event.type() == QEvent.Type.MouseButtonPress \
                    and QThread.currentThread() is self.thread():
                self._owner._handle_click_away(event)
        except RuntimeError:
            pass  # owner already destroyed
        return False
