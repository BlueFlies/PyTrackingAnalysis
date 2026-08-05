"""Circular ? help buttons and TopBar help entry."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QToolButton, QWidget

from .dialog import open_getting_started, show_help


_HELP_BTN_STYLE = (
    "QToolButton {"
    "  border: 1px solid palette(mid);"
    "  border-radius: 9px;"
    "  background: palette(button);"
    "  color: palette(button-text);"
    "  font-size: 11px;"
    "  font-weight: 600;"
    "  padding: 0px;"
    "}"
    "QToolButton:hover {"
    "  background: palette(midlight);"
    "  border-color: palette(highlight);"
    "}"
)


class HelpButton(QToolButton):
    """Circular ``?`` button that opens a single help topic."""

    def __init__(
        self,
        topic_id: str,
        parent: QWidget | None = None,
        *,
        tooltip: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._topic_id = topic_id
        self.setText("?")
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_HELP_BTN_STYLE)
        self.setToolTip(tooltip or f"Help: {topic_id.replace('_', ' ')}")
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self) -> None:
        host = self.window()
        show_help(host if isinstance(host, QWidget) else self, self._topic_id)


def make_topbar_help_button(
    parent: QWidget | None = None,
    *,
    topic_id: str = "getting_started",
    browser: bool = True,
) -> QToolButton:
    """Top-bar control labelled Help that opens Getting Started / help browser."""
    btn = QToolButton(parent)
    btn.setText("Help")
    btn.setAutoRaise(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip("Getting started and in-app documentation")

    def _open() -> None:
        host = parent
        if parent is not None:
            win = parent.window()
            if isinstance(win, QWidget):
                host = win
        if browser:
            open_getting_started(host, topic_id=topic_id)
        else:
            show_help(host, topic_id)

    btn.clicked.connect(_open)
    return btn
