"""Script-editor inspector: parameter form for the selected step.

Renders a :class:`QFormLayout` whose rows come from the action's
:class:`ParamSpec` list.  Emits :pyattr:`paramsChanged(index, params)`
whenever any widget fires its edit signal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..ui import Category, category_color, icon
from .actions import ACTIONS, Action, ParamSpec


class Inspector(QWidget):
    """Right pane: dynamic form for the currently-selected step."""

    paramsChanged = pyqtSignal(int, dict)  # step_index, new params

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        self._title = QLabel("Step parameters")
        self._title.setStyleSheet("font-weight: 600; font-size: 12pt;")
        outer.addWidget(self._title)

        # Header card (action title + description + icon)
        self._header = QWidget()
        self._header.setObjectName("PtrackInspectorHeader")
        hh = QHBoxLayout(self._header)
        hh.setContentsMargins(10, 8, 10, 8)
        hh.setSpacing(8)
        self._header_icon = QLabel()
        self._header_title = QLabel("")
        self._header_title.setStyleSheet("font-weight: 600;")
        self._header_desc = QLabel("")
        self._header_desc.setStyleSheet("color: palette(mid); font-size: 9pt;")
        self._header_desc.setWordWrap(True)
        text_col = QVBoxLayout()
        text_col.addWidget(self._header_title)
        text_col.addWidget(self._header_desc)
        hh.addWidget(self._header_icon)
        hh.addLayout(text_col, 1)
        outer.addWidget(self._header)

        # Error banner (QC red)
        self._errors_lbl = QLabel("")
        self._errors_lbl.setStyleSheet(
            f"color: {category_color(Category.QC)}; font-size: 9pt;"
        )
        self._errors_lbl.setWordWrap(True)
        self._errors_lbl.setVisible(False)
        outer.addWidget(self._errors_lbl)

        # Scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        self._form_host = QWidget()
        self._form = QFormLayout(self._form_host)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._form.setHorizontalSpacing(10)
        self._form.setVerticalSpacing(6)
        scroll.setWidget(self._form_host)
        outer.addWidget(scroll, 1)

        self._clear_empty()

        self._current_index: int = -1
        self._current_action: Action | None = None
        self._experiment_type: str | None = None
        # param name → human-readable inherited value. Surfaced as placeholder
        # text on the matching widget so the user can see what value the
        # script will inherit from the project's tracking_config.yaml when
        # left blank.
        self._inherited: dict[str, str] = {}
        # param name → field widget for the currently rendered step. Used by
        # _collect_params so we never depend on form-row indexing.
        self._widgets_by_name: dict[str, QWidget] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_experiment_type(self, exp_type: str | None) -> None:
        """Affects the ``plot`` action's method dropdown, etc."""
        if exp_type != self._experiment_type:
            self._experiment_type = exp_type
            # If something is currently selected, re-render it so choices update.
            if self._current_index >= 0 and self._current_action is not None:
                self.show_step(self._current_index, self._current_action, self._collect_params())

    def set_inherited(self, values: dict[str, str]) -> None:
        """Provide YAML-inherited values to display as placeholders.

        Maps param name → string representation. Each is rendered as
        placeholder text on the matching widget so the user sees what the
        step will fall back to when the field is left blank.
        """
        self._inherited = dict(values)
        if self._current_index >= 0 and self._current_action is not None:
            self.show_step(self._current_index, self._current_action, self._collect_params())

    def clear(self) -> None:
        self._current_index = -1
        self._current_action = None
        self._clear_empty()

    def show_step(self, index: int, action: Action, params: dict) -> None:
        # Detach the current action *before* clearing the form. Widgets
        # destroyed by ``_clear_form`` may emit final signals that fire the
        # connected ``_validate_and_emit`` slot; we don't want it walking the
        # half-cleared form against the new action's specs.
        self._current_index = -1
        self._current_action = None
        self._clear_form()

        self._current_index = index
        self._current_action = action

        self._header.setStyleSheet(
            f"QWidget#PtrackInspectorHeader {{"
            f"  border-left: 4px solid {category_color(action.category)};"
            f"  border-radius: 6px;"
            f"  background: palette(alternate-base);"
            f"}}"
        )
        self._header_icon.setPixmap(
            icon(action.icon_name, category=action.category).pixmap(24, 24)
        )
        self._header_title.setText(action.title)
        self._header_desc.setText(action.description)

        self._widgets_by_name = {}
        for spec in action.params:
            value = params.get(spec.name, spec.default)
            widget = self._make_widget(spec, value)
            self._form.addRow(f"{spec.label}:", widget)
            self._widgets_by_name[spec.name] = widget

        # Wire `enabled_when` dependencies: a dependent widget is enabled iff
        # its sibling controller checkbox is checked.
        for spec in action.params:
            if spec.enabled_when is None:
                continue
            controller = self._widgets_by_name.get(spec.enabled_when)
            dependent = self._widgets_by_name.get(spec.name)
            if not isinstance(controller, QCheckBox) or dependent is None:
                continue
            self._wire_enabled_when(controller, dependent)

        # Validate + surface errors immediately
        self._validate_and_emit(emit_change=False)

    @staticmethod
    def _wire_enabled_when(controller: QCheckBox, dependent: QWidget) -> None:
        def _sync() -> None:
            dependent.setEnabled(controller.isChecked())
        _sync()
        controller.toggled.connect(lambda _checked: _sync())

    def _clear_empty(self) -> None:
        self._header.setVisible(False)
        self._errors_lbl.setVisible(False)
        self._clear_form()
        empty = QLabel(
            "Select a step on the left to edit its parameters."
        )
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet("color: palette(mid); font-style: italic; padding: 24px;")
        self._form.addRow(empty)

    def _clear_form(self) -> None:
        # Drop every row. ``removeRow`` (unlike ``takeAt``) also collapses the
        # row count, so subsequent ``addRow`` calls start at row 0 again.
        while self._form.rowCount() > 0:
            self._form.removeRow(0)
        self._widgets_by_name = {}
        self._header.setVisible(True)

    # ------------------------------------------------------------------
    # Widget factory
    # ------------------------------------------------------------------

    def _make_widget(self, spec: ParamSpec, value: Any) -> QWidget:
        if spec.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(value) if value is not None else bool(spec.default))
            w.stateChanged.connect(lambda _: self._validate_and_emit())
            return w

        if spec.kind == "int":
            w = QSpinBox()
            lo = int(spec.min) if spec.min is not None else -10**9
            hi = int(spec.max) if spec.max is not None else 10**9
            w.setRange(lo, hi)
            try:
                w.setValue(int(value) if value is not None else int(spec.default or 0))
            except (TypeError, ValueError):
                w.setValue(0)
            w.valueChanged.connect(lambda _: self._validate_and_emit())
            return w

        if spec.kind == "float":
            w = QDoubleSpinBox()
            w.setDecimals(3)
            w.setSingleStep(0.05)
            lo = float(spec.min) if spec.min is not None else -1e9
            hi = float(spec.max) if spec.max is not None else 1e9
            w.setRange(lo, hi)
            try:
                w.setValue(float(value) if value is not None else float(spec.default or 0.0))
            except (TypeError, ValueError):
                w.setValue(0.0)
            w.valueChanged.connect(lambda _: self._validate_and_emit())
            return w

        if spec.kind == "choice":
            w = QComboBox()
            choices = list(spec.choices or ())
            w.addItems(choices)
            if value is not None and str(value) in choices:
                w.setCurrentText(str(value))
            elif choices:
                w.setCurrentIndex(0)
            w.currentTextChanged.connect(lambda _: self._validate_and_emit())
            return w

        if spec.kind == "path":
            w = QWidget()
            row = QHBoxLayout(w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            edit = QLineEdit(str(value) if value is not None else str(spec.default or ""))
            edit.setObjectName("pathField")
            edit.textChanged.connect(lambda _: self._validate_and_emit())
            row.addWidget(edit, 1)
            browse = QPushButton("…")
            browse.setFixedWidth(30)
            def _pick() -> None:
                chosen = QFileDialog.getExistingDirectory(self, "Choose directory", edit.text() or ".")
                if chosen:
                    edit.setText(chosen)
            browse.clicked.connect(_pick)
            row.addWidget(browse)
            return w

        if spec.kind == "list":
            w = QLineEdit()
            if isinstance(value, (list, tuple)):
                w.setText(", ".join(str(v) for v in value))
            elif value is not None:
                w.setText(str(value))
            inherited = self._inherited.get(spec.name)
            w.setPlaceholderText(
                f"inherited: {inherited}" if inherited else "comma-separated"
            )
            w.textChanged.connect(lambda _: self._validate_and_emit())
            return w

        # default: string
        w = QLineEdit()
        w.setText(str(value) if value is not None else str(spec.default or ""))
        w.textChanged.connect(lambda _: self._validate_and_emit())
        return w

    def _collect_params(self) -> dict:
        if self._current_action is None:
            return {}
        params: dict[str, Any] = {}
        for spec in self._current_action.params:
            w = self._widgets_by_name.get(spec.name)
            if w is None:
                continue
            params[spec.name] = self._widget_value(w, spec)
        return params

    @staticmethod
    def _widget_value(widget: QWidget, spec: ParamSpec) -> Any:
        if spec.kind == "bool":
            return bool(widget.isChecked())
        if spec.kind == "int":
            return int(widget.value())
        if spec.kind == "float":
            return float(widget.value())
        if spec.kind == "choice":
            return widget.currentText()
        if spec.kind == "path":
            edit = widget.findChild(QLineEdit, "pathField")
            return edit.text() if edit is not None else ""
        if spec.kind == "list":
            raw = widget.text().strip()
            if not raw:
                return []
            return [x.strip() for x in raw.split(",") if x.strip()]
        return widget.text()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_and_emit(self, emit_change: bool = True) -> None:
        if self._current_action is None or self._current_index < 0:
            return
        params = self._collect_params()
        errors = self._current_action.validate(params, experiment_type=self._experiment_type)
        self._errors_lbl.setVisible(bool(errors))
        if errors:
            self._errors_lbl.setText(" · ".join(errors))
        if emit_change:
            self.paramsChanged.emit(self._current_index, params)
