"""Reusable themed widgets shared across the PyTrackingAnalysis Qt apps.

Vendored from pyflic's ``base/ui/widgets.py`` with ``Pyflic*`` objectNames
renamed to ``Ptrack*`` so the vendored QSS rules are namespaced.

* :class:`SidebarNav`  — vertical navigation rail with category-tinted items
* :class:`TopBar`      — app title + arbitrary right-aligned controls
* :class:`Card`        — rounded panel with title, optional subtitle, and a body layout
* :class:`ActionButton`— QPushButton with category-coloured left border + icon
* :class:`PlotDock`    — tabbed interactive plot dock (matplotlib + nav toolbar)
* :class:`OutputLog`   — monospaced log panel that grows scrollback
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPalette, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .icons import icon
from .theme import Category, category_color, resolved_mode


# ---------------------------------------------------------------------------
# Sidebar navigation rail
# ---------------------------------------------------------------------------

class SidebarNav(QWidget):
    """Vertical navigation rail.

    Items emit :pyattr:`itemSelected` with the item's *key*.  Use
    :meth:`add_item` to register entries; the first added item is selected
    by default.
    """

    itemSelected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None, *, width: int = 180) -> None:
        super().__init__(parent)
        self.setObjectName("PtrackSidebar")
        self.setFixedWidth(width)
        self.setAutoFillBackground(True)
        pal = self.palette()
        bg = pal.color(QPalette.ColorRole.Window).darker(105) \
            if resolved_mode() == "light" \
            else pal.color(QPalette.ColorRole.Window).lighter(110)
        pal.setColor(QPalette.ColorRole.Window, bg)
        self.setPalette(pal)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 12, 8, 12)
        self._lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}

    def add_item(
        self,
        key: str,
        label: str,
        icon_name: str,
        *,
        category: Category | None = None,
        tooltip: str | None = None,
    ) -> QPushButton:
        btn = QPushButton(label, self)
        btn.setObjectName("PtrackSidebarItem")
        btn.setCheckable(True)
        btn.setIcon(icon(icon_name, category=category))
        btn.setIconSize(QSize(16, 16))
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda _checked, k=key: self.itemSelected.emit(k))
        self._lay.addWidget(btn)
        self._group.addButton(btn)
        self._buttons[key] = btn
        if len(self._buttons) == 1:
            btn.setChecked(True)
        return btn

    def add_action(
        self,
        label: str,
        icon_name: str,
        *,
        category: Category | None = None,
        tooltip: str | None = None,
    ) -> QPushButton:
        """Add a plain action button to the rail (not a checkable nav anchor).

        Unlike :meth:`add_item`, this is not part of the exclusive selection
        group and does not scroll to a card — the caller connects ``clicked`` to
        whatever it should do. Useful for a rail entry that acts like a button.
        """
        btn = QPushButton(label, self)
        btn.setObjectName("PtrackSidebarItem")
        btn.setIcon(icon(icon_name, category=category))
        btn.setIconSize(QSize(16, 16))
        if tooltip:
            btn.setToolTip(tooltip)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._lay.addWidget(btn)
        return btn

    def add_separator(self) -> None:
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        self._lay.addWidget(line)

    def add_stretch(self) -> None:
        self._lay.addStretch(1)

    def select(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setChecked(True)
            self.itemSelected.emit(key)


# ---------------------------------------------------------------------------
# Top bar
# ---------------------------------------------------------------------------

class TopBar(QFrame):
    """Slim top bar with an app title on the left and slots on the right."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PtrackTopBar")
        self.setFixedHeight(56)
        self.setFrameShape(QFrame.Shape.NoFrame)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 12, 6)
        lay.setSpacing(10)

        self._title = QLabel(title, self)
        self._title.setObjectName("PtrackAppTitle")
        lay.addWidget(self._title)

        lay.addStretch(1)

        self._right_lay = QHBoxLayout()
        self._right_lay.setContentsMargins(0, 0, 0, 0)
        self._right_lay.setSpacing(8)
        right_host = QWidget(self)
        right_host.setLayout(self._right_lay)
        lay.addWidget(right_host)

    def add_right(self, widget: QWidget) -> None:
        self._right_lay.addWidget(widget)

    def set_title(self, title: str) -> None:
        self._title.setText(title)


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

