"""Create Experiment wizard.

A dialog (launched from the Hub's project card) that creates a new project from
an Experiment Type: it collects the type, location, rig, optional facets and
design factors, then writes a ready-to-edit ``tracking_config.yaml`` and the
``data/``/``analysis/``/``qc/`` folders.

The config assembly lives in each Experiment Type's ``build_config`` (so the
Valence plate/multipliers/aliases stay with the type); this module only gathers
inputs and does the filesystem work. ``create_project`` and
``ConfigureExperimentDialog.build_config`` are Qt-light / Qt-free so they can be
unit-tested without driving a modal dialog.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import experiment_types as _et
from ..io_utils import atomic_write_text
from ._config_tabs import TRACKING_RIGS, TRACKING_TYPES, _find_data


def create_project(parent_dir, name: str, config: dict) -> Path:
    """Create a new project directory ``<parent>/<name>/`` and write *config*.

    Makes the project folder plus its ``data/``, ``analysis/``, ``qc/``
    subdirectories and writes ``tracking_config.yaml`` into it. Returns the path
    to the written config. Raises ``FileExistsError`` if the project folder
    already exists (so an existing experiment is never overwritten).
    """
    project = Path(parent_dir) / name
    if project.exists():
        raise FileExistsError(f"'{project}' already exists.")
    (project / "data").mkdir(parents=True, exist_ok=False)
    (project / "analysis").mkdir(exist_ok=True)
    (project / "qc").mkdir(exist_ok=True)
    config_path = project / "tracking_config.yaml"
    atomic_write_text(
        config_path,
        lambda handle: yaml.dump(config, handle, default_flow_style=False,
                                 allow_unicode=True, sort_keys=False),
    )
    return config_path


def _parse_cutoffs(text: str):
    """Parse a 'facets' field into a list of numbers, or None when blank.

    Raises ValueError on non-numeric input.
    """
    text = (text or "").strip()
    if not text:
        return None
    return [int(p) if float(p) == int(float(p)) else float(p)
            for p in (x.strip() for x in text.split(",")) if p]


def _parse_labels(text: str):
    """Parse a phase-names field into a list of names, or None when blank."""
    names = [p for p in (x.strip() for x in (text or "").split(",")) if p]
    return names or None


class ConfigureExperimentDialog(QDialog):
    """Collects new-project inputs and writes the config on accept."""

    def __init__(self, parent=None, start_dir: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create project")
        self.setMinimumWidth(560)
        self._created_path: Path | None = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.type_combo = QComboBox()
        for t in _et.available_experiment_types():
            self.type_combo.addItem(t.display_name, t.name)
        form.addRow("Experiment type:", self.type_combo)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("new project folder name")
        form.addRow("Project name:", self.name_edit)

        self.dir_edit = QLineEdit(str(start_dir or ""))
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setPlaceholderText("where to create the project folder")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(browse)
        dir_wrap = QWidget()
        dir_wrap.setLayout(dir_row)
        form.addRow("Create in:", dir_wrap)

        self.tracking_type_combo = QComboBox()
        for label, value in TRACKING_TYPES:
            self.tracking_type_combo.addItem(label, value)
        form.addRow("Tracking type:", self.tracking_type_combo)

        self.rig_combo = QComboBox()
        form.addRow("Tracking rig:", self.rig_combo)

        self.facets_edit = QLineEdit("10, 70")
        self.facets_edit.setPlaceholderText("e.g. 10, 70  (blank = no faceting)")
        form.addRow("Facet cutoffs:", self.facets_edit)

        # Phase names only exist when there are facets, so the field follows
        # the cutoffs field: blank cutoffs = nothing to name = disabled.
        self.facet_labels_edit = QLineEdit()
        self.facet_labels_edit.setPlaceholderText(
            "e.g. Acclimation, Experiment, Cooldown  (optional)")
        self.facets_edit.textChanged.connect(
            lambda text: self.facet_labels_edit.setEnabled(bool(text.strip())))
        self.facet_labels_edit.setEnabled(bool(self.facets_edit.text().strip()))
        form.addRow("Phase names:", self.facet_labels_edit)

        outer.addLayout(form)

        outer.addWidget(QLabel("Experimental design factors (optional):"))
        self.factors_table = QTableWidget(0, 2)
        self.factors_table.setHorizontalHeaderLabels(
            ["Factor name", "Levels (comma-separated)"])
        self.factors_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.factors_table.setMaximumHeight(140)
        outer.addWidget(self.factors_table)
        frow = QHBoxLayout()
        add_f = QPushButton("Add factor")
        add_f.clicked.connect(lambda: self.factors_table.insertRow(self.factors_table.rowCount()))
        rm_f = QPushButton("Remove selected")
        rm_f.clicked.connect(self._remove_factor)
        frow.addWidget(add_f)
        frow.addWidget(rm_f)
        frow.addStretch(1)
        outer.addLayout(frow)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._on_type_changed()

    # ---- helpers ------------------------------------------------------

    def current_type(self):
        return _et.get_experiment_type(self.type_combo.currentData())

    def _browse(self) -> None:
        start = self.dir_edit.text() or ""
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose where to create the project", start)
        if chosen:
            self.dir_edit.setText(chosen)

    def _remove_factor(self) -> None:
        rows = {idx.row() for idx in self.factors_table.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.factors_table.removeRow(r)

    def _on_type_changed(self) -> None:
        t = self.current_type()
        custom = t.is_custom
        self.tracking_type_combo.setEnabled(custom)
        if not custom:
            idx = _find_data(self.tracking_type_combo, t.tracking_type.name)
            if idx >= 0:
                self.tracking_type_combo.setCurrentIndex(idx)
        # Constrain the rig list to the type's allowed set.
        allowed = list(t.allowed_rigs) if t.allowed_rigs is not None \
            else [value for _label, value in TRACKING_RIGS]
        keep = self.rig_combo.currentData()
        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()
        labels = {value: label for label, value in TRACKING_RIGS}
        for value in allowed:
            self.rig_combo.addItem(labels.get(value, value), value)
        idx = _find_data(self.rig_combo, keep)
        self.rig_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.rig_combo.blockSignals(False)
        # Facets default from the type (10, 70 for Valence), as do the phase
        # names (Acclimation, Experiment, Cooldown for Valence).
        if t.facet_cutoffs is not None:
            self.facets_edit.setText(", ".join(str(c) for c in t.facet_cutoffs))
        self.facet_labels_edit.setText(", ".join(t.phase_labels) if t.phase_labels else "")

    def factors(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for r in range(self.factors_table.rowCount()):
            name_item = self.factors_table.item(r, 0)
            levels_item = self.factors_table.item(r, 1)
            if name_item and name_item.text().strip():
                levels = [x.strip() for x in
                          (levels_item.text() if levels_item else "").split(",") if x.strip()]
                out[name_item.text().strip()] = levels
        return out

    def build_config(self) -> dict:
        """Assemble the config dict from the current field values."""
        t = self.current_type()
        return t.build_config(
            tracking_type=self.tracking_type_combo.currentData(),
            rig=self.rig_combo.currentData(),
            facet_cutoffs=_parse_cutoffs(self.facets_edit.text()),
            facet_labels=_parse_labels(self.facet_labels_edit.text()),
            factors=self.factors() or None,
        )

    @property
    def created_path(self) -> Path | None:
        return self._created_path

    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()
        parent = self.dir_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Create project", "Enter a project name.")
            return
        if not parent:
            QMessageBox.warning(self, "Create project",
                                "Choose where to create the project.")
            return
        try:
            cutoffs = _parse_cutoffs(self.facets_edit.text())  # validate only
        except ValueError:
            QMessageBox.warning(self, "Create project",
                                "Facet cutoffs must be numbers, comma-separated (or blank).")
            return
        names = _parse_labels(self.facet_labels_edit.text())
        if cutoffs and names and len(names) != len(cutoffs) + 1:
            QMessageBox.warning(
                self, "Create project",
                f"{len(cutoffs)} facet cutoffs create {len(cutoffs) + 1} phases, "
                f"so give {len(cutoffs) + 1} phase names (or leave them blank); "
                f"got {len(names)}.")
            return
        try:
            self._created_path = create_project(parent, name, self.build_config())
        except FileExistsError:
            QMessageBox.warning(self, "Create project",
                                f"A folder named '{name}' already exists there.")
            return
        except Exception as err:  # noqa: BLE001
            QMessageBox.critical(self, "Create project", f"Could not create:\n{err}")
            return
        self.accept()
