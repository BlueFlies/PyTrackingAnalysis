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
            f"QPushButton:disabled {{ color: palette(mid); border-left-color: palette(mid); }}"
        )


# ---------------------------------------------------------------------------
# Output log
# ---------------------------------------------------------------------------

class OutputLog(QPlainTextEdit):
    """Read-only log panel with a capped scrollback."""

    def __init__(self, parent: QWidget | None = None, *, max_lines: int = 5000) -> None:
        super().__init__(parent)
        self.setObjectName("PtrackLog")
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lines)

    def append_line(self, text: str) -> None:
        self.appendPlainText(text.rstrip())
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.ensureCursorVisible()


# ---------------------------------------------------------------------------
# Plot dock
# ---------------------------------------------------------------------------

class PlotDock(QTabWidget):
    """Tabbed dock for matplotlib figures.

    The first tab is always *Output* (the supplied :class:`OutputLog`);
    subsequent tabs are added by :meth:`add_figure` and are individually
    closable.
    """

    def __init__(self, output_log: OutputLog, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.tabCloseRequested.connect(self._on_close)

        self.addTab(output_log, icon("info"), "Output")
        self.tabBar().setTabButton(0, self.tabBar().ButtonPosition.RightSide, None)

    def _on_close(self, idx: int) -> None:
        if idx == 0:
            return
        w = self.widget(idx)
        self.removeTab(idx)
        if w is not None:
            w.deleteLater()

    def add_figure(self, title: str, figure: Any, *, interactive: bool = False) -> None:
        """Embed *figure* (a matplotlib ``Figure``) as a new tab.

        ``interactive=True`` uses matplotlib's native Qt canvas + navigation
        toolbar; ``interactive=False`` (default) renders the figure to a PNG
        and shows it inside :class:`ZoomableImageView` so the user can pan,
        wheel-zoom, and use the +/−/Fit buttons just like the saved-artifact
        tabs in the QC viewer.
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
            widget: QWidget = host
        else:
            import io as _io

            from .zoom import ZoomableImageView

            buf = _io.BytesIO()
            figure.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            buf.seek(0)
            pix = QPixmap()
            pix.loadFromData(buf.getvalue())
            try:
                import matplotlib.pyplot as _plt

                _plt.close(figure)
            except Exception:  # noqa: BLE001
                pass
            widget = ZoomableImageView(pix)

        idx = self.addTab(widget, icon("plots", category=Category.PLOTS), title)
        self.setCurrentIndex(idx)