class Card(QFrame):
    """Rounded panel with a category-tinted left border + title row."""

    def __init__(
        self,
        title: str,
        category: Category = Category.NEUTRAL,
        subtitle: str | None = None,
        icon_name: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PtrackCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._category = category

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        if icon_name is not None:
            ico = QLabel(self)
            ico.setPixmap(icon(icon_name, category=category).pixmap(20, 20))
            title_row.addWidget(ico)

        self._title_lbl = QLabel(title, self)
        self._title_lbl.setObjectName("PtrackCardTitle")
        self._title_lbl.setStyleSheet(
            f"QLabel#PtrackCardTitle {{ "
            f"  border-left: 4px solid {category_color(category)};"
            f"  padding-left: 8px;"
            f"}}"
        )
        title_row.addWidget(self._title_lbl, 1)
        self._title_row = title_row

        outer.addLayout(title_row)

        if subtitle:
            sub = QLabel(subtitle, self)
            sub.setObjectName("PtrackCardSubtitle")
            sub.setWordWrap(True)
            outer.addWidget(sub)

        self._body = QVBoxLayout()
        self._body.setSpacing(8)
        outer.addLayout(self._body)

        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Base)
        bg = base.lighter(102) if resolved_mode() == "light" else base.lighter(115)
        pal.setColor(QPalette.ColorRole.Window, bg)
        self.setAutoFillBackground(True)
        self.setPalette(pal)

    def body_layout(self) -> QVBoxLayout:
        return self._body

    def add_body(self, widget_or_layout: QWidget | Any) -> None:
        if isinstance(widget_or_layout, QWidget):
            self._body.addWidget(widget_or_layout)
        else:
            self._body.addLayout(widget_or_layout)

    def set_title(self, title: str) -> None:
        self._title_lbl.setText(title)

    def add_title_widget(self, widget: QWidget) -> None:
        """Add a widget to the title row (e.g. a contextual help button)."""
        self._title_row.addWidget(widget)

    def add_section_label(self, text: str) -> None:
        lbl = QLabel(text, self)
        lbl.setObjectName("PtrackSectionDivider")
        self._body.addWidget(lbl)


# ---------------------------------------------------------------------------
# Action button
# ---------------------------------------------------------------------------

