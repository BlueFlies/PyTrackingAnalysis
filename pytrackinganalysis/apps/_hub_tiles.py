"""Tile strip widgets for the Analysis Hub (ADR-0007).

A :class:`StatusTile` is a compact, clickable live-status chip in the strip
across the top of the Hub; all of a tile's controls live in its
:class:`TilePanel` — an anchored overlay that drops down under the tile,
hosting the full existing Card widgets. Panels are persistent hidden children
of the Hub's central widget (state survives open/close; ``findChildren``
keeps working for tests), one open at a time. A panel closes when its own tile
is clicked again, when another tile takes its place, on a click anywhere in the
background, or on Esc — a running task leaves it alone.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..ui import Category, category_color, icon, resolved_mode


def chrome_colors() -> dict:
    """Surface colors for the strip, tiles, and panels — one source of truth
    with the app theme (see ``ui.theme.surface_colors``)."""
    from ..ui.theme import surface_colors

    c = surface_colors()
    return {"band": c["band"], "chip": c["base"], "border": c["border"],
            "hover": c["hover"], "text": c["text"], "muted": c["muted"]}


class StatusTile(QFrame):
    """One strip tile: icon + title row and up to two live summary lines.

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
        #: (left, right) corner radii. With hairline seams between chips a
        #: gentle radius keeps the seams from flaring near the corners.
        self._radii = (5, 5)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        ## A width RANGE, not a fixed size: six fixed 196px tiles forced a
        ## 1416px minimum window that no 1366x768 laptop could show.
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(118)
        self.setMaximumWidth(196)
        self.setFixedHeight(84)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(6)
        self._icon = icon(icon_name)
        self._icon_lbl = QLabel()
        head.addWidget(self._icon_lbl)
        self._title_lbl = QLabel(title.upper())
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
        full = [str(line) for line in lines]
        clipped = []
        for line in full[:2]:
            if len(line) > self._MAX_LINE_CHARS:
                line = line[: self._MAX_LINE_CHARS - 1] + "…"
            clipped.append(line)
        self._summary_lbl.setText("\n".join(clipped))
        ## The untruncated summary is always one hover away.
        self.setToolTip("\n".join(full))

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

    def set_rounding(self, left: int, right: int) -> None:
        """Round only these corners (px) — the strip's outer ends keep the
        radius; interior edges sit flush."""
        self._radii = (left, right)
        self._restyle()

    def restyle(self) -> None:
        """Public re-skin hook — the Hub calls it on theme toggles."""
        self._restyle()

    def _restyle(self) -> None:
        chrome = chrome_colors()
        color = category_color(self._category)
        ## Chips with a hairline seam and a thin outline (user feedback
        ## 2026-08-22); the open panel's tile upgrades it to its category
        ## color. An inapplicable tile keeps the outline — dimming must not
        ## cost it its edge, or the strip loses its shape.
        border = f"2px solid {color}" if self._active \
            else f"1px solid {chrome['border']}"
        left, right = self._radii
        if self._dimmed:
            ## Dimmed tiles recede toward the window behind the strip, with
            ## every element muted together — the title, the summary, and the
            ## icon (user feedback 2026-08-24, superseding the 2026-08-22
            ## "titles always wear their category color"). Words alone said
            ## it too quietly: seven equally bright chips read as seven
            ## equally available ones.
            background, title, pop = chrome["band"], chrome["muted"], chrome["muted"]
        else:
            background, title = chrome["hover"], color
            ## Uniform, high-contrast subtext on a live tile: pure white or
            ## black by theme.
            pop = "#ffffff" if resolved_mode() == "dark" else "#000000"
        self.setStyleSheet(
            f"StatusTile {{ background: {background}; "
            f"border: {border}; "
            f"border-top-left-radius: {left}px; "
            f"border-bottom-left-radius: {left}px; "
            f"border-top-right-radius: {right}px; "
            f"border-bottom-right-radius: {right}px; }} "
            f"QLabel {{ color: {pop}; background: transparent; "
            "border: none; }")
        self._title_lbl.setStyleSheet(
            f"color: {title}; font-weight: 700; font-size: 9pt; "
            "letter-spacing: 0.06em;")
        mode = QIcon.Mode.Disabled if self._dimmed else QIcon.Mode.Normal
        self._icon_lbl.setPixmap(self._icon.pixmap(QSize(16, 16), mode))

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class StatusPanel(QFrame):
    """The strip's right-hand readout: what is open right now.

    Not a tile — it opens nothing and is never dimmed. It fills the strip's
    leftover width so the Hub can always answer "which project, and which
    experiment inside it?" without opening a panel first.
    """

    #: Kept to the tile height so the strip stays one band.
    _HEIGHT = 84
    _MAX_ROWS = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._HEIGHT)
        self.setMinimumWidth(160)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(0)
        self._label = QLabel("")
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._label, 1, Qt.AlignmentFlag.AlignTop)
        self._plain = ""
        self.restyle()

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        """Render ``(label, value)`` pairs, one per line. Extra rows go to the
        tooltip rather than growing the strip."""
        import html as _html

        chrome = chrome_colors()
        shown = rows[: self._MAX_ROWS]
        parts = []
        for label, value in shown:
            lab = _html.escape(str(label))
            val = _html.escape(str(value))
            parts.append(
                f"<div style='margin:0'>"
                f"<span style='color:{chrome['muted']}'>{lab}:</span> "
                f"{val}</div>")
        self._label.setText("".join(parts))
        self._plain = "\n".join(f"{lab}: {val}" for lab, val in rows)
        self.setToolTip(self._plain)

    def status_text(self) -> str:
        """The rendered rows as plain text (every row, not just the shown)."""
        return self._plain

    def restyle(self) -> None:
        chrome = chrome_colors()
        ## A chip like the tiles: same radius, same thin outline, same
        ## high-contrast value text.
        pop = "#ffffff" if resolved_mode() == "dark" else "#000000"
        self.setStyleSheet(
            f"QFrame#StatusPanel {{ background: {chrome['hover']}; "
            f"border: 1px solid {chrome['border']}; border-radius: 5px; }} "
            f"QLabel {{ color: {pop}; background: transparent; "
            "border: none; font-size: 9pt; }")


