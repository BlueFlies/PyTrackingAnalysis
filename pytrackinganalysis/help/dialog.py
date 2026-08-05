"""Help dialogs: single-topic HelpDialog and multi-topic HelpBrowser."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .render import topic_html
from .topics import TOPICS, get_topic


class HelpDialog(QDialog):
    """Modal dialog showing one help topic."""

    def __init__(
        self,
        topic_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        topic = get_topic(topic_id)
        self.setWindowTitle(topic.title)
        self.setMinimumSize(520, 420)
        self.resize(640, 520)

        lay = QVBoxLayout(self)
        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(True)
        browser.setHtml(topic_html(topic_id))
        lay.addWidget(browser, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        lay.addWidget(buttons)


class HelpBrowser(QDialog):
    """Modal help browser with a topic list and content pane."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        initial_topic: str = "getting_started",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PyTrackingAnalysis — Help")
        self.setMinimumSize(720, 480)
        self.resize(860, 600)

        outer = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(QLabel("Topics"))
        self._list = QListWidget()
        for topic in TOPICS:
            item = QListWidgetItem(topic.title)
            item.setData(Qt.ItemDataRole.UserRole, topic.id)
            item.setToolTip(topic.summary)
            self._list.addItem(item)
        self._list.currentItemChanged.connect(self._on_topic_changed)
        left_lay.addWidget(self._list, 1)
        splitter.addWidget(left)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        splitter.addWidget(self._browser)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([220, 640])
        outer.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.select_topic(initial_topic)

    def select_topic(self, topic_id: str) -> None:
        get_topic(topic_id)  # validate
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == topic_id:
                self._list.setCurrentItem(item)
                return
        if self._list.count():
            self._list.setCurrentRow(0)

    def _on_topic_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        topic_id = current.data(Qt.ItemDataRole.UserRole)
        if not topic_id:
            return
        topic = get_topic(topic_id)
        self.setWindowTitle(f"Help — {topic.title}")
        self._browser.setHtml(topic_html(topic_id))


def show_help(parent: QWidget | None, topic_id: str) -> None:
    """Show a single-topic help dialog."""
    dlg = HelpDialog(topic_id, parent)
    dlg.exec()


def open_help_browser(
    parent: QWidget | None,
    topic_id: str = "getting_started",
) -> None:
    """Show the multi-topic help browser."""
    dlg = HelpBrowser(parent, initial_topic=topic_id)
    dlg.exec()


def open_getting_started(
    parent: QWidget | None,
    *,
    topic_id: str = "getting_started",
) -> None:
    """Open the help browser on Getting Started (or another topic)."""
    open_help_browser(parent, topic_id=topic_id)
