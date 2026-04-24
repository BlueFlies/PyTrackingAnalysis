"""Form-based editors for each top-level YAML section.

Ported verbatim from ``config_ui.py`` so the visual layout matches the
legacy editor.  The wrapping :class:`~pytrackinganalysis.apps.config_editor.ConfigEditorWindow`
is responsible for the surrounding pyflic-style chrome (TopBar, Cards,
YAML preview, Script Editor launcher).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


TRACKING_TYPES = [
    "TRACKER", "TWOCHOICETRACKER", "XCHOICETRACKER", "DDROPTRACKER",
    "PAIRWISEINTERACTIONTRACKER", "CENTROPHOBISMTRACKER",
    "COUNTER", "TWOCHOICECOUNTER", "PAIRWISEINTERACTIONCOUNTER",
]
TRACKING_RIGS = ["small_arena", "arena_max", "colosseum", "obscura", "movie"]


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    font = QFont()
    font.setBold(True)
    lbl.setFont(font)
    return lbl


class GlobalTab(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.tracking_type = QComboBox()
        self.tracking_type.addItems(TRACKING_TYPES)
        form.addRow("Tracking type:", self.tracking_type)

        self.tracking_rig = QComboBox()
        self.tracking_rig.addItems(TRACKING_RIGS)
        self.tracking_rig.currentTextChanged.connect(self._on_rig_changed)
        form.addRow("Tracking rig:", self.tracking_rig)

        outer.addLayout(form)

        outer.addSpacing(12)
        outer.addWidget(_section_label("Experimental design factors"))

        self.factors_table = QTableWidget(0, 2)
        self.factors_table.setHorizontalHeaderLabels(["Factor name", "Levels (comma-separated)"])
        self.factors_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.factors_table.setMaximumHeight(160)
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

    def _on_rig_changed(self, rig: str) -> None:
        movie = rig == "movie"
        self.fps.setEnabled(movie)
        self.mm_per_pixel.setEnabled(movie)
        if not movie:
            self.fps.clear()
            self.mm_per_pixel.clear()

    def _on_facet_toggled(self, state) -> None:
        self.facet_cutoffs.setEnabled(bool(state))

    def _add_factor_row(self) -> None:
        r = self.factors_table.rowCount()
        self.factors_table.insertRow(r)

    def _remove_factor_row(self) -> None:
        rows = {idx.row() for idx in self.factors_table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.factors_table.removeRow(r)

    def load(self, config: dict) -> None:
        g = config.get("global", {})

        tt = g.get("tracking_type", "TRACKER")
        idx = self.tracking_type.findText(tt, Qt.MatchFlag.MatchFixedString)
        self.tracking_type.setCurrentIndex(max(idx, 0))

        rig = g.get("tracking_rig", "small_arena")
        idx = self.tracking_rig.findText(
            rig, Qt.MatchFlag.MatchFixedString | Qt.MatchFlag.MatchCaseSensitive
        )
        if idx < 0:
            idx = self.tracking_rig.findText(rig, Qt.MatchFlag.MatchFixedString)
        self.tracking_rig.setCurrentIndex(max(idx, 0))

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

    def dump(self) -> dict:
        g = {
            "tracking_type": self.tracking_type.currentText(),
            "tracking_rig": self.tracking_rig.currentText(),
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
    def __init__(self, global_tab: GlobalTab):
        super().__init__()
        self._global_tab = global_tab
        layout = QVBoxLayout(self)

        info = QLabel(
            "Each row is one tracking region (tube/well). "
            "Experimental factors must match the factor levels defined on the Global tab."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add region")
        add_btn.clicked.connect(self._add_row)
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

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Region name", "Experimental factors", "X multiplier", "Y multiplier"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

    def _add_row(self, name: str = "", factors: str = "", x: int = 1, y: int = 1) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name or f"T_{r}"))
        self.table.setItem(r, 1, QTableWidgetItem(factors))
        xc = QComboBox()
        xc.addItems(["1", "-1"])
        xc.setCurrentText(str(x))
        yc = QComboBox()
        yc.addItems(["1", "-1"])
        yc.setCurrentText(str(y))
        self.table.setCellWidget(r, 2, xc)
        self.table.setCellWidget(r, 3, yc)

    def _remove_row(self) -> None:
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)

    def _bulk_generate(self) -> None:
        self.table.setRowCount(0)
        n = self.count_spin.value()
        for i in range(n):
            self._add_row(name=f"T_{i}")

    def load(self, config: dict) -> None:
        self.table.setRowCount(0)
        for name, data in config.get("tracking_regions", {}).items():
            self._add_row(
                name=name,
                factors=data.get("experimental_factors", ""),
                x=data.get("x_location_multiplier", 1),
                y=data.get("y_location_multiplier", 1),
            )

    def dump(self) -> dict:
        regions: dict[str, dict] = {}
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 0)
            factors_item = self.table.item(r, 1)
            xw = self.table.cellWidget(r, 2)
            yw = self.table.cellWidget(r, 3)
            if name_item and name_item.text().strip():
                regions[name_item.text().strip()] = {
                    "experimental_factors": factors_item.text().strip() if factors_item else "",
                    "x_location_multiplier": int(xw.currentText()) if xw else 1,
                    "y_location_multiplier": int(yw.currentText()) if yw else 1,
                }
        return {"tracking_regions": regions} if regions else {}


class CountingRegionsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        info = QLabel(
            "Counting regions map region names in the data file to treatment labels. "
            "Each row defines one treatment and the aliases that refer to it (comma-separated)."
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