class TilePanel(QFrame):
    """The anchored overlay under a tile: a framed, scrollable host for the
    full Card widgets. Created once, shown/hidden — never destroyed."""

    def __init__(self, key: str, width: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._panel_width = width
        self.setObjectName("TilePanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.restyle()

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

    def restyle(self) -> None:
        chrome = chrome_colors()
        self.setStyleSheet(
            f"QFrame#TilePanel {{ background: {chrome['band']}; "
            f"border: 1px solid {chrome['border']}; border-radius: 10px; }}")

    def add_card(self, card: QWidget) -> None:
        """Reparent an existing Card into this panel (its handlers, child
        widgets, and findChildren-visibility all come along)."""
        self._content_lay.addWidget(card)
        card.setVisible(True)

    def finish(self) -> None:
        self._content_lay.addStretch(1)

    def _content_height(self) -> int:
        """Height the panel needs to show its cards without scrolling.

        Qt defers geometry updates for hidden widgets, so cards rebuilt while
        the panel was closed (e.g. the plot buttons after an experiment load)
        leave stale cached hints in every layout above them: the host layout
        kept reporting the pre-rebuild height, and the panel opened far too
        short, with a scrollbar. Walk the subtree — ``updateGeometry`` on each
        widget, ``invalidate`` on each layout — so the measurement below sees
        the content as it is now.
        """
        host = self._scroll.widget()
        for lay in host.findChildren(QLayout):
            lay.invalidate()
        for child in host.findChildren(QWidget):
            child.updateGeometry()
        outer = self.layout()
        if host.layout() is not None:
            host.layout().invalidate()
            host.layout().activate()
        margins = outer.contentsMargins()
        ## Chrome the content does not get: the panel's own frame, the scroll
        ## area's frame, and the outer layout's margins.
        return (host.sizeHint().height() + margins.top() + margins.bottom()
                + 2 * self._scroll.frameWidth() + 2 * self.frameWidth())

    def open_at(self, x: int, y: int, max_bottom: int) -> None:
        """Show anchored at (*x*, *y*) in parent coordinates, clamped so the
        panel never runs past *max_bottom* or the parent's right edge."""
        parent = self.parentWidget()
        width = min(self._panel_width, parent.width() - 16)
        available_height = max(0, max_bottom - y)
        height = min(self._content_height(), available_height)
        if available_height >= 120:
            height = max(120, height)
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
