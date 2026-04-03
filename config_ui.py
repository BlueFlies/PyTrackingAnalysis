"""
config_ui.py – PyQt6 UI for creating / editing tracking_config.yaml
"""

import sys
import os
import yaml

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QPushButton, QFileDialog, QMessageBox,
    QScrollArea, QGroupBox, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


TRACKING_TYPES = [
    "TRACKER", "TWOCHOICETRACKER", "XCHOICETRACKER", "DDROPTRACKER",
    "PAIRWISEINTERACTIONTRACKER", "CENTROPHOBISMTRACKER",
    "COUNTER", "TWOCHOICECOUNTER", "PAIRWISEINTERACTIONCOUNTER",
]
TRACKING_RIGS = ["small_arena", "arena_max", "colosseum", "obscura", "movie"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section_label(text):
    lbl = QLabel(text)
    font = QFont()
    font.setBold(True)
    lbl.setFont(font)
    return lbl


# ---------------------------------------------------------------------------
# Tab 1 – Global settings
# ---------------------------------------------------------------------------

class GlobalTab(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignTop)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Tracking type
        self.tracking_type = QComboBox()
        self.tracking_type.addItems(TRACKING_TYPES)
        form.addRow("Tracking type:", self.tracking_type)

        # Tracking rig
        self.tracking_rig = QComboBox()
        self.tracking_rig.addItems(TRACKING_RIGS)
        self.tracking_rig.currentTextChanged.connect(self._on_rig_changed)
        form.addRow("Tracking rig:", self.tracking_rig)

        outer.addLayout(form)

        # ── Experimental design factors ─────────────────────────────────
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

        # ── Facet cutoffs ───────────────────────────────────────────────
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

        # ── Optional parameter overrides ────────────────────────────────
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

    # ── slots ──────────────────────────────────────────────────────────

    def _on_rig_changed(self, rig):
        movie = rig == "movie"
        self.fps.setEnabled(movie)
        self.mm_per_pixel.setEnabled(movie)
        if not movie:
            self.fps.clear()
            self.mm_per_pixel.clear()

    def _on_facet_toggled(self, state):
        self.facet_cutoffs.setEnabled(bool(state))

    def _add_factor_row(self):
        r = self.factors_table.rowCount()
        self.factors_table.insertRow(r)

    def _remove_factor_row(self):
        rows = {idx.row() for idx in self.factors_table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.factors_table.removeRow(r)

    # ── load / dump ────────────────────────────────────────────────────

    def load(self, config):
        g = config.get("global", {})

        tt = g.get("tracking_type", "TRACKER")
        idx = self.tracking_type.findText(tt, Qt.MatchFlag.MatchFixedString)
        self.tracking_type.setCurrentIndex(max(idx, 0))

        rig = g.get("tracking_rig", "small_arena")
        idx = self.tracking_rig.findText(rig, Qt.MatchFlag.MatchFixedString | Qt.MatchFlag.MatchCaseSensitive)
        if idx < 0:
            # case-insensitive fallback
            idx = self.tracking_rig.findText(rig, Qt.MatchFlag.MatchFixedString)
        self.tracking_rig.setCurrentIndex(max(idx, 0))

        # factors
        self.factors_table.setRowCount(0)
        for name, levels in g.get("experimental_design_factors", {}).items():
            r = self.factors_table.rowCount()
            self.factors_table.insertRow(r)
            self.factors_table.setItem(r, 0, QTableWidgetItem(name))
            self.factors_table.setItem(r, 1, QTableWidgetItem(", ".join(str(l) for l in levels)))

        # facets
        cutoffs = g.get("facet_cutoffs")
        if cutoffs:
            self.use_facets.setChecked(True)
            self.facet_cutoffs.setText(", ".join(str(c) for c in cutoffs))
        else:
            self.use_facets.setChecked(False)
            self.facet_cutoffs.clear()

        # overrides
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

    def dump(self):
        g = {
            "tracking_type": self.tracking_type.currentText(),
            "tracking_rig": self.tracking_rig.currentText(),
        }

        # factors
        factors = {}
        for r in range(self.factors_table.rowCount()):
            name_item = self.factors_table.item(r, 0)
            levels_item = self.factors_table.item(r, 1)
            if name_item and name_item.text().strip():
                levels = [l.strip() for l in (levels_item.text() if levels_item else "").split(",") if l.strip()]
                factors[name_item.text().strip()] = levels
        if factors:
            g["experimental_design_factors"] = factors

        # facets
        if self.use_facets.isChecked() and self.facet_cutoffs.text().strip():
            try:
                g["facet_cutoffs"] = [int(x.strip()) for x in self.facet_cutoffs.text().split(",") if x.strip()]
            except ValueError:
                pass

        # overrides
        def _float(w):
            t = w.text().strip()
            return float(t) if t else None

        def _int(w):
            t = w.text().strip()
            return int(t) if t else None

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
                g["interaction_distances"] = [float(x.strip()) for x in idist.split(",") if x.strip()]
            except ValueError:
                pass

        return {"global": g}


# ---------------------------------------------------------------------------
# Tab 2 – Tracking regions
# ---------------------------------------------------------------------------

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

        # toolbar
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
        self.table.setHorizontalHeaderLabels([
            "Region name", "Experimental factors", "X multiplier", "Y multiplier"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

    def _add_row(self, name="", factors="", x=1, y=1):
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

    def _remove_row(self):
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)

    def _bulk_generate(self):
        self.table.setRowCount(0)
        n = self.count_spin.value()
        for i in range(n):
            self._add_row(name=f"T_{i}")

    def load(self, config):
        self.table.setRowCount(0)
        for name, data in config.get("tracking_regions", {}).items():
            self._add_row(
                name=name,
                factors=data.get("experimental_factors", ""),
                x=data.get("x_location_multiplier", 1),
                y=data.get("y_location_multiplier", 1),
            )

    def dump(self):
        regions = {}
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


# ---------------------------------------------------------------------------
# Tab 3 – Counting regions
# ---------------------------------------------------------------------------

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

    def _add_row(self, label="", aliases=""):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(label))
        self.table.setItem(r, 1, QTableWidgetItem(aliases))

    def _remove_row(self):
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.table.removeRow(r)

    def load(self, config):
        self.table.setRowCount(0)
        for label, data in config.get("counting_regions", {}).items():
            self._add_row(label=label, aliases=data.get("alias", ""))

    def dump(self):
        regions = {}
        for r in range(self.table.rowCount()):
            label_item = self.table.item(r, 0)
            aliases_item = self.table.item(r, 1)
            if label_item and label_item.text().strip():
                regions[label_item.text().strip()] = {
                    "alias": aliases_item.text().strip() if aliases_item else ""
                }
        return {"counting_regions": regions} if regions else {}


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class ConfigWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tracking Config Editor")
        self.resize(800, 650)
        self._current_path = None

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # ── file bar ───────────────────────────────────────────────────
        file_bar = QHBoxLayout()
        self.path_label = QLabel("No file loaded")
        self.path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        open_btn = QPushButton("Open…")
        open_btn.clicked.connect(self.open_file)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_file)
        save_as_btn = QPushButton("Save as…")
        save_as_btn.clicked.connect(self.save_as_file)
        file_bar.addWidget(self.path_label)
        file_bar.addWidget(open_btn)
        file_bar.addWidget(save_btn)
        file_bar.addWidget(save_as_btn)
        main_layout.addLayout(file_bar)

        # ── tabs ───────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.global_tab = GlobalTab()
        self.tracking_tab = TrackingRegionsTab(self.global_tab)
        self.counting_tab = CountingRegionsTab()
        self.tabs.addTab(self.global_tab, "Global")
        self.tabs.addTab(self.tracking_tab, "Tracking regions")
        self.tabs.addTab(self.counting_tab, "Counting regions")
        main_layout.addWidget(self.tabs)

    # ── file I/O ───────────────────────────────────────────────────────

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open config", "", "YAML files (*.yaml *.yml);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path) as f:
                config = yaml.safe_load(f)
            self._load_config(config)
            self._current_path = path
            self.path_label.setText(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load file:\n{e}")

    def save_file(self):
        if not self._current_path:
            self.save_as_file()
            return
        self._write(self._current_path)

    def save_as_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save config", "tracking_config.yaml",
            "YAML files (*.yaml *.yml);;All files (*)"
        )
        if path:
            self._write(path)
            self._current_path = path
            self.path_label.setText(path)

    def _write(self, path):
        try:
            config = self._dump_config()
            with open(path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            QMessageBox.information(self, "Saved", f"Config saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")

    def _load_config(self, config):
        self.global_tab.load(config)
        self.tracking_tab.load(config)
        self.counting_tab.load(config)

    def _dump_config(self):
        config = {}
        config.update(self.global_tab.dump())
        config.update(self.tracking_tab.dump())
        config.update(self.counting_tab.dump())
        return config


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    win = ConfigWindow()

    # auto-load tracking_config.yaml from the script's directory if present
    default = os.path.join(os.path.dirname(__file__), "tracking_config.yaml")
    if os.path.exists(default):
        try:
            with open(default) as f:
                config = yaml.safe_load(f)
            win._load_config(config)
            win._current_path = default
            win.path_label.setText(default)
        except Exception:
            pass

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