class ActionButton(QPushButton):
    """QPushButton with a category-coloured left accent and themed icon."""

    def __init__(
        self,
        text: str,
        category: Category = Category.NEUTRAL,
        icon_name: str | None = None,
        *,
        primary: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._category = category
        if not self.toolTip():
            self.setToolTip(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if icon_name is not None:
            self.setIcon(icon(icon_name, category=category))
            self.setIconSize(QSize(16, 16))
        col = category_color(category)
        weight = "600" if primary else "500"
        bg = "palette(highlight)" if primary else "palette(button)"
        fg = "palette(highlighted-text)" if primary else "palette(button-text)"
        self.setStyleSheet(
            f"QPushButton {{"
            f"  border-left: 3px solid {col};"
            f"  border-radius: 6px;"
            f"  padding: 6px 12px;"
            f"  font-weight: {weight};"
            f"  background: {bg};"
            f"  color: {fg};"
            f"}}"
            f"QPushButton:hover {{ background: {col}; color: white; }}"
            f"QPushButton:disabled {{ color: palette(mid); border-left-color: palette(mid); background: palette(window); }}"
        )


# ---------------------------------------------------------------------------
# Output log
# ---------------------------------------------------------------------------

class OutputLog(QPlainTextEdit):
    """Read-only log panel with a capped scrollback.

    Lines render as rich text — proportional prose with muted ``[prefix]``
    tags, accents for failures/warnings, and the monospace font only when a
    line's spacing is tabular (see :mod:`..ui.textformat`)."""

    line_appended = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None, *, max_lines: int = 5000) -> None:
        super().__init__(parent)
        self.setObjectName("PtrackLog")
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lines)
        #: Text written without a closing newline, waiting for the rest of
        #: its line. It is displayed immediately (as its own block) and that
        #: block is rewritten when the remainder arrives.
        self._pending = ""
        self._pending_shown = False

    def append_line(self, text: str) -> None:
        """Append *text*, which may be one line, many, or a partial chunk.

        Writes arrive straight from a redirected ``stdout``, so one call can
        carry a whole multi-line table, a bare newline, or the front half of
        a line. ``appendHtml`` renders its argument as a single HTML
        fragment, where newlines are just whitespace — passing a multi-line
        chunk to it ran every row of a table together on one line. Split
        here so each line becomes its own block.
        """
        if not text:
            return
        # Re-attach anything held back from the previous chunk, then peel off
        # the new trailing fragment (empty when the chunk ends in a newline).
        lines = (self._pending + text).split("\n")
        self._pending = lines.pop()
        if self._pending_shown:
            self._drop_last_block()
            self._pending_shown = False
        for line in lines:
            self._append_one(line)
        if self._pending:
            self._append_one(self._pending)
            self._pending_shown = True
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.ensureCursorVisible()
        self.line_appended.emit(text)

    def _append_one(self, line: str) -> None:
        from .textformat import log_line_to_html

        stripped = line.rstrip()
        if stripped:
            self.appendHtml(log_line_to_html(stripped))
        else:
            self.appendPlainText("")

    def _drop_last_block(self) -> None:
        """Remove the block holding the partial line, so the completed line
        replaces it rather than appearing twice."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.removeSelectedText()


# ---------------------------------------------------------------------------
# Plot dock
# ---------------------------------------------------------------------------

def _close_figure(figure: Any) -> None:
    """Unregister *figure* from pyplot, ignoring anything that goes wrong."""
    try:
        import matplotlib.pyplot as _plt

        _plt.close(figure)
    except Exception:  # noqa: BLE001
        pass


def _close_figure_when_destroyed(widget: QWidget, figure: Any) -> None:
    """Close *figure* once *widget*'s C++ object goes away.

    ``destroyed`` fires after ``deleteLater`` has run, which is exactly when
    the embedded canvas stops needing the figure. The slot touches no Qt
    state, so it is safe at that point in the object's life.
    """
    # Bind both the figure and the helper as default arguments: the signal can
    # fire from the garbage collector or at interpreter shutdown, when free
    # variables and module globals are no longer reachable, and an exception
    # raised inside a Qt slot takes the process down.
    widget.destroyed.connect(
        lambda *_args, fig=figure, close=_close_figure: close(fig)
    )


class PlotDock(QTabWidget):
    """Tabbed dock for matplotlib figures.

    The first tab is always *Output* (the supplied :class:`OutputLog`); an
    optional second permanent *Errors* tab (``error_log``) collects warnings
    and errors so they aren't lost in the normal output. Subsequent tabs are
    added by :meth:`add_figure` and are individually closable.
    """

    def __init__(
        self,
        output_log: OutputLog,
        error_log: OutputLog | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.tabCloseRequested.connect(self._on_close)

        no_btn = self.tabBar().ButtonPosition.RightSide
        self._output_log = output_log
        self._error_log = error_log
        self._unseen_issues = 0
        self.addTab(output_log, icon("info"), "Output")
        self.tabBar().setTabButton(0, no_btn, None)
        if error_log is not None:
            idx = self.addTab(error_log, icon("warning"), "Errors")
            self.tabBar().setTabButton(idx, no_btn, None)
            # Badge the Errors tab when lines arrive while it isn't visible.
            error_log.line_appended.connect(self._on_issue_logged)
            self.currentChanged.connect(self._on_tab_changed)

        clear_btn = QToolButton(self)
        clear_btn.setText("Clear plots")
        clear_btn.setIcon(icon("clear"))
        clear_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        clear_btn.setAutoRaise(True)
        clear_btn.setToolTip("Close all plot tabs and show the Output tab.")
        clear_btn.clicked.connect(self.clear_figures)
        self.setCornerWidget(clear_btn, Qt.Corner.TopRightCorner)

    def _on_issue_logged(self, _text: str) -> None:
        idx = self.indexOf(self._error_log)
        if idx < 0 or self.currentWidget() is self._error_log:
            return
        self._unseen_issues += 1
        self.setTabText(idx, f"Errors ({self._unseen_issues})")

    def _on_tab_changed(self, _idx: int) -> None:
        if self.currentWidget() is self._error_log:
            self._unseen_issues = 0
            self.setTabText(self.indexOf(self._error_log), "Errors")

    def clear_figures(self) -> None:
        """Close every figure tab (everything but Output/Errors), show Output."""
        fixed = (self._output_log, self._error_log)
        for idx in range(self.count() - 1, -1, -1):
            w = self.widget(idx)
            if w in fixed:
                continue
            self.removeTab(idx)
            if w is not None:
                w.deleteLater()
        self.setCurrentWidget(self._output_log)

    def _on_close(self, idx: int) -> None:
        if self.widget(idx) in (self._output_log, self._error_log):
            return
        w = self.widget(idx)
        self.removeTab(idx)
        if w is not None:
            w.deleteLater()

    def add_figure(
        self,
        title: str,
        figure: Any,
        *,
        interactive: bool = False,
        replace_existing: bool = False,
    ) -> None:
        """Embed *figure* (a matplotlib ``Figure``) as a tab.

        ``interactive=True`` uses matplotlib's native Qt canvas + navigation
        toolbar; ``interactive=False`` (default) renders the figure to a PNG
        and shows it inside :class:`ZoomableImageView` so the user can pan,
        wheel-zoom, and use the +/−/Fit buttons just like the saved-artifact
        tabs in the QC viewer.

        ``replace_existing=True`` reuses the tab that already carries *title*
        instead of opening another one — for views that re-render the same
        panel as the user clicks around, so tabs don't pile up unboundedly.
        """
        if not hasattr(figure, "savefig") and hasattr(figure, "draw"):
            figure = figure.draw()

        if interactive:
            host = QWidget(self)
            lay = QVBoxLayout(host)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

            canvas = FigureCanvasQTAgg(figure)
            toolbar = NavigationToolbar2QT(canvas, host)
            lay.addWidget(toolbar)
            lay.addWidget(canvas, 1)
            try:
                import mplcursors

                cursor = mplcursors.cursor(figure, hover=True)
                host._mpl_cursor = cursor  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
            # The tab owns the figure from here on. Without this, an
            # interactive figure stayed registered with pyplot forever —
            # closing the tab (or "Clear plots") freed the widget but left the
            # full RGBA buffer and the source dataframes alive.
            _close_figure_when_destroyed(host, figure)
            widget: QWidget = host
        else:
            import io as _io

            from .zoom import ZoomableImageView

            buf = _io.BytesIO()
            try:
                figure.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            finally:
                # Also close on a savefig failure, which used to leak the figure.
                _close_figure(figure)
            buf.seek(0)
            pix = QPixmap()
            pix.loadFromData(buf.getvalue())
            widget = ZoomableImageView(pix)

        self.add_widget(title, widget, replace_existing=replace_existing)

    def add_widget(
        self,
        title: str,
        widget: QWidget,
        tab_icon: Any = None,
        *,
        replace_existing: bool = False,
    ) -> int:
        """Add *widget* as a tab titled *title* and make it current.

        ``replace_existing=True`` reuses the tab that already carries *title*
        (deleting the widget it held) instead of opening a second one, so
        re-rendering the same panel doesn't grow the tab bar without bound.
        Returns the tab index.
        """
        if tab_icon is None:
            tab_icon = icon("plots", category=Category.PLOTS)
        if replace_existing:
            for existing in range(self.count()):
                if self.tabText(existing) != title:
                    continue
                old = self.widget(existing)
                if old in (self._output_log, self._error_log):
                    break
                self.removeTab(existing)
                if old is not None:
                    old.deleteLater()
                idx = self.insertTab(existing, widget, tab_icon, title)
                self.setCurrentIndex(idx)
                return idx

        idx = self.addTab(widget, tab_icon, title)
        self.setCurrentIndex(idx)
        return idx
