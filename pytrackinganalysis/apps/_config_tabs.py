"""Form-based editors for each top-level YAML section.

Ported verbatim from ``config_ui.py`` so the visual layout matches the
legacy editor.  The wrapping :class:`~pytrackinganalysis.apps.config_editor.ConfigEditorWindow`
is responsible for the surrounding pyflic-style chrome (TopBar, Cards,
YAML preview, Script Editor launcher).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import Parameters as _ParametersMod


# (display_label, yaml/enum_value). The dropdowns show the label; we read and
# write the value so the YAML stays unchanged.
TRACKING_TYPES: list[tuple[str, str]] = [
    ("Tracker", "TRACKER"),
    ("Two Choice Tracker", "TWOCHOICETRACKER"),
    ("X Choice Tracker", "XCHOICETRACKER"),
    ("D-Drop Tracker", "DDROPTRACKER"),
    ("Pairwise Interaction Tracker", "PAIRWISEINTERACTIONTRACKER"),
    ("Centrophobism Tracker", "CENTROPHOBISMTRACKER"),
    ("Counter", "COUNTER"),
    ("Two Choice Counter", "TWOCHOICECOUNTER"),
    ("Pairwise Interaction Counter", "PAIRWISEINTERACTIONCOUNTER"),
]

TRACKING_RIGS: list[tuple[str, str]] = [
    ("Small Arena", "small_arena"),
    ("Arena Max", "arena_max"),
    ("Colosseum", "colosseum"),
    ("Obscura", "obscura"),
    ("Movie", "movie"),
]

_RIG_LABELS: dict[str, str] = {value: label for label, value in TRACKING_RIGS}

# mm_per_pixel calibrations, read from the single source of truth in Parameters so
# the editor's placeholders cannot drift from what the analysis actually applies.
# A movie has no preset — the user must supply its calibration.
RIG_MM_PER_PIXEL: dict[str, float | None] = {
    **_ParametersMod.RIG_MM_PER_PIXEL,
    "movie": None,
}


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    font = QFont()
    font.setBold(True)
    lbl.setFont(font)
    return lbl


def _find_data(combo: QComboBox, value: str) -> int:
    """Locate an item by its userData (case-insensitive fallback for legacy YAML)."""
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            return i
    needle = str(value).lower()
    for i in range(combo.count()):
        if str(combo.itemData(i)).lower() == needle:
            return i
    return -1


class _NoScrollComboBox(QComboBox):
    """QComboBox that ignores wheel events so the surrounding table scrolls
    instead of accidentally changing the selection when the user spins the
    wheel over the regions grid."""

    def wheelEvent(self, event):  # noqa: N802 — Qt API
        event.ignore()


def _style_label_combo(combo: QComboBox) -> None:
    """Make a combo's closed text left-aligned and wide enough for its longest item.

    qdarktheme's style draws non-editable combo text in a way that ignores
    ``text-align: left`` and right-justifies long values. Switching to an
    editable + read-only combo lets the internal QLineEdit honour alignment.
    """
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    combo.setEditable(True)
    le = combo.lineEdit()
    le.setReadOnly(True)
    le.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    # Strip the line-edit chrome so the combo still looks like a combo.
    le.setStyleSheet("background: transparent; border: none;")
    le.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class GlobalTab(QWidget):
    # Emitted whenever the experimental-design factors change (name/levels
    # edited, row added/removed). Payload: {factor_name: [levels]}.
    factorsChanged = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.tracking_type = QComboBox()
        for label, value in TRACKING_TYPES:
            self.tracking_type.addItem(label, value)
        _style_label_combo(self.tracking_type)

        self.tracking_rig = QComboBox()
        for label, value in TRACKING_RIGS:
            self.tracking_rig.addItem(label, value)
        self.tracking_rig.currentIndexChanged.connect(
            lambda _i: self._on_rig_changed(self.tracking_rig.currentData())
        )
        _style_label_combo(self.tracking_rig)

        # Type on the left, rig on the right, sharing one row.
        type_rig_row = QHBoxLayout()
        type_rig_row.addWidget(QLabel("Tracking type:"))
        type_rig_row.addWidget(self.tracking_type, 1)
        type_rig_row.addSpacing(24)
        type_rig_row.addWidget(QLabel("Tracking rig:"))
        type_rig_row.addWidget(self.tracking_rig, 1)
        outer.addLayout(type_rig_row)

        outer.addSpacing(12)
        outer.addWidget(_section_label("Experimental design factors"))

        self.factors_table = QTableWidget(0, 2)
        self.factors_table.setHorizontalHeaderLabels(["Factor name", "Levels (comma-separated)"])
        self.factors_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.factors_table.setMaximumHeight(160)
        self.factors_table.itemChanged.connect(self._emit_factors_changed)
        m = self.factors_table.model()
        m.rowsInserted.connect(self._emit_factors_changed)
        m.rowsRemoved.connect(self._emit_factors_changed)
        outer.addWidget(self.factors_table)

        btn_row = QHBoxLayout()
        add_factor_btn = QPushButton("Add factor")
        add_factor_btn.clicked.connect(self._add_factor_row)
        rm_factor_btn = QPushButton("Remove selected")
        rm_factor_btn.clicked.connect(self._remove_factor_row)
        btn_row.addWidget(add_factor_btn)
        btn_row.addWidget(rm_factor_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        outer.addSpacing(12)
        outer.addWidget(_section_label("Facet cutoffs (optional)"))

        facet_row = QHBoxLayout()
        self.use_facets = QCheckBox("Enable faceted analysis")
        self.use_facets.stateChanged.connect(self._on_facet_toggled)
        self.facet_cutoffs = QLineEdit()
        self.facet_cutoffs.setPlaceholderText("e.g. 10, 70")
        self.facet_cutoffs.setEnabled(False)
        facet_row.addWidget(self.use_facets)
        facet_row.addWidget(QLabel("Cutoffs (minutes):"))
        facet_row.addWidget(self.facet_cutoffs)
        outer.addLayout(facet_row)

        outer.addSpacing(12)
        outer.addWidget(_section_label("Parameter overrides (leave blank to use rig defaults)"))

        pform = QFormLayout()
        pform.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.fps = QLineEdit()
        self.fps.setPlaceholderText("required for 'movie' rig")
        pform.addRow("fps:", self.fps)

        self.mm_per_pixel = QLineEdit()
        self.mm_per_pixel.setPlaceholderText("required for 'movie' rig")
        pform.addRow("mm_per_pixel:", self.mm_per_pixel)

        self.speed_window = QLineEdit()
        self.speed_window.setPlaceholderText("default 1")
        pform.addRow("speed_window_seconds:", self.speed_window)

        self.micromove_min = QLineEdit()
        self.micromove_min.setPlaceholderText("default 0.2")
        self.micromove_max = QLineEdit()
        self.micromove_max.setPlaceholderText("default 2")
        mmrow = QHBoxLayout()
        mmrow.addWidget(self.micromove_min)
        mmrow.addWidget(QLabel("–"))
        mmrow.addWidget(self.micromove_max)
        pform.addRow("micromove_speed_mm_sec [min–max]:", mmrow)

        self.walking_speed = QLineEdit()
        self.walking_speed.setPlaceholderText("default 2")
        pform.addRow("walking_speed_mm_sec:", self.walking_speed)

        self.sleep_threshold = QLineEdit()
        self.sleep_threshold.setPlaceholderText("default 5")
        pform.addRow("sleep_threshold_min:", self.sleep_threshold)

        self.interaction_distances = QLineEdit()
        self.interaction_distances.setPlaceholderText("e.g. 8  (pairwise only)")
        pform.addRow("interaction_distances (mm):", self.interaction_distances)

        outer.addLayout(pform)
        outer.addStretch()

        # Apply initial placeholders for the default-selected rig
        # (currentIndexChanged does not fire for the initial selection).
        self._on_rig_changed(self.tracking_rig.currentData())

    def _on_rig_changed(self, rig: str) -> None:
        movie = rig == "movie"
        self.fps.setEnabled(movie)
        self.mm_per_pixel.setEnabled(movie)
        if not movie:
            self.fps.clear()
            self.mm_per_pixel.clear()

        rig_label = _RIG_LABELS.get(rig, rig)
        if movie:
            self.fps.setPlaceholderText(f"required for '{rig_label}' rig")
            self.mm_per_pixel.setPlaceholderText(f"required for '{rig_label}' rig")
        else:
            self.fps.setPlaceholderText("auto-detected from data")
            mm = RIG_MM_PER_PIXEL.get(rig)
            self.mm_per_pixel.setPlaceholderText(
                f"{mm} ({rig_label} default)" if mm is not None else ""
            )

    def _on_facet_toggled(self, state) -> None:
        self.facet_cutoffs.setEnabled(bool(state))

    def _add_factor_row(self) -> None:
        r = self.factors_table.rowCount()
        self.factors_table.insertRow(r)

    def _remove_factor_row(self) -> None:
        rows = {idx.row() for idx in self.factors_table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.factors_table.removeRow(r)

    def get_factors(self) -> dict[str, list[str]]:
        """Return the current factor → levels mapping (in row order)."""
        result: dict[str, list[str]] = {}
        for r in range(self.factors_table.rowCount()):
            name_item = self.factors_table.item(r, 0)
            levels_item = self.factors_table.item(r, 1)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            levels = [
                lvl.strip()
                for lvl in (levels_item.text() if levels_item else "").split(",")
                if lvl.strip()
            ]
            result[name] = levels
        return result

    def _emit_factors_changed(self, *_args) -> None:
        self.factorsChanged.emit(self.get_factors())

    def load(self, config: dict) -> None:
        g = config.get("global", {})

        tt = g.get("tracking_type", "TRACKER")
        self.tracking_type.setCurrentIndex(max(_find_data(self.tracking_type, tt), 0))

        rig = g.get("tracking_rig", "small_arena")
        self.tracking_rig.setCurrentIndex(max(_find_data(self.tracking_rig, rig), 0))
        # Refresh override placeholders even if the index did not change
        # (currentIndexChanged would not fire in that case).
        self._on_rig_changed(self.tracking_rig.currentData())

        self.factors_table.setRowCount(0)
        for name, levels in g.get("experimental_design_factors", {}).items():
            r = self.factors_table.rowCount()
            self.factors_table.insertRow(r)
            self.factors_table.setItem(r, 0, QTableWidgetItem(name))
            self.factors_table.setItem(r, 1, QTableWidgetItem(", ".join(str(l) for l in levels)))

        cutoffs = g.get("facet_cutoffs")
        if cutoffs:
            self.use_facets.setChecked(True)
            self.facet_cutoffs.setText(", ".join(str(c) for c in cutoffs))
        else:
            self.use_facets.setChecked(False)
            self.facet_cutoffs.clear()

        self.fps.setText(str(g["fps"]) if "fps" in g else "")
        self.mm_per_pixel.setText(str(g["mm_per_pixel"]) if "mm_per_pixel" in g else "")
        self.speed_window.setText(str(g["speed_window_seconds"]) if "speed_window_seconds" in g else "")
        mm = g.get("micromove_speed_mm_sec")
        if mm and len(mm) == 2:
            self.micromove_min.setText(str(mm[0]))
            self.micromove_max.setText(str(mm[1]))
        self.walking_speed.setText(str(g["walking_speed_mm_sec"]) if "walking_speed_mm_sec" in g else "")
        self.sleep_threshold.setText(str(g["sleep_threshold_min"]) if "sleep_threshold_min" in g else "")
        idist = g.get("interaction_distances")
        if idist:
            self.interaction_distances.setText(", ".join(str(d) for d in idist))

    # Keys this tab owns. The window uses these to tell "the user cleared this
    # field" apart from "this key was hand-added and is none of our business".
    _OWNED_KEYS = (
        "tracking_type",
        "tracking_rig",
        "experimental_design_factors",
        "facet_cutoffs",
        "fps",
        "mm_per_pixel",
        "speed_window_seconds",
        "walking_speed_mm_sec",
        "sleep_threshold_min",
        "micromove_speed_mm_sec",
        "interaction_distances",
    )

    def owned_keys(self) -> tuple[str, ...]:
        """The ``global:`` keys this tab is responsible for."""
        return self._OWNED_KEYS

    def validation_errors(self) -> list[str]:
        """Field-level problems that must be fixed before the config can be saved.

        A malformed number used to be dropped on the floor by ``dump()``, so the
        value silently vanished from the saved file and the analysis quietly ran
        with a rig default instead.
        """
        errors: list[str] = []

        def _check_number(label, text, *, positive=False):
            text = text.strip()
            if not text:
                return
            try:
                value = float(text)
            except ValueError:
                errors.append(f"{label}: '{text}' is not a number")
                return
            if positive and value <= 0:
                errors.append(f"{label}: must be greater than zero")

        _check_number("FPS", self.fps.text())
        _check_number("mm per pixel", self.mm_per_pixel.text(), positive=True)
        _check_number("Speed window (s)", self.speed_window.text(), positive=True)
        _check_number("Walking speed (mm/s)", self.walking_speed.text())
        _check_number("Sleep threshold (min)", self.sleep_threshold.text())

        mn, mx = self.micromove_min.text().strip(), self.micromove_max.text().strip()
        if bool(mn) != bool(mx):
            errors.append("Micro-move speed: set both the minimum and the maximum, or neither")
        elif mn and mx:
            try:
                if float(mn) >= float(mx):
                    errors.append("Micro-move speed: the minimum must be below the maximum")
            except ValueError:
                errors.append(f"Micro-move speed: '{mn}, {mx}' is not a pair of numbers")

        if self.use_facets.isChecked():
            text = self.facet_cutoffs.text().strip()
            if not text:
                errors.append("Facet cutoffs: enter at least one minute boundary, or untick faceting")
            else:
                try:
                    values = [float(x.strip()) for x in text.split(",") if x.strip()]
                except ValueError:
                    errors.append(f"Facet cutoffs: '{text}' is not a comma-separated list of numbers")
                else:
                    if sorted(values) != values:
                        errors.append("Facet cutoffs: values must increase from left to right")
                    if len(set(values)) != len(values):
                        errors.append("Facet cutoffs: values must be distinct")

        idist = self.interaction_distances.text().strip()
        if idist:
            try:
                [float(x.strip()) for x in idist.split(",") if x.strip()]
            except ValueError:
                errors.append(f"Interaction distances: '{idist}' is not a comma-separated list of numbers")

        if self.tracking_rig.currentData() == "movie":
            for label, widget in (("FPS", self.fps), ("mm per pixel", self.mm_per_pixel)):
                if not widget.text().strip():
                    errors.append(f"{label}: required when the rig is Movie (there is no preset to fall back on)")

        return errors

    def dump(self) -> dict:
        g = {
            "tracking_type": self.tracking_type.currentData(),
            "tracking_rig": self.tracking_rig.currentData(),
        }

        factors: dict[str, list[str]] = {}
        for r in range(self.factors_table.rowCount()):
            name_item = self.factors_table.item(r, 0)
            levels_item = self.factors_table.item(r, 1)
            if name_item and name_item.text().strip():
                levels = [
                    l.strip()
                    for l in (levels_item.text() if levels_item else "").split(",")
                    if l.strip()
                ]
                factors[name_item.text().strip()] = levels
        if factors:
            g["experimental_design_factors"] = factors

        if self.use_facets.isChecked() and self.facet_cutoffs.text().strip():
            try:
                g["facet_cutoffs"] = [
                    int(x.strip()) for x in self.facet_cutoffs.text().split(",") if x.strip()
                ]
            except ValueError:
                pass

        def _float(w):
            t = w.text().strip()
            return float(t) if t else None

        for key, fn, widget in [
            ("fps", _float, self.fps),
            ("mm_per_pixel", _float, self.mm_per_pixel),
            ("speed_window_seconds", _float, self.speed_window),
            ("walking_speed_mm_sec", _float, self.walking_speed),
            ("sleep_threshold_min", _float, self.sleep_threshold),
        ]:
            v = fn(widget)
            if v is not None:
                g[key] = v

        mn, mx = self.micromove_min.text().strip(), self.micromove_max.text().strip()
        if mn and mx:
            try:
                g["micromove_speed_mm_sec"] = [float(mn), float(mx)]
            except ValueError:
                pass

        idist = self.interaction_distances.text().strip()
        if idist:
            try:
                g["interaction_distances"] = [
                    float(x.strip()) for x in idist.split(",") if x.strip()
                ]
            except ValueError:
                pass

        return {"global": g}


class TrackingRegionsTab(QWidget):
    """Regions table with one dropdown column per experimental-design factor.

    Columns are rebuilt whenever ``GlobalTab.factorsChanged`` fires. The on-disk
    YAML format is unchanged (``experimental_factors`` is a comma-joined string);
    we map each token to whichever factor's levels it belongs to on load, and
    re-join in factor declaration order on dump.
    """

    _FIXED_LEFT = 1   # "Region name"
    _FIXED_RIGHT = 2  # "X multiplier", "Y multiplier"

    def __init__(self, global_tab: GlobalTab):
        super().__init__()
        self._global_tab = global_tab
        # Current factor → levels mapping driving the dynamic columns.
        self._factors: dict[str, list[str]] = {}

        layout = QVBoxLayout(self)

        info = QLabel(
            "Each row is one tracking region (tube/well). "
            "Pick a level for every experimental-design factor defined on the Global tab."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add region")
        add_btn.clicked.connect(lambda: self._add_row())
        rm_btn = QPushButton("Remove selected")
        rm_btn.clicked.connect(self._remove_row)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 200)
        self.count_spin.setValue(24)
        bulk_btn = QPushButton("Generate N regions")
        bulk_btn.clicked.connect(self._bulk_generate)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rm_btn)
        btn_row.addStretch()
        btn_row.addWidget(QLabel("N:"))
        btn_row.addWidget(self.count_spin)
        btn_row.addWidget(bulk_btn)
        layout.addLayout(btn_row)

        self.table = QTableWidget(0, self._FIXED_LEFT + self._FIXED_RIGHT)
        layout.addWidget(self.table)

        # Pull initial factor list (will be empty until GlobalTab loads), then
        # listen for changes so columns track factor edits live.
        self._factors = self._global_tab.get_factors()
        self._apply_columns()
        self._global_tab.factorsChanged.connect(self._on_factors_changed)

    # ------------------------------------------------------------------
    # Column management
    # ------------------------------------------------------------------

    def _factor_names(self) -> list[str]:
        return list(self._factors.keys())

    def _x_col(self) -> int:
        return self._FIXED_LEFT + len(self._factors)

    def _y_col(self) -> int:
        return self._x_col() + 1

    def _apply_columns(self) -> None:
        """Set the table headers + resize modes for the current factor list."""
        headers = ["Region name"] + self._factor_names() + ["X multiplier", "Y multiplier"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for i in range(len(self._factors)):
            h.setSectionResizeMode(self._FIXED_LEFT + i, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(self._x_col(), QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._y_col(), QHeaderView.ResizeMode.ResizeToContents)

    def _on_factors_changed(self, factors: dict[str, list[str]]) -> None:
        """Rebuild columns + cells when the Global tab's factors change."""
        # Snapshot using the *old* factor list, then swap and re-render.
        snapshot = self._snapshot_rows()
        self._factors = factors
        self._apply_columns()
        self.table.setRowCount(0)
        for row in snapshot:
            self._add_row(
                name=row["name"],
                factor_values=row["factors"],
                x=row["x"],
                y=row["y"],
            )

    def _snapshot_rows(self) -> list[dict]:
        """Capture current row state, keyed by factor name (so renames drop cleanly)."""
        rows: list[dict] = []
        prev_factor_names = self._factor_names()
        prev_x = self._FIXED_LEFT + len(prev_factor_names)
        prev_y = prev_x + 1
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 0)
            name = name_item.text() if name_item else ""
            factor_values: dict[str, str] = {}
            for i, fname in enumerate(prev_factor_names):
                w = self.table.cellWidget(r, self._FIXED_LEFT + i)
                if w is not None:
                    factor_values[fname] = w.currentText()
            xw = self.table.cellWidget(r, prev_x)
            yw = self.table.cellWidget(r, prev_y)
            rows.append({
                "name": name,
                "factors": factor_values,
                "x": xw.currentText() if xw else "1",
                "y": yw.currentText() if yw else "1",
            })
        return rows

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------

    def _add_row(
        self,
        name: str = "",
        factor_values: dict[str, str] | None = None,
        x: str | int = 1,
        y: str | int = 1,
    ) -> None:
        factor_values = factor_values or {}
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name or f"T_{r}"))
        for i, (fname, levels) in enumerate(self._factors.items()):
            combo = _NoScrollComboBox()
            combo.addItem("")  # blank = unset
            combo.addItems([str(l) for l in levels])
            current = factor_values.get(fname, "")
            idx = combo.findText(current, Qt.MatchFlag.MatchFixedString)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.table.setCellWidget(r, self._FIXED_LEFT + i, combo)
        xc = _NoScrollComboBox()
        xc.addItems(["1", "-1"])
        xc.setCurrentText(str(x))
        yc = _NoScrollComboBox()
        yc.addItems(["1", "-1"])
        yc.setCurrentText(str(y))
        self.table.setCellWidget(r, self._x_col(), xc)
        self.table.setCellWidget(r, self._y_col(), yc)

    def _remove_row(self) -> None:
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)

    def _bulk_generate(self) -> None:
        self.table.setRowCount(0)
        n = self.count_spin.value()
        for i in range(n):
            self._add_row(name=f"T_{i}")

    # ------------------------------------------------------------------
    # Load / dump
    # ------------------------------------------------------------------

    def _split_factor_string(self, s: str) -> dict[str, str]:
        """Map each token in a comma-list to the factor whose levels it belongs to."""
        out: dict[str, str] = {}
        if not s:
            return out
        tokens = [t.strip() for t in s.split(",") if t.strip()]
        for tok in tokens:
            for fname, levels in self._factors.items():
                if fname in out:
                    continue  # already filled, don't overwrite
                if tok in levels:
                    out[fname] = tok
                    break
        return out

    def load(self, config: dict) -> None:
        # Re-sync factor columns from the current Global tab, in case load
        # order put us ahead of factorsChanged.
        self._factors = self._global_tab.get_factors()
        self._apply_columns()
        self.table.setRowCount(0)
        for name, data in config.get("tracking_regions", {}).items():
            ef = data.get("experimental_factors", "")
            factor_values = self._split_factor_string(str(ef))
            self._add_row(
                name=name,
                factor_values=factor_values,
                x=data.get("x_location_multiplier", 1),
                y=data.get("y_location_multiplier", 1),
            )

    def dump(self) -> dict:
        regions: dict[str, dict] = {}
        factor_names = self._factor_names()
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 0)
            if not (name_item and name_item.text().strip()):
                continue
            parts: list[str] = []
            for i, _fname in enumerate(factor_names):
                w = self.table.cellWidget(r, self._FIXED_LEFT + i)
                val = w.currentText().strip() if w else ""
                if val:
                    parts.append(val)
            xw = self.table.cellWidget(r, self._x_col())
            yw = self.table.cellWidget(r, self._y_col())
            regions[name_item.text().strip()] = {
                "experimental_factors": ", ".join(parts),
                "x_location_multiplier": int(xw.currentText()) if xw else 1,
                "y_location_multiplier": int(yw.currentText()) if yw else 1,
            }
        return {"tracking_regions": regions} if regions else {}


class CountingRegionsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        info = QLabel(
            "Each row defines a treatment and the strings that identify it in the "
            "tracking data file's counting_region column. Any value in that column "
            "matching one of the aliases (comma-separated) is mapped to the "
            "treatment label. Example: a row with label \"Light\" and aliases "
            "\"Light, LL, L\" assigns the \"Light\" treatment to every data row "
            "whose counting_region is Light, LL, or L."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add region")
        add_btn.clicked.connect(self._add_row)
        rm_btn = QPushButton("Remove selected")
        rm_btn.clicked.connect(self._remove_row)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rm_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Treatment label", "Aliases (comma-separated)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

    def _add_row(self, label: str = "", aliases: str = "") -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(label))
        self.table.setItem(r, 1, QTableWidgetItem(aliases))

    def _remove_row(self) -> None:
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)

    def load(self, config: dict) -> None:
        self.table.setRowCount(0)
        for label, data in config.get("counting_regions", {}).items():
            self._add_row(label=label, aliases=data.get("alias", ""))

    def dump(self) -> dict:
        regions: dict[str, dict] = {}
        for r in range(self.table.rowCount()):
            label_item = self.table.item(r, 0)
            aliases_item = self.table.item(r, 1)
            if label_item and label_item.text().strip():
                regions[label_item.text().strip()] = {
                    "alias": aliases_item.text().strip() if aliases_item else ""
                }
        return {"counting_regions": regions} if regions else {}
