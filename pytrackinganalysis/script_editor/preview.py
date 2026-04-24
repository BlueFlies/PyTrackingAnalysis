"""Bottom preview panel: live YAML of the active script."""

from __future__ import annotations

from PyQt6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class Preview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.setSpacing(4)
        self._edit = QPlainTextEdit()
        self._edit.setObjectName("PtrackLog")
        self._edit.setReadOnly(True)
        self._edit.setMinimumHeight(100)
        lay.addWidget(self._edit)

    def set_text(self, text: str) -> None:
        if self._edit.toPlainText() != text:
            self._edit.setPlainText(text)
