"""Script-editor canvas: the ordered list of steps.

Each step is a :class:`_StepCard`: a rounded panel with the step number,
the action's icon, its title, a one-line parameter summary, plus Move
Up / Move Down / Remove buttons.  Selecting a card emits
:pyattr:`stepSelected` so the inspector can re-render its form.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..ui import Category, category_color, icon
from .actions import ACTIONS, Action


def _unknown_action(key: str) -> Action:
    """A stand-in :class:`Action` for a step whose key is not in the registry.

    Skipping the card instead would leave ``_cards`` shorter than ``_steps``:
    every index after the unknown step would then address the wrong entry, so
    selecting a card opened its neighbour's parameters and Remove deleted the
    wrong step.  Rendering a placeholder keeps the two lists in lockstep *and*
    makes the bad step visible so the user can delete it.
    """
    return Action(
        key=key,
        title=f"Unknown action: {key!r}" if key else "Unknown action",
        description=(
            "This step's action is not in the registry — it may come from a "
            "newer version or a typo in the YAML. It cannot be edited here; "
            "remove it or fix the 'action:' key in tracking_config.yaml."
        ),
        category=Category.QC,
        icon_name="warning",
        params=(),
    )


class _StepCard(QFrame):
    """A single step in the canvas."""

    selected = pyqtSignal(int)
    removeRequested = pyqtSignal(int)
    moveUpRequested = pyqtSignal(int)
    moveDownRequested = pyqtSignal(int)

    def __init__(self, index: int, action: Action, params: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self._action = action
        self._is_selected = False
        self.setObjectName("PtrackStepCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(10)

        self._num_lbl = QLabel(f"{index + 1}.")
        self._num_lbl.setFixedWidth(28)
        self._num_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._num_lbl.setStyleSheet("color: palette(mid);")
        outer.addWidget(self._num_lbl)

        ico = QLabel()
        ico.setPixmap(icon(action.icon_name, category=action.category).pixmap(22, 22))
        outer.addWidget(ico)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self._title_lbl = QLabel(action.title)
        self._title_lbl.setStyleSheet("font-weight: 600;")
        self._chip_lbl = QLabel(self._format_params(params))
        self._chip_lbl.setStyleSheet("color: palette(mid); font-size: 9pt;")
        self._chip_lbl.setWordWrap(False)
        text_col.addWidget(self._title_lbl)
        text_col.addWidget(self._chip_lbl)
        outer.addLayout(text_col, 1)

        self._warning_lbl = QLabel("")
        self._warning_lbl.setPixmap(icon("warning", category=Category.QC).pixmap(16, 16))
        self._warning_lbl.setVisible(False)
        outer.addWidget(self._warning_lbl)

        btn_up = self._tool_button("up", "Move up", lambda: self.moveUpRequested.emit(self._index))
        btn_down = self._tool_button("down", "Move down", lambda: self.moveDownRequested.emit(self._index))
        btn_rm = self._tool_button("delete", "Remove step", lambda: self.removeRequested.emit(self._index))
        outer.addWidget(btn_up)
        outer.addWidget(btn_down)
        outer.addWidget(btn_rm)

    # ------------------------------------------------------------------
    # Public API used by Canvas
    # ------------------------------------------------------------------

    def set_index(self, new_index: int) -> None:
        self._index = new_index
        self._num_lbl.setText(f"{new_index + 1}.")

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self._update_style()

    def set_params_summary(self, params: dict) -> None:
        self._chip_lbl.setText(self._format_params(params))

    def set_has_errors(self, has_errors: bool, tooltip: str = "") -> None:
        self._warning_lbl.setVisible(has_errors)
        self._warning_lbl.setToolTip(tooltip)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.selected.emit(self._index)
        super().mousePressEvent(event)

    def _update_style(self) -> None:
        col = category_color(self._action.category)
        sel_bg = "rgba(100, 140, 220, 35)" if self._is_selected else "palette(base)"
        self.setStyleSheet(
            f"QFrame#PtrackStepCard {{"
            f"  border-left: 4px solid {col};"
            f"  border-radius: 6px;"
            f"  background: {sel_bg};"
            f"  padding: 2px;"
            f"}}"
        )

    def _format_params(self, params: dict) -> str:
        if not params:
            return "(no parameters)"
        pieces = []
        for k, v in params.items():
            if isinstance(v, (list, tuple)):
                val = ", ".join(str(x) for x in v)
            else:
                val = str(v)
            if len(val) > 30:
                val = val[:27] + "…"
            pieces.append(f"{k}={val}")
        return " · ".join(pieces)

    def _tool_button(self, icon_name: str, tip: str, slot) -> QToolButton:
        btn = QToolButton(self)
        btn.setIcon(icon(icon_name))
        btn.setIconSize(QSize(14, 14))
        btn.setAutoRaise(True)
        btn.setToolTip(tip)
        btn.clicked.connect(slot)
        return btn


class Canvas(QWidget):
    """Ordered list of :class:`_StepCard` rows with selection + reorder."""

    stepSelected = pyqtSignal(int)  # index, or -1 when nothing selected
    stepsChanged = pyqtSignal()  # emitted whenever the step list changes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self._title_lbl = QLabel("Steps")
        self._title_lbl.setStyleSheet("font-weight: 600; font-size: 12pt;")
        outer.addWidget(self._title_lbl)

        self._empty_lbl = QLabel(
            "Double-click an action in the palette on the left to add it here."
        )
        self._empty_lbl.setStyleSheet("color: palette(mid); font-style: italic;")
        self._empty_lbl.setWordWrap(True)
        outer.addWidget(self._empty_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        host = QWidget()
        self._list_layout = QVBoxLayout(host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch(1)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)

        self._steps: list[dict] = []
        self._cards: list[_StepCard] = []
        self._selected_idx: int = -1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_steps(self, steps: list[dict]) -> None:
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()
        self._steps = [dict(s) for s in steps]
        for step in self._steps:
            self._append_card(step)
        self._selected_idx = 0 if self._cards else -1
        self._refresh_selection()
        self._empty_lbl.setVisible(not self._cards)
        self.stepsChanged.emit()
        if self._selected_idx >= 0:
            self.stepSelected.emit(self._selected_idx)

    def steps(self) -> list[dict]:
        # Return a deep-enough copy; params dicts are shared-by-reference but
        # callers that modify them go through update_params().
        return [dict(s, params=dict(s.get("params", {}))) for s in self._steps]

    def set_actions(self, actions: dict[str, Action]) -> None:
        """The registry used to resolve step cards (project vs experiment)."""
        self._actions = actions

    def add_action(self, key: str) -> None:
        action = getattr(self, "_actions", ACTIONS).get(key)
        if action is None:
            return
        defaults = {p.name: p.default for p in action.params if p.default is not None}
        step = {"action": key, "params": defaults}
        self._steps.append(step)
        self._append_card(step)
        self._selected_idx = len(self._steps) - 1
        self._refresh_selection()
        self._empty_lbl.setVisible(False)
        self.stepsChanged.emit()
        self.stepSelected.emit(self._selected_idx)

    def update_params(self, index: int, params: dict) -> None:
        if 0 <= index < len(self._steps):
            self._steps[index]["params"] = dict(params)
            self._cards[index].set_params_summary(params)
            self.stepsChanged.emit()

    def set_errors(self, errors_by_index: dict[int, list[str]]) -> None:
        for i, card in enumerate(self._cards):
            errs = errors_by_index.get(i, [])
            card.set_has_errors(bool(errs), "\n".join(errs))

    def current_step(self) -> dict | None:
        if 0 <= self._selected_idx < len(self._steps):
            return self._steps[self._selected_idx]
        return None

    def current_index(self) -> int:
        return self._selected_idx

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _append_card(self, step: dict) -> None:
        key = step.get("action", "")
        action = getattr(self, "_actions", ACTIONS).get(key) or _unknown_action(key)
        idx = len(self._cards)
        card = _StepCard(idx, action, step.get("params", {}))
        card.selected.connect(self._on_card_selected)
        card.removeRequested.connect(self._remove_at)
        card.moveUpRequested.connect(lambda i: self._move(i, -1))
        card.moveDownRequested.connect(lambda i: self._move(i, +1))
        # Insert before the trailing stretch
        self._list_layout.insertWidget(self._list_layout.count() - 1, card)
        self._cards.append(card)

    def _on_card_selected(self, index: int) -> None:
        self._selected_idx = index
        self._refresh_selection()
        self.stepSelected.emit(index)

    def _refresh_selection(self) -> None:
        for i, c in enumerate(self._cards):
            c.set_selected(i == self._selected_idx)

    def _remove_at(self, index: int) -> None:
        if not (0 <= index < len(self._steps)):
            return
        card = self._cards.pop(index)
        card.setParent(None)
        card.deleteLater()
        self._steps.pop(index)
        for i, c in enumerate(self._cards):
            c.set_index(i)
        if self._cards:
            self._selected_idx = min(index, len(self._cards) - 1)
        else:
            self._selected_idx = -1
        self._refresh_selection()
        self._empty_lbl.setVisible(not self._cards)
        self.stepsChanged.emit()
        self.stepSelected.emit(self._selected_idx)

    def _move(self, index: int, delta: int) -> None:
        new = index + delta
        if not (0 <= new < len(self._steps)):
            return
        self._steps[index], self._steps[new] = self._steps[new], self._steps[index]
        # Rebuild cards: simplest correctness.
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()
        for step in self._steps:
            self._append_card(step)
        self._selected_idx = new
        self._refresh_selection()
        self.stepsChanged.emit()
        self.stepSelected.emit(new)
