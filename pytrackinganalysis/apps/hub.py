"""Analysis Hub — the main entry point for PyTrackingAnalysis.

Loads a tracking experiment, exposes single + batch analyses and per
tracking-type plot actions as category-coloured buttons, routes figures
and logs to a tabbed :class:`~pytrackinganalysis.ui.widgets.PlotDock`, and
launches the Config Editor and QC Viewer apps in their own subprocesses.

Modelled on pyflic's ``base/analysis_hub.py``; see the plan file for the
card-by-card breakdown.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

# Force a non-GUI matplotlib backend before the domain layer imports pyplot.
import matplotlib

matplotlib.use("Agg")

from PyQt6.QtCore import QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import Experiment as ExperimentMod
from ..help import HelpButton, make_topbar_help_button
from ..ui import (
    ActionButton,
    Card,
    Category,
    OutputLog,
    PlotDock,
    SidebarNav,
    TopBar,
    ZoomableImageView,
    ZoomableTextView,
    app_icon,
    apply_theme,
    icon,
    resolved_mode,
)
from ..ui import settings as ui_settings
from .common import TaskWorker, capture_figures, shutdown_worker


# Lines like "Saved: /path/to/file.png" come out of the various Experiment
# methods that write artifacts to disk. We mirror them as zoomable PlotDock
# tabs in the Hub.
_SAVED_RE = re.compile(r"^\s*Saved:\s+(\S.*?)\s*$")

# The only config file ``Experiment.__init__`` ever opens — it takes a project
# directory and joins this name onto it, with no parameter to override it.
_CANONICAL_CONFIG = "tracking_config.yaml"


# Per-tracking-type plot buttons for the Plots card. Each entry is
# (label, flat_method, facet_method); the Hub picks the variant based on the
# Analyze card's facet checkbox and updates button labels accordingly.
_PLOT_BUTTONS: dict[str, list[tuple[str, str, str]]] = {
    "TRACKER": [
        ("Total distance", "plot_totaldistance", "plot_totaldistance_facet"),
    ],
    "TWOCHOICETRACKER": [
        ("PI", "plot_pi", "plot_pi_facet"),
        ("Percentage", "plot_percentage", "plot_percentage_facet"),
        ("Transitions", "plot_transitions", "plot_transitions_facet"),
        ("Total distance", "plot_totaldistance", "plot_totaldistance_facet"),
    ],
    "TWOCHOICECOUNTER": [
        ("PI", "plot_pi", "plot_pi_facet"),
        ("Percentage", "plot_percentage", "plot_percentage_facet"),
    ],
    "XCHOICETRACKER": [
        ("Adjusted X position", "plot_adjusted_x_position", "plot_adjusted_x_position_facet"),
        ("Total distance", "plot_totaldistance", "plot_totaldistance_facet"),
    ],
    "PAIRWISEINTERACTIONTRACKER": [
        ("Interactions", "plot_interactions", "plot_interactions_facet"),
        ("Total distance", "plot_totaldistance", "plot_totaldistance_facet"),
    ],
    "PAIRWISEINTERACTIONCOUNTER": [
        ("Interactions", "plot_interactions", "plot_interactions_facet"),
    ],
}

_PLOT_ICON_BY_LABEL: dict[str, str] = {
    "Total distance": "distance",
    "PI": "plot",
    "Percentage": "plot",
    "Transitions": "transition",
    "Adjusted X position": "xy",
    "Interactions": "plot",
}


class HubWindow(QMainWindow):
    """The Analysis Hub main window."""

    def __init__(self, initial_project: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("PyTrackingAnalysis — Analysis Hub")
        self.resize(1350, 860)

        self._exp: ExperimentMod.Experiment | None = None
        self._project_dir: Path | None = None
        self._worker: TaskWorker | None = None
        # (app_name, Popen) for child apps launched from the Tools card. They run
        # independently of the Hub; tracked only so an immediate failure is visible.
        self._subapps: list[tuple[str, object]] = []
        # Maps a Plots-card ActionButton to its Arena method name; rebuilt whenever
        # an experiment is loaded so the buttons always reflect the tracking type.
        self._plot_buttons: list[ActionButton] = []
        # Cards we reference by sidebar key so clicking a sidebar item scrolls to it.
        self._cards: dict[str, Card] = {}
        self._scripts: list[dict] = []
        # Resolved artifact path → tab widget. Used to deduplicate tabs when
        # the same file is re-saved by a subsequent task run. Stored by widget
        # (not index) so it survives the user closing other tabs.
        self._artifact_tabs: dict[str, QWidget] = {}

        self._build_ui()

        if initial_project:
            self._set_project_dir(initial_project)

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Top bar ─────────────────────────────────────────────────────
        self._top_bar = TopBar("PyTrackingAnalysis — Analysis Hub")
        self._interactive_checkbox = QCheckBox("Interactive plots")
        self._interactive_checkbox.setToolTip(
            "When checked, figures embed as live matplotlib canvases with "
            "zoom/pan/save toolbars. When unchecked, they render as static "
            "PNGs (faster)."
        )
        self._top_bar.add_right(self._interactive_checkbox)
        self._top_bar.add_right(make_topbar_help_button(self, topic_id="getting_started"))
        self._btn_theme = QToolButton()
        self._btn_theme.setIcon(
            icon("theme_dark" if resolved_mode() == "light" else "theme_light")
        )
        self._btn_theme.setIconSize(QSize(18, 18))
        self._btn_theme.setAutoRaise(True)
        self._btn_theme.setToolTip("Toggle light / dark theme")
        self._btn_theme.clicked.connect(self._toggle_theme)
        self._top_bar.add_right(self._btn_theme)
        outer.addWidget(self._top_bar)

        # ── Splitter ────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: sidebar + scrollable card column
        left_host = QWidget()
        left_lay = QHBoxLayout(left_host)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        self._sidebar = SidebarNav()
        self._sidebar.add_item("project", "Project", "project", category=Category.NEUTRAL)
        # A rail button (not a scroll anchor): create a new project from a type.
        create_proj_btn = self._sidebar.add_action(
            "Create project", "new", category=Category.LOAD,
            tooltip="Create a new project from an Experiment Type")
        create_proj_btn.clicked.connect(lambda: self._create_experiment())
        self._sidebar.add_item("load", "Load", "load", category=Category.LOAD)
        self._sidebar.add_item("analyze", "Analyze", "basic", category=Category.ANALYZE)
        self._sidebar.add_item("plots", "Plots", "plots", category=Category.PLOTS)
        self._sidebar.add_item("scripts", "Scripts", "scripts", category=Category.SCRIPTS)
        self._sidebar.add_item("ai", "AI", "ai", category=Category.AI)
        self._sidebar.add_item("tools", "Tools", "tools", category=Category.TOOLS)
        self._sidebar.add_stretch()
        self._sidebar.itemSelected.connect(self._scroll_to_card)
        left_lay.addWidget(self._sidebar)

        # Scrollable cards column
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        cards_host = QWidget()
        self._cards_lay = QVBoxLayout(cards_host)
        self._cards_lay.setContentsMargins(12, 12, 12, 12)
        self._cards_lay.setSpacing(12)

        self._build_project_card()
        self._build_load_card()
        self._build_analyze_card()
        self._build_plots_card()
        self._build_scripts_card()
        self._build_ai_card()
        self._build_tools_card()
        self._cards_lay.addStretch(1)

        scroll.setWidget(cards_host)
        left_lay.addWidget(scroll, 1)
        # 180px sidebar + ~420px cards column so the form rows + button
        # clusters never get clipped behind the splitter handle.
        left_host.setMinimumWidth(600)
        splitter.addWidget(left_host)

        # Right: plot dock
        self._log = OutputLog()
        self._err_log = OutputLog()
        self._plot_dock = PlotDock(self._log, self._err_log)
        self._plot_dock.setMinimumWidth(420)
        splitter.addWidget(self._plot_dock)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([620, 730])

        outer.addWidget(splitter, 1)

        # Progress bar (hidden until a task runs)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(4)
        outer.addWidget(self._progress)

        self._log.append_line(
            "Welcome to PyTrackingAnalysis. Pick a project directory under "
            "Project → Load, then click 'Load experiment'."
        )

    # ---------------- Project card ----------------

    def _build_project_card(self) -> None:
        card = Card(
            "Project",
            category=Category.NEUTRAL,
            subtitle="Pick the experiment folder and its config file.",
            icon_name="project",
        )
        card.add_title_widget(
            HelpButton(
                "project_structure",
                tooltip="Project directory layout and naming rules",
            )
        )
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._project_edit = QLineEdit()
        self._project_edit.setPlaceholderText("/path/to/experiment/folder")
        self._project_edit.setReadOnly(True)
        browse = ActionButton("Browse…", Category.NEUTRAL, icon_name="browse")
        browse.clicked.connect(self._pick_project_dir)
        reload_btn = ActionButton("Reload", Category.TOOLS, icon_name="clear")
        reload_btn.clicked.connect(self._reload_project)
        # Path on its own line so long paths stay readable; buttons below.
        proj_col = QVBoxLayout()
        proj_col.setContentsMargins(0, 0, 0, 0)
        proj_col.setSpacing(6)
        proj_col.addWidget(self._project_edit)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addWidget(browse)
        btn_row.addWidget(reload_btn)
        btn_row.addStretch(1)
        proj_col.addLayout(btn_row)
        form.addRow("Project dir:", _wrap_layout(proj_col))

        self._config_combo = QComboBox()
        self._config_combo.setToolTip(
            "YAML configs found in the project dir. The selected file is the "
            "one that Validate YAML checks, the Scripts card reads, and Load "
            "experiment analyses."
        )
        # Both the Scripts list and the "wrong config" notice below are read
        # off this selection; without this the Scripts card kept listing the
        # previously selected file's recipes.
        self._config_combo.currentIndexChanged.connect(self._on_config_changed)
        form.addRow("Config:", self._config_combo)

        card.add_body(form)

        self._config_note = QLabel()
        self._config_note.setWordWrap(True)
        self._config_note.setStyleSheet("color: #f59e0b; font-size: 9pt;")
        self._config_note.setVisible(False)
        card.add_body(self._config_note)

        # A summary of the selected config, shown as soon as it is read: the
        # Experiment Type, tracking type/rig, phases, and treatment breakdown.
        self._project_summary = QLabel()
        self._project_summary.setWordWrap(True)
        self._project_summary.setTextFormat(Qt.TextFormat.RichText)
        self._project_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._project_summary.setStyleSheet(
            "QLabel { background: palette(alternate-base); border: 1px solid "
            "palette(mid); border-radius: 6px; padding: 8px; font-size: 9pt; }")
        self._project_summary.setVisible(False)
        card.add_body(self._project_summary)

        launchers = QHBoxLayout()
        edit_cfg = ActionButton("Edit config…", Category.TOOLS, icon_name="config")
        edit_cfg.clicked.connect(lambda: self._launch_subapp("config"))
        qc_view = ActionButton("QC viewer…", Category.QC, icon_name="qc")
        qc_view.clicked.connect(lambda: self._launch_subapp("qc"))
        launchers.addWidget(edit_cfg)
        launchers.addWidget(qc_view)
        card.add_body(launchers)

        self._cards["project"] = card
        self._cards_lay.addWidget(card)

    # ---------------- Load card ----------------

    def _build_load_card(self) -> None:
        card = Card(
            "Load",
            category=Category.LOAD,
            subtitle="Load a single experiment, or point at a parent dir for batch runs.",
            icon_name="load",
        )

        self._mode_single = QRadioButton("Single project")
        self._mode_batch = QRadioButton("Batch experiments")
        self._mode_single.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._mode_single)
        mode_group.addButton(self._mode_batch)
        mode_group.buttonClicked.connect(self._on_mode_changed)

        batch_help = HelpButton(
            "batch_experiments",
            tooltip="How batch analyses work",
        )

        mode_row = QHBoxLayout()
        mode_row.addWidget(self._mode_single)
        mode_row.addWidget(self._mode_batch)
        mode_row.addWidget(batch_help)
        mode_row.addStretch(1)
        card.add_body(mode_row)

        load_btn = ActionButton(
            "Load experiment", Category.LOAD, icon_name="load", primary=True
        )
        load_btn.clicked.connect(self._load_experiment)
        card.add_body(load_btn)
        self._load_btn = load_btn

        self._cards["load"] = card
        self._cards_lay.addWidget(card)

    # ---------------- Analyze card ----------------

    def _build_analyze_card(self) -> None:
        card = Card(
            "Analyze",
            category=Category.ANALYZE,
            subtitle="Summaries, QC, stats, and PDF reports.",
            icon_name="basic",
        )
        card.add_title_widget(
            HelpButton("hub_workflow", tooltip="Analysis Hub workflow")
        )

        # Facet checkbox controls whether Summarize / Pairwise / Plots buttons
        # call the faceted variants. Disabled until a project is loaded; its
        # label is rewritten then to show the configured cutoffs.
        self._facet_checkbox = QCheckBox("Faceted (no project loaded)")
        self._facet_checkbox.setEnabled(False)
        self._facet_checkbox.setToolTip(
            "When checked, Summarize, Run pairwise comparisons, and the Plots "
            "buttons all call their faceted variants using the cutoffs from "
            "the project's tracking_config.yaml."
        )
        self._facet_checkbox.toggled.connect(self._on_facet_toggled)
        card.add_body(self._facet_checkbox)

        # Tracks (button, base_label) for any button whose text gets the
        # "(facet)" suffix appended when the checkbox is on.
        self._dynamic_label_buttons: list[tuple[ActionButton, str]] = []

        self._btn_run_analysis = ActionButton(
            "Run Analysis", Category.ANALYZE, icon_name="basic", primary=True
        )
        self._btn_run_analysis.clicked.connect(self._run_full_analysis)

        self._btn_run_qc = ActionButton(
            "Run QC only", Category.QC, icon_name="quality"
        )
        self._btn_run_qc.clicked.connect(self._run_qc_only)

        self._btn_create_report = ActionButton(
            "Create PDF Report", Category.ANALYZE, icon_name="report"
        )
        self._btn_create_report.clicked.connect(self._run_create_report)

        self._btn_summarize = ActionButton(
            "Summarize", Category.ANALYZE, icon_name="csv"
        )
        self._btn_summarize.clicked.connect(self._run_summarize)
        self._dynamic_label_buttons.append((self._btn_summarize, "Summarize"))

        self._btn_pairwise = ActionButton(
            "Run pairwise comparisons", Category.ANALYZE, icon_name="compare"
        )
        self._btn_pairwise.clicked.connect(self._run_pairwise)
        self._dynamic_label_buttons.append((self._btn_pairwise, "Run pairwise comparisons"))

        for btn in (
            self._btn_run_analysis,
            self._btn_run_qc,
            self._btn_create_report,
            self._btn_summarize,
            self._btn_pairwise,
        ):
            card.add_body(btn)
            btn.setEnabled(False)

        self._cards["analyze"] = card
        self._cards_lay.addWidget(card)

    # ---------------- Plots card ----------------

    def _build_plots_card(self) -> None:
        card = Card(
            "Plots",
            category=Category.PLOTS,
            subtitle="Figures appear as tabs on the right.",
            icon_name="plots",
        )
        card.add_title_widget(
            HelpButton("hub_workflow", tooltip="Plots and Hub workflow")
        )
        self._plots_empty = QLabel(
            "Load an experiment to see available plots for its tracking type."
        )
        self._plots_empty.setStyleSheet("color: palette(mid); font-style: italic;")
        self._plots_empty.setWordWrap(True)
        card.add_body(self._plots_empty)
        self._cards["plots"] = card
        self._plots_card = card
        self._cards_lay.addWidget(card)

    # ---------------- Scripts card ----------------

    def _build_scripts_card(self) -> None:
        card = Card(
            "Scripts",
            category=Category.SCRIPTS,
            subtitle="Run saved recipes from the Script Editor.",
            icon_name="scripts",
        )
        card.add_title_widget(
            HelpButton("scripts_overview", tooltip="Scripts and Script Editor")
        )

        self._scripts_combo = QComboBox()
        self._scripts_combo.setToolTip(
            "Scripts defined under the 'scripts:' key of the active config."
        )
        card.add_body(self._scripts_combo)

        row = QHBoxLayout()
        self._btn_run_script = ActionButton(
            "Run Script", Category.SCRIPTS, icon_name="script", primary=True
        )
        self._btn_run_script.clicked.connect(self._run_selected_script)
        self._btn_run_all_scripts = ActionButton(
            "Run All", Category.SCRIPTS, icon_name="run"
        )
        self._btn_run_all_scripts.clicked.connect(self._run_all_scripts)
        self._btn_refresh_scripts = ActionButton(
            "Reload", Category.TOOLS, icon_name="clear"
        )
        self._btn_refresh_scripts.clicked.connect(self._refresh_scripts)
        row.addWidget(self._btn_run_script)
        row.addWidget(self._btn_run_all_scripts)
        row.addWidget(self._btn_refresh_scripts)
        card.add_body(row)

        self._scripts_empty = QLabel(
            "No scripts yet. Use the Config Editor's Script Editor to add some."
        )
        self._scripts_empty.setStyleSheet("color: palette(mid); font-style: italic;")
        self._scripts_empty.setWordWrap(True)
        card.add_body(self._scripts_empty)

        for w in (self._scripts_combo, self._btn_run_script, self._btn_run_all_scripts):
            w.setEnabled(False)

        self._cards["scripts"] = card
        self._cards_lay.addWidget(card)

    # ---------------- AI card ----------------

    def _build_ai_card(self) -> None:
        """AI-assisted functions (one for now: the AI Summary, ADR-0004).

        The action is offered only when a provider API key is present in the
        environment / a ``.env`` file — presence is checked, validity is not;
        a bad key surfaces as an error when a summary is requested."""
        from ..ai import available_providers

        card = Card(
            "AI",
            category=Category.AI,
            subtitle="AI-assisted functions.",
            icon_name="ai",
        )
        card.add_title_widget(
            HelpButton("ai_summary", tooltip="AI summary")
        )
        self._ai_available = bool(available_providers())
        self._btn_ai_summary = ActionButton(
            "AI summary…", Category.AI, icon_name="ai", primary=True
        )
        self._btn_ai_summary.setToolTip(
            "Have an AI provider write a one-page summary of the current "
            "analysis and embed it in the report."
        )
        self._btn_ai_summary.clicked.connect(self._open_ai_summary_dialog)
        self._btn_ai_summary.setEnabled(False)
        card.add_body(self._btn_ai_summary)
        if not self._ai_available:
            note = QLabel(
                "No API key found. Add ANTHROPIC_API_KEY or OPENAI_API_KEY "
                "to a .env file (or the environment) and restart to enable "
                "AI features."
            )
            note.setStyleSheet("color: palette(mid); font-style: italic;")
            note.setWordWrap(True)
            card.add_body(note)
        self._cards["ai"] = card
        self._cards_lay.addWidget(card)

    def _open_ai_summary_dialog(self) -> None:
        if self._exp is None:
            return
        from .ai_summary_dialog import AiSummaryDialog

        AiSummaryDialog(self).exec()

    # ---------------- Tools card ----------------

    def _build_tools_card(self) -> None:
        card = Card(
            "Tools",
            category=Category.TOOLS,
            subtitle="Housekeeping.",
            icon_name="tools",
        )
        card.add_title_widget(
            HelpButton("outputs", tooltip="Where analysis and QC outputs are written")
        )
        btn_validate = ActionButton(
            "Validate YAML", Category.TOOLS, icon_name="lint"
        )
        btn_validate.clicked.connect(self._validate_yaml)
        btn_open_analysis = ActionButton(
            "Open analysis folder", Category.TOOLS, icon_name="open"
        )
        btn_open_analysis.clicked.connect(lambda: self._open_folder("analysis"))
        btn_open_qc = ActionButton(
            "Open qc folder", Category.TOOLS, icon_name="open"
        )
        btn_open_qc.clicked.connect(lambda: self._open_folder("qc"))
        btn_clear_cache = ActionButton(
            "Clear matplotlib cache", Category.TOOLS, icon_name="clear"
        )
        btn_clear_cache.clicked.connect(self._clear_mpl_cache)
        btn_batch_tools = ActionButton(
            "Batch tools", Category.TOOLS, icon_name="batch"
        )
        btn_batch_tools.setToolTip(
            "Open a window with batch operations across project subdirectories: "
            "convert to data/ layout, rename subdirectories, and combine summary CSVs."
        )
        btn_batch_tools.clicked.connect(self._open_batch_tools)
        # Two columns: five full-width stacked buttons made the card oddly wide
        # and tall for what are small housekeeping actions.
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        buttons = (btn_open_analysis, btn_open_qc, btn_batch_tools, btn_validate,
                   btn_clear_cache)
        for i, b in enumerate(buttons):
            grid.addWidget(b, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        card.add_body(grid)
        self._cards["tools"] = card
        self._cards_lay.addWidget(card)

    # ==================================================================
    # Behaviour — project dir / config
    # ==================================================================

    def _scroll_to_card(self, key: str) -> None:
        card = self._cards.get(key)
        if card is None:
            return
        scroll = card.parent()
        # Walk up to the QScrollArea
        while scroll is not None and not hasattr(scroll, "ensureWidgetVisible"):
            scroll = scroll.parent()
        if scroll is not None:
            scroll.ensureWidgetVisible(card, 0, 20)

    def _pick_project_dir(self) -> None:
        start = str(self._project_dir) if self._project_dir else os.getcwd()
        chosen = QFileDialog.getExistingDirectory(self, "Choose project directory", start)
        if chosen:
            self._set_project_dir(chosen)

    def _create_experiment(self) -> None:
        """Open the Create Experiment wizard; on success, select the new project."""
        from .create_experiment import ConfigureExperimentDialog

        start = str(self._project_dir.parent) if self._project_dir else os.getcwd()
        dialog = ConfigureExperimentDialog(self, start_dir=start)
        if dialog.exec() and dialog.created_path is not None:
            project = dialog.created_path.parent
            self._set_project_dir(project)
            self._log.append_line(
                f"Created experiment at {project}. "
                "Assign region treatments in the Config Editor, then add the "
                "DTrack export to data/ before loading.")

    def _on_mode_changed(self) -> None:
        is_batch = self._mode_batch.isChecked()
        self._load_btn.setText("Run batch script" if is_batch else "Load experiment")
        # Single-project analyses only make sense for single mode
        for btn in (
            self._btn_run_analysis,
            self._btn_run_qc,
            self._btn_create_report,
        ):
            btn.setVisible(not is_batch)
        # Scripts and AI cards run against a single loaded experiment; disable
        # them wholesale in batch mode so only the load card's "Run batch
        # script" button stays interactive.
        for key in ("scripts", "ai"):
            card = self._cards.get(key)
            if card is not None:
                card.setEnabled(not is_batch)

    def _set_project_dir(self, path: str | Path) -> None:
        p = Path(path).expanduser().resolve()
        self._project_dir = p
        # Show only the folder name; the full path lives in self._project_dir
        # and is surfaced via the tooltip.
        self._project_edit.setText(p.name or str(p))
        self._project_edit.setToolTip(str(p))
        ui_settings.add_recent_project(p)
        # Populate config combo
        self._config_combo.blockSignals(True)
        self._config_combo.clear()
        yamls = sorted([f.name for f in p.glob("*.yaml")]) if p.exists() else []
        if not yamls:
            yamls = ["tracking_config.yaml"]
        for name in yamls:
            self._config_combo.addItem(name)
        if "tracking_config.yaml" in yamls:
            self._config_combo.setCurrentText("tracking_config.yaml")
        self._config_combo.blockSignals(False)
        self._log.append_line(f"Project: {p}")
        self._on_config_changed()

    def _reload_project(self) -> None:
        if self._project_dir:
            self._set_project_dir(self._project_dir)

    # ==================================================================
    # Scripts card
    # ==================================================================

    def _config_path(self) -> Path | None:
        if self._project_dir is None:
            return None
        return self._project_dir / self._config_combo.currentText()

    def _uses_canonical_config(self) -> bool:
        """True when the selected config is the one an Experiment would read."""
        return self._config_combo.currentText().strip() == _CANONICAL_CONFIG

    def _on_config_changed(self, _index: int = -1) -> None:
        """Re-read the selected file and note when it isn't the default.

        ``Experiment`` now takes a ``config_path``, so the selection genuinely
        drives the analysis. It previously did not: the filename was joined on
        unconditionally, so the Hub validated one file and analysed another.
        The note stays because loading a non-default config is worth seeing.
        """
        if self._uses_canonical_config():
            self._config_note.setVisible(False)
        else:
            self._config_note.setText(
                f"Using '{self._config_combo.currentText()}' instead of "
                f"{_CANONICAL_CONFIG} for validation, scripts and analysis."
            )
            self._config_note.setVisible(True)
        self._refresh_project_summary()
        self._refresh_scripts()

    def _refresh_project_summary(self) -> None:
        """Render a short summary of the selected config in the project card."""
        import yaml

        from .. import config_summary

        cfg_path = self._config_path()
        if cfg_path is None or not cfg_path.exists():
            self._project_summary.setVisible(False)
            return
        try:
            with open(cfg_path, encoding="utf-8") as handle:
                config = yaml.safe_load(handle)
            rows = config_summary.summarize(config)
        except Exception as err:  # noqa: BLE001
            self._project_summary.setText(f"<i>Could not read config: {err}</i>")
            self._project_summary.setVisible(True)
            return
        self._project_summary.setText(self._format_summary_html(rows))
        self._project_summary.setVisible(True)

    @staticmethod
    def _format_summary_html(rows) -> str:
        import html as _html

        out = []
        for label, value in rows:
            lab = _html.escape(str(label))
            val = _html.escape(str(value))
            if label == "Experiment type":
                out.append(f"<div style='margin-bottom:3px'><b>{lab}:</b> "
                           f"<b>{val}</b></div>")
            else:
                out.append(f"<div><span style='color:#64748b'>{lab}:</span> "
                           f"{val}</div>")
        return "".join(out)

    def _refresh_scripts(self) -> None:
        from ..script_editor.runner import load_scripts

        cfg = self._config_path()
        scripts: list[dict] = []
        if cfg and cfg.exists():
            try:
                scripts = load_scripts(cfg)
            except Exception as err:  # noqa: BLE001
                self._log_issue(f"[scripts] failed to read {cfg}: {err}")
        self._scripts = scripts
        self._scripts_combo.blockSignals(True)
        self._scripts_combo.clear()
        for s in scripts:
            self._scripts_combo.addItem(s.get("name", "Untitled"))
        self._scripts_combo.blockSignals(False)
        has = bool(scripts)
        self._scripts_empty.setVisible(not has)
        self._scripts_combo.setEnabled(has)
        self._btn_run_script.setEnabled(has)
        self._btn_run_all_scripts.setEnabled(has)

    def _run_selected_script(self) -> None:
        idx = self._scripts_combo.currentIndex()
        if idx < 0 or idx >= len(getattr(self, "_scripts", [])):
            return
        self._spawn_script_task([self._scripts[idx]])

    def _run_all_scripts(self) -> None:
        scripts = list(getattr(self, "_scripts", []))
        if not scripts:
            return
        self._spawn_script_task(scripts)

    def _spawn_script_task(self, scripts: list[dict]) -> None:
        from ..script_editor.runner import run_script

        project_dir = self._project_dir
        exp = self._exp

        # Figure callback (runs on worker thread, signal-free — Qt queues
        # add_figure on the main thread at the end via finished signal).
        # Simpler: capture figures + titles in a list and replay after the task.
        figures: list[tuple[str, object]] = []
        worker_log = []  # collected log lines; flushed via finished_ok

        def _fig(title: str, fig) -> None:
            figures.append((title, fig))

        def _log_cb(msg: str) -> None:
            worker_log.append(str(msg))

        names = [s.get("name", "?") for s in scripts]

        def _run() -> str:
            current_exp = exp
            for s in scripts:
                current_exp = run_script(
                    s,
                    project_dir=project_dir,
                    log_cb=_log_cb,
                    figure_cb=_fig,
                    exp=current_exp,
                ).exp
            return f"Ran {len(scripts)} script(s): {', '.join(names)}"

        def _on_ok(msg: str) -> None:
            for ln in worker_log:
                self._log.append_line(ln)
            interactive = self._interactive_checkbox.isChecked()
            for title, fig in figures:
                self._plot_dock.add_figure(title, fig, interactive=interactive)
            self._log.append_line(msg)

        def _on_fail(msg: str) -> None:
            for ln in worker_log:
                self._log.append_line(ln)
            self._log_issue(msg)

        # Dispatch through our regular TaskWorker for thread safety + log redirect
        self._spawn_task_with_callbacks("Script run", _run, _on_ok, _on_fail)

    # ==================================================================
    # Behaviour — loading an Experiment
    # ==================================================================

    def _load_experiment(self) -> None:
        if self._mode_batch.isChecked():
            self._run_batch_scripts_per_subdir()
            return
        if not self._project_dir:
            self._warn("Choose a project directory first.")
            return
        project_dir = self._project_dir
        # The file the user actually selected — the same one Validate YAML
        # checks and the Scripts card reads.
        config_name = self._config_combo.currentText().strip() or _CANONICAL_CONFIG
        # Use a list as a mutable holder so the worker callable can hand the
        # built Experiment back to the GUI thread without a custom signal.
        result_holder: list = []

        def _do_load_and_qc() -> str:
            exp = ExperimentMod.Experiment(str(project_dir), config_path=config_name)
            result_holder.append(exp)
            print(str(exp))
            exp.run_qc()
            return f"Loaded experiment and ran QC ({project_dir})."

        def _on_ok(msg: str) -> None:
            if result_holder:
                self._exp = result_holder[0]
                self._on_experiment_ready()
                # Launch the QC viewer so it picks up the freshly-saved qc/ artifacts.
                self._launch_subapp("qc")
            self._log.append_line(msg)

        def _on_fail(msg: str) -> None:
            self._log_issue(msg)
            self._warn("Failed to load experiment — see Output for details.")

        self._log.append_line(f"Loading experiment from {project_dir}…")
        # Don't pop QC artifacts as Hub tabs — the QC viewer (auto-launched on
        # success) is the canonical surface for them.
        self._spawn_task_with_callbacks(
            "Load + QC", _do_load_and_qc, _on_ok, _on_fail, surface_artifacts=False,
        )

    def _on_experiment_ready(self) -> None:
        # Enable single-mode analysis buttons (including the new dynamic ones).
        for btn in (
            self._btn_run_analysis,
            self._btn_run_qc,
            self._btn_create_report,
            self._btn_summarize,
            self._btn_pairwise,
        ):
            btn.setEnabled(True)
        # Configure the facet checkbox based on the experiment's cutoffs.
        cutoffs = getattr(self._exp, "facet_cutoffs", None)
        if cutoffs is None:
            self._facet_checkbox.setEnabled(False)
            self._facet_checkbox.setChecked(False)
            self._facet_checkbox.setText("Faceted (no cutoffs in config)")
        else:
            self._facet_checkbox.setEnabled(True)
            self._facet_checkbox.setChecked(True)
            cuts = ", ".join(str(c) for c in cutoffs)
            self._facet_checkbox.setText(f"Faceted (cutoffs: {cuts})")
        self._rebuild_plot_buttons()
        # Sync labels after both rebuild + checkbox state changes.
        self._refresh_dynamic_labels()

    def _rebuild_plot_buttons(self) -> None:
        # Clear existing plot buttons.
        for btn in self._plot_buttons:
            btn.setParent(None)
            btn.deleteLater()
        self._plot_buttons.clear()
        # Drop entries in the dynamic-label registry that belong to plot buttons
        # we just deleted, so _refresh_dynamic_labels doesn't dereference dead Qt objects.
        self._dynamic_label_buttons = [
            (b, lbl) for (b, lbl) in self._dynamic_label_buttons
            if b is self._btn_summarize or b is self._btn_pairwise
        ]
        self._plots_empty.setVisible(False)

        if self._exp is None:
            self._plots_empty.setVisible(True)
            return

        tt_name = self._exp.parameters.get_tracking_type().name
        entries = _PLOT_BUTTONS.get(tt_name, [])
        if not entries:
            self._plots_empty.setText(
                f"No plots registered for tracking type {tt_name}."
            )
            self._plots_empty.setVisible(True)
            return

        for label, flat_method, facet_method in entries:
            icon_name = _PLOT_ICON_BY_LABEL.get(label, "plot")
            btn = ActionButton(label, Category.PLOTS, icon_name=icon_name)
            btn.clicked.connect(
                lambda _=False, lbl=label, fm=flat_method, fa=facet_method:
                    self._render_dynamic_plot(lbl, fm, fa)
            )
            self._plots_card.add_body(btn)
            self._plot_buttons.append(btn)
            self._dynamic_label_buttons.append((btn, label))

    def _render_plot(self, method_name: str, kwargs: dict, title: str) -> None:
        """Run an Arena plot method, capture its figure, and add a PlotDock tab.

        Routes through ``self._exp.arena`` rather than ``self._exp`` so we
        bypass any Experiment wrappers that save-and-close the figure (which
        would leave nothing for ``capture_figures`` to grab).
        """
        if self._exp is None:
            return
        fn = getattr(self._exp.arena, method_name, None)
        if fn is None:
            self._log_issue(f"Unknown plot method: arena.{method_name}")
            return
        self._log.append_line(f"[plot] arena.{method_name}({_fmt_kwargs(kwargs)})")

        figs: list = []

        def _do() -> str:
            # ``capture_figures`` swaps the module-global ``plt.show``; running
            # it on the GUI thread meant a plot click during an analysis had
            # two threads fighting over that global — the worker's figure was
            # swallowed, its PNG never written, and plt.show left corrupted.
            # Going through TaskWorker serialises the two (the Plots card is
            # also disabled while busy, see _set_busy).
            with capture_figures() as captured:
                fn(**kwargs)
            figs.extend(captured)
            return f"Plot complete: {title}."

        def _on_ok(msg: str) -> None:
            if not figs:
                self._log_issue(f"[plot] {method_name} produced no figures.")
                return
            interactive = self._interactive_checkbox.isChecked()
            for i, fig in enumerate(figs):
                tab_title = title if len(figs) == 1 else f"{title} ({i+1})"
                self._plot_dock.add_figure(tab_title, fig, interactive=interactive)
            self._log.append_line(msg)

        def _on_fail(msg: str) -> None:
            self._log_issue(msg)
            self._warn(f"Plot failed: {title} — see the Errors tab.")

        self._spawn_task_with_callbacks(f"Plot {title}", _do, _on_ok, _on_fail)

    def _render_dynamic_plot(
        self, base_label: str, flat_method: str, facet_method: str
    ) -> None:
        """Dispatch a Plots-card click to either the flat or faceted Arena method."""
        if self._exp is None:
            return
        if self._is_facet_active():
            method = facet_method
            kwargs = {"cutoffs": tuple(self._exp.facet_cutoffs)}
            title = f"{base_label} (facet)"
        else:
            method = flat_method
            kwargs = {}
            title = base_label
        self._render_plot(method, kwargs, title)

    # ------------------------------------------------------------------
    # Facet checkbox plumbing
    # ------------------------------------------------------------------

    def _is_facet_active(self) -> bool:
        return (
            self._facet_checkbox.isEnabled()
            and self._facet_checkbox.isChecked()
            and self._exp is not None
            and getattr(self._exp, "facet_cutoffs", None) is not None
        )

    def _on_facet_toggled(self, _checked: bool = False) -> None:
        self._refresh_dynamic_labels()

    def _refresh_dynamic_labels(self) -> None:
        suffix = " (facet)" if self._is_facet_active() else ""
        for btn, base in self._dynamic_label_buttons:
            try:
                btn.setText(base + suffix)
            except RuntimeError:
                # Underlying C++ widget was deleted; ignore.
                pass

    # ==================================================================
    # Behaviour — analysis tasks (threaded)
    # ==================================================================

    def _prompt_run_notes(self, exp) -> None:
        """Collect optional user notes for the run about to start.

        Prefilled with any existing notes so they can be revised; OK saves
        (blank clears), Cancel keeps the existing notes. Saved notes are
        rendered near the top of the report.
        """
        try:
            existing = exp.read_run_notes()
        except Exception:  # noqa: BLE001 — a broken notes file must not block a run
            existing = ""
        text, ok = QInputDialog.getMultiLineText(
            self, "Run notes",
            "Notes for this run (optional) — shown at the top of the report.\n"
            "Leave blank to clear saved notes. Cancel keeps them unchanged.",
            existing,
        )
        if not ok:
            return
        try:
            exp.write_run_notes(text)
        except OSError as err:
            QMessageBox.warning(self, "Run notes",
                                f"Could not save the notes:\n{err}")

    def _run_full_analysis(self) -> None:
        if self._exp is None:
            return
        exp = self._exp
        self._prompt_run_notes(exp)
        self._spawn_task(
            "Run analysis",
            lambda: (exp.run_analysis(), exp.create_report(), "Analysis + report complete.")[-1],
        )

    def _run_qc_only(self) -> None:
        if self._exp is None:
            return
        exp = self._exp
        self._spawn_task("QC", lambda: exp.qc() or "QC complete.")

    def _run_create_report(self) -> None:
        if self._exp is None:
            return
        exp = self._exp
        self._prompt_run_notes(exp)
        self._spawn_task("PDF report", lambda: exp.create_report())

    def _run_summarize(self) -> None:
        if self._exp is None:
            return
        exp = self._exp
        if self._is_facet_active():
            cutoffs = tuple(exp.facet_cutoffs)

            def _do() -> str:
                exp.save_summary(cutoffs=cutoffs)
                return "Summarize (facet) complete."

            self._spawn_task("Summarize (facet)", _do)
        else:
            def _do() -> str:
                # Pass cutoffs=None so save_summary writes only the flat CSV.
                exp.save_summary(cutoffs=None)
                return "Summarize complete."

            self._spawn_task("Summarize", _do)

    def _run_pairwise(self) -> None:
        if self._exp is None:
            return
        exp = self._exp
        if self._is_facet_active():
            cutoffs = tuple(exp.facet_cutoffs)

            def _do() -> str:
                exp.stats(cutoffs=cutoffs, save=True)
                return "Pairwise comparisons (facet) complete."

            self._spawn_task("Pairwise (facet)", _do)
        else:
            def _do() -> str:
                _run_pairwise_flat(exp)
                return "Pairwise comparisons complete."

            self._spawn_task("Pairwise", _do)

    def _run_batch_scripts_per_subdir(self) -> None:
        """Run the script named ``batch`` against every immediate subdirectory
        of the project directory. Each subdir is treated as its own project:
        scripts are loaded from ``<subdir>/tracking_config.yaml``. Subdirs
        that don't define a ``batch`` script are reported as warnings and
        skipped."""
        from ..script_editor.runner import load_scripts, run_script

        if self._project_dir is None:
            self._warn("Choose a project directory first.")
            return
        parent = self._project_dir
        if not parent.is_dir():
            self._warn(f"Project directory is not a directory: {parent}")
            return
        subdirs = sorted(d for d in parent.iterdir() if d.is_dir())
        if not subdirs:
            self._warn(f"No subdirectories found in {parent}.")
            return

        figures: list[tuple[str, object]] = []
        worker_log: list[str] = []
        issues: list[str] = []  # warning/error lines, mirrored to the Errors tab

        def _log_cb(msg: str) -> None:
            worker_log.append(str(msg))

        def _issue(msg: str) -> None:
            worker_log.append(msg)
            issues.append(msg)

        def _fig_cb(title: str, fig) -> None:
            figures.append((title, fig))

        def _find_config(subdir: Path) -> Path | None:
            for entry in subdir.iterdir():
                if entry.is_file() and entry.name.lower() == "tracking_config.yaml":
                    return entry
            return None

        def _find_batch_script(scripts: list[dict]) -> dict | None:
            for s in scripts:
                if str(s.get("name", "")).strip().lower() == "batch":
                    return s
            return None

        def _do() -> str:
            ran = 0
            skipped_no_config = 0
            skipped_no_script = 0
            failed = 0
            for sub in subdirs:
                cfg = _find_config(sub)
                if cfg is None:
                    _issue(f"[batch] {sub.name}: no tracking_config.yaml — skipped.")
                    skipped_no_config += 1
                    continue
                try:
                    scripts = load_scripts(cfg)
                except Exception as err:  # noqa: BLE001
                    _issue(f"[batch] {sub.name}: failed to read scripts ({err}) — skipped.")
                    failed += 1
                    continue
                script = _find_batch_script(scripts)
                if script is None:
                    _issue(
                        f"[batch] {sub.name}: no script named 'batch' in {cfg.name} — skipped."
                    )
                    skipped_no_script += 1
                    continue
                worker_log.append(f"── Running 'batch' in {sub.name} ──")
                try:
                    run_script(
                        script,
                        project_dir=sub,
                        log_cb=_log_cb,
                        figure_cb=_fig_cb,
                        exp=None,
                    )
                    ran += 1
                except Exception as err:  # noqa: BLE001
                    _issue(f"[batch] {sub.name}: script failed: {err}")
                    failed += 1
            return (
                f"Batch script complete: {ran} ran, "
                f"{skipped_no_script} without 'batch' script, "
                f"{skipped_no_config} without config, "
                f"{failed} failed (of {len(subdirs)} subdirs)."
            )

        def _on_ok(msg: str) -> None:
            for ln in worker_log:
                self._log.append_line(ln)
            for ln in issues:
                self._err_log.append_line(ln)
            interactive = self._interactive_checkbox.isChecked()
            for title, fig in figures:
                self._plot_dock.add_figure(title, fig, interactive=interactive)
            self._log.append_line(msg)

        def _on_fail(msg: str) -> None:
            for ln in worker_log:
                self._log.append_line(ln)
            for ln in issues:
                self._err_log.append_line(ln)
            self._log_issue(msg)

        self._spawn_task_with_callbacks("Batch script", _do, _on_ok, _on_fail)

    def _spawn_task(self, task_name: str, fn: Callable[[], object]) -> None:
        self._spawn_task_with_callbacks(task_name, fn, self._on_task_ok, self._on_task_failed)

    def _spawn_task_with_callbacks(
        self,
        task_name: str,
        fn: Callable[[], object],
        on_ok: Callable[[str], None],
        on_fail: Callable[[str], None],
        surface_artifacts: bool = True,
    ) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._warn("Another task is already running.")
            return
        self._progress.setVisible(True)
        self._set_busy(True)
        # Whether ``Saved: <path>`` lines from this task should appear as
        # PlotDock tabs. Disabled for Load + QC since the QC viewer is the
        # canonical surface for those artifacts.
        self._surface_artifacts = surface_artifacts
        worker = TaskWorker(task_name, fn)
        worker.log_text.connect(self._on_worker_log)
        worker.finished_ok.connect(on_ok)
        worker.failed.connect(on_fail)
        worker.finished.connect(lambda: self._on_task_finished(worker))
        self._worker = worker
        worker.start()

    def _on_worker_log(self, text: str) -> None:
        """Mirror worker stdout to the Output tab and (when enabled for the
        current task) surface ``Saved: <path>`` artifacts as PlotDock tabs."""
        self._log.append_line(text)
        if not getattr(self, "_surface_artifacts", True):
            return
        for line in text.splitlines():
            m = _SAVED_RE.match(line)
            if not m:
                continue
            path_str = m.group(1).strip()
            if not path_str:
                continue
            try:
                path = Path(path_str)
            except Exception:  # noqa: BLE001
                continue
            self._add_artifact_tab(path)

    def _add_artifact_tab(self, path: Path) -> None:
        """Add a zoomable PlotDock tab for *path* (PNG / TXT / CSV)."""
        if not path.exists():
            return
        key = str(path.resolve())
        cached = self._artifact_tabs.get(key)
        if cached is not None:
            try:
                idx = self._plot_dock.indexOf(cached)
            except RuntimeError:
                # Belt and braces: the C++ side is normally pruned by the
                # destroyed handler below, but this slot is queued, so never
                # let a dead wrapper raise here — PyQt escalates an exception
                # in a queued slot to qFatal() and the whole Hub goes down
                # mid-analysis.
                idx = -1
            if idx >= 0:
                self._plot_dock.setCurrentIndex(idx)
                return
            # Tab was closed by the user — drop the stale entry and re-add below.
            self._artifact_tabs.pop(key, None)

        suffix = path.suffix.lower()
        title = path.stem
        if suffix == ".png":
            view = ZoomableImageView(path)
            if view.is_empty():
                return
            tab_icon = icon("plots", category=Category.PLOTS)
        elif suffix in (".txt", ".csv"):
            view = ZoomableTextView(path)
            tab_icon = icon("csv", category=Category.ANALYZE)
        else:
            return  # PDFs / other formats: just leave them on disk.

        self._artifact_tabs[key] = view
        # Closing the tab (or "Clear plots") calls deleteLater; prune the
        # mapping when the widget actually goes away so the next "Saved:" line
        # for the same path can't reach a deleted C++ object.
        # Everything the slot needs is bound as a default argument: a plain
        # closure over ``self`` breaks when the signal fires from the garbage
        # collector, which clears the enclosing cell first (NameError inside a
        # Qt slot is fatal).
        view.destroyed.connect(
            lambda *_args, hub=self, k=key, w=view: hub._forget_artifact_tab(k, w)
        )
        self._plot_dock.add_widget(title, view, tab_icon)

    def _forget_artifact_tab(self, key: str, widget: QWidget) -> None:
        """Drop *key* from the artifact map, but only if it still maps to *widget*.

        Guards the case where the tab was re-added before the old widget's
        deferred deletion was processed.
        """
        if self._artifact_tabs.get(key) is widget:
            del self._artifact_tabs[key]

    def _on_task_ok(self, msg: str) -> None:
        self._log.append_line(msg)

    def _on_task_failed(self, msg: str) -> None:
        # An Errors-tab badge alone left a failed run looking like a finished
        # one; _load_experiment already pops a dialog, so do the same here.
        self._log_issue(msg)
        headline = msg.splitlines()[0] if msg else "The task failed."
        QMessageBox.warning(
            self, "PyTrackingAnalysis",
            f"{headline}\n\nSee the Errors tab for the full traceback.",
        )

    def _on_task_finished(self, worker: TaskWorker) -> None:
        if self._worker is worker:
            self._worker = None
        self._progress.setVisible(False)
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        for btn in (
            self._btn_run_analysis,
            self._btn_run_qc,
            self._btn_create_report,
            self._btn_summarize,
            self._btn_pairwise,
            self._load_btn,
        ):
            btn.setEnabled(
                (not busy)
                and (
                    btn is self._load_btn
                    or self._exp is not None
                )
            )
        # The AI summary additionally needs a provider key (checked once at
        # card build; presence-gated per ADR-0004).
        self._btn_ai_summary.setEnabled(
            (not busy) and self._exp is not None and self._ai_available
        )
        # Plot rendering and script runs are workloads too; leaving their cards
        # live during a task let a second one start behind the first.
        for key in ("plots", "scripts"):
            card = self._cards.get(key)
            if card is None:
                continue
            if key == "scripts" and self._mode_batch.isChecked():
                continue  # already disabled wholesale by _on_mode_changed
            card.setEnabled(not busy)

    # ==================================================================
    # Behaviour — tools
    # ==================================================================

    def _validate_yaml(self) -> None:
        if not self._project_dir:
            return
        path = self._project_dir / self._config_combo.currentText()
        # Parsing cleanly is not the same as being usable — check the semantics
        # too, so an unknown rig or a missing movie calibration is reported here
        # rather than surfacing mid-analysis or silently falling back to defaults.
        from ..config_validation import validate_config_file

        problems = validate_config_file(str(path))
        if not problems:
            self._log.append_line(f"[validate] {path} is valid.")
            return
        self._log_issue(f"[validate] {path}: {len(problems)} problem(s) found:")
        for problem in problems:
            self._log_issue(f"[validate]   • {problem}")

    def _open_folder(self, subfolder: str) -> None:
        if not self._project_dir:
            return
        target = self._project_dir / subfolder
        if not target.exists():
            self._log_issue(f"[open] {target} does not exist yet.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _clear_mpl_cache(self) -> None:
        import matplotlib as mpl

        cache = Path(mpl.get_cachedir())
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
            self._log.append_line(f"[tools] cleared {cache}")
        else:
            self._log.append_line(f"[tools] no cache at {cache}")

    def _convert_subdirectories(self) -> None:
        """For each subdirectory of the project dir, ensure a ``data/`` folder
        exists and move every non-YAML top-level file into it. Preps a
        directory tree for a batch run."""
        if not self._project_dir:
            self._warn("Choose a project directory first.")
            return
        project = self._project_dir
        subdirs = sorted(d for d in project.iterdir() if d.is_dir())
        if not subdirs:
            self._log_issue(f"[convert] no subdirectories under {project}")
            return

        def _do_convert() -> str:
            print(f"Converting {len(subdirs)} subdirectories under {project}…")
            moved = 0
            overwritten = 0
            for sub in subdirs:
                data = sub / "data"
                if not data.exists():
                    data.mkdir()
                    print(f"Created: {data}")
                for entry in sorted(sub.iterdir()):
                    if entry.is_dir():
                        continue
                    if entry.suffix.lower() in (".yaml", ".yml"):
                        continue
                    dest = data / entry.name
                    existed = dest.exists()
                    if existed:
                        dest.unlink()
                    shutil.move(str(entry), str(dest))
                    if existed:
                        print(f"Overwrote: {entry.name} → {dest}")
                        overwritten += 1
                    else:
                        print(f"Moved: {entry.name} → {dest}")
                        moved += 1
            return (
                f"Convert complete: {moved} new, {overwritten} overwritten, "
                f"across {len(subdirs)} subdirectories."
            )

        self._spawn_task("Convert subdirectories", _do_convert)

    def _open_batch_tools(self) -> None:
        if not self._project_dir:
            self._warn("Choose a project directory first.")
            return
        existing = getattr(self, "_batch_tools_dialog", None)
        if existing is not None and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return
        dlg = BatchToolsDialog(self)
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.destroyed.connect(lambda _=None: setattr(self, "_batch_tools_dialog", None))
        self._batch_tools_dialog = dlg
        dlg.show()

    def _rename_subdirectories(self, mode: str, text: str) -> None:
        """Rename every immediate subdirectory of the project dir.

        ``mode`` is one of ``"prepend"``, ``"append"``, or ``"remove"``.
        ``text`` is the substring to add or remove.
        """
        if not self._project_dir:
            self._warn("Choose a project directory first.")
            return
        if not text:
            self._warn("Enter a non-empty substring.")
            return
        project = self._project_dir
        subdirs = sorted(d for d in project.iterdir() if d.is_dir())
        if not subdirs:
            self._log_issue(f"[rename] no subdirectories under {project}")
            return

        # Compute new names up front so we can detect collisions and skip
        # no-ops before mutating the filesystem.
        plans: list[tuple[Path, Path]] = []
        existing = {d.name for d in subdirs}
        seen_targets: set[str] = set()
        for sub in subdirs:
            old = sub.name
            if mode == "prepend":
                new = f"{text}{old}"
            elif mode == "append":
                new = f"{old}{text}"
            elif mode == "remove":
                new = old.replace(text, "")
            else:
                self._warn(f"Unknown rename mode: {mode}")
                return
            if not new or new == old:
                continue
            if new in existing or new in seen_targets:
                self._log_issue(
                    f"[rename] skip {old} → {new} (collides with existing name)"
                )
                continue
            seen_targets.add(new)
            plans.append((sub, sub.with_name(new)))

        if not plans:
            self._log.append_line("[rename] nothing to do.")
            return

        def _do_rename() -> str:
            print(f"Renaming {len(plans)} subdirectories under {project}…")
            renamed = 0
            for src, dst in plans:
                if dst.exists():
                    print(f"Skipped (exists): {dst.name}")
                    continue
                src.rename(dst)
                print(f"Renamed: {src.name} → {dst.name}")
                renamed += 1
            return f"Rename complete: {renamed} of {len(plans)} subdirectories."

        self._spawn_task("Rename subdirectories", _do_rename)

    def _copy_yaml_to_subdirectories(self, yaml_path: Path) -> None:
        """Copy ``yaml_path`` into every immediate subdirectory of the project."""
        if not self._project_dir:
            self._warn("Choose a project directory first.")
            return
        src = Path(yaml_path)
        if not src.is_file():
            self._warn(f"YAML not found: {src}")
            return
        project = self._project_dir
        subdirs = sorted(d for d in project.iterdir() if d.is_dir())
        if not subdirs:
            self._log_issue(f"[copy-yaml] no subdirectories under {project}")
            return

        def _do_copy() -> str:
            print(f"Copying {src.name} into {len(subdirs)} subdirectories…")
            copied = 0
            overwritten = 0
            for sub in subdirs:
                dest = sub / src.name
                if dest.resolve() == src.resolve():
                    print(f"Skipped (same file): {dest}")
                    continue
                existed = dest.exists()
                shutil.copy2(src, dest)
                if existed:
                    print(f"Overwrote: {dest}")
                    overwritten += 1
                else:
                    print(f"Copied: {dest}")
                    copied += 1
            return (
                f"Copy YAML complete: {copied} new, {overwritten} overwritten "
                f"across {len(subdirs)} subdirectories."
            )

        self._spawn_task("Copy YAML to subdirectories", _do_copy)

    def _combine_summaries(self) -> None:
        """Stack every ``*_Summary.csv`` and ``*_Summary_Facet.csv`` found in
        ``<subdir>/analysis/`` across the project dir into a single combined
        CSV per type, tagged with the originating subdirectory name."""
        if not self._project_dir:
            self._warn("Choose a project directory first.")
            return
        project = self._project_dir
        subdirs = sorted(d for d in project.iterdir() if d.is_dir())
        if not subdirs:
            self._log_issue(f"[combine] no subdirectories under {project}")
            return

        def _do_combine() -> str:
            import pandas as pd

            flat_frames: list[pd.DataFrame] = []
            facet_frames: list[pd.DataFrame] = []
            for sub in subdirs:
                analysis = sub / "analysis"
                if not analysis.is_dir():
                    continue
                for csv_path in sorted(analysis.glob("*_Summary.csv")):
                    df = pd.read_csv(csv_path)
                    df.insert(0, "subdirectory", sub.name)
                    flat_frames.append(df)
                    print(f"Read: {csv_path}")
                for csv_path in sorted(analysis.glob("*_Summary_Facet.csv")):
                    df = pd.read_csv(csv_path)
                    df.insert(0, "subdirectory", sub.name)
                    facet_frames.append(df)
                    print(f"Read: {csv_path}")

            if not flat_frames and not facet_frames:
                return "No summary CSVs found to combine."

            written: list[str] = []
            base = project.name
            if flat_frames:
                out = project / f"{base}_combined.csv"
                pd.concat(flat_frames, ignore_index=True).to_csv(
                    out, index=False, na_rep="NA"
                )
                print(f"Saved: {out}")
                written.append(f"{len(flat_frames)} → {out.name}")
            if facet_frames:
                out = project / f"{base}_combined_facet.csv"
                pd.concat(facet_frames, ignore_index=True).to_csv(
                    out, index=False, na_rep="NA"
                )
                print(f"Saved: {out}")
                written.append(f"{len(facet_frames)} → {out.name}")
            return "Combine complete: " + "; ".join(written)

        self._spawn_task("Combine summaries", _do_combine)

    def _launch_subapp(self, which: str) -> None:
        """Launch the Config or QC viewer in a separate process.

        The child outlives the Hub on purpose, so the user can close the Hub and
        keep editing. We keep the handles only so a child that dies immediately
        (bad install, import error) gets reported instead of vanishing silently.
        """
        args = [sys.executable, "-m", "pytrackinganalysis", which]
        if self._project_dir:
            args.append(str(self._project_dir))
        try:
            process = subprocess.Popen(args, close_fds=True)
        except Exception as err:  # noqa: BLE001
            self._warn(f"Failed to launch {which}: {err}")
            return

        self._subapps.append((which, process))
        self._log.append_line(f"[tools] launched pytrack-{which} (pid {process.pid})")
        QTimer.singleShot(2000, lambda: self._check_subapp(which, process))
        self._start_reaper()

    def _start_reaper(self) -> None:
        """Keep polling the child apps so exited ones don't stay zombies.

        A QC viewer is spawned on every successful load and each handle used to
        be polled exactly once, 2 s in; anything the user closed later was
        never waited on and lingered as a defunct process for the life of the
        Hub.
        """
        timer = getattr(self, "_subapp_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setInterval(3000)
            timer.timeout.connect(self._reap_subapps)
            self._subapp_timer = timer
        if not timer.isActive():
            timer.start()

    def _reap_subapps(self) -> None:
        """Collect the exit status of every finished child app."""
        alive: list[tuple[str, object]] = []
        for which, process in self._subapps:
            try:
                code = process.poll()
            except Exception:  # noqa: BLE001
                continue
            if code is None:
                alive.append((which, process))
            else:
                self._log.append_line(
                    f"[tools] pytrack-{which} (pid {process.pid}) exited with code {code}."
                )
        self._subapps = alive
        timer = getattr(self, "_subapp_timer", None)
        if not alive and timer is not None:
            timer.stop()

    def _check_subapp(self, which: str, process) -> None:
        """Report a child app that exited right after launch."""
        code = process.poll()
        if code not in (None, 0):
            self._log_issue(
                f"[tools] pytrack-{which} exited immediately with code {code}. "
                "Run it from a terminal to see the error."
            )
        if code is not None:
            self._subapps = [entry for entry in self._subapps if entry[1] is not process]

    # ==================================================================
    # Theme toggle
    # ==================================================================

    def _toggle_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        new_mode = "dark" if resolved_mode() == "light" else "light"
        apply_theme(app, mode=new_mode)
        ui_settings.set_value("theme", new_mode)
        self._btn_theme.setIcon(
            icon("theme_dark" if resolved_mode() == "light" else "theme_light")
        )

    # ==================================================================
    # Helpers
    # ==================================================================

    def _log_issue(self, msg: str) -> None:
        """Log *msg* to the Errors tab as well as the chronological Output tab."""
        self._log.append_line(msg)
        self._err_log.append_line(msg)

    def _warn(self, msg: str) -> None:
        self._err_log.append_line(f"[warning] {msg}")
        QMessageBox.warning(self, "PyTrackingAnalysis", msg)

    # ==================================================================
    # Shutdown
    # ==================================================================

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        """Never let a running task's QThread be destroyed with the window.

        Qt aborts the process in that case; an analysis is exactly the kind of
        long task a user is tempted to close out from under.
        """
        worker = self._worker
        if worker is not None and worker.isRunning():
            answer = QMessageBox.question(
                self, "PyTrackingAnalysis",
                f"'{worker.task_name}' is still running.\n\n"
                "Wait for it to finish and then close?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Ok:
                event.ignore()
                return
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                finished = shutdown_worker(worker)
            finally:
                QApplication.restoreOverrideCursor()
            if not finished:
                QMessageBox.warning(
                    self, "PyTrackingAnalysis",
                    f"'{worker.task_name}' is still running. Closing now would "
                    "abort the application — try again once it finishes.",
                )
                event.ignore()
                return
        self._worker = None
        timer = getattr(self, "_subapp_timer", None)
        if timer is not None:
            timer.stop()
        # Child apps are meant to outlive the Hub, but collect any that have
        # already exited so they aren't left defunct.
        self._reap_subapps()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _wrap_layout(layout) -> QWidget:
    host = QWidget()
    host.setLayout(layout)
    return host


def _fmt_kwargs(kwargs: dict) -> str:
    if not kwargs:
        return ""
    return ", ".join(f"{k}={v!r}" for k, v in kwargs.items())


def _run_pairwise_flat(exp) -> None:
    """Non-facet counterpart to ``Experiment.stats`` — runs over the full range
    and writes ``<exp>_Stats_flat.txt`` to ``analysis_path``."""
    import io as _io
    import sys as _sys

    metrics = exp._stats_metrics()
    if not metrics:
        print("No comparison metrics defined for this tracking type.")
        return

    buf = _io.StringIO()
    saved_stdout = _sys.stdout
    _sys.stdout = buf
    try:
        for metric in metrics:
            try:
                exp.arena.run_pairwise_comparisons(metric=metric)
            except Exception as err:  # noqa: BLE001
                print(f"Warning: could not run comparison for '{metric}': {err}")
    finally:
        _sys.stdout = saved_stdout

    text = buf.getvalue()
    print(text)

    path = os.path.join(
        exp.analysis_path, f"{exp.arena.experiment_name}_Stats_flat.txt"
    )
    with open(path, "w") as f:
        f.write(text)
    print(f"Saved: {path}")


class BatchToolsDialog(QDialog):
    """Secondary window with batch operations across project subdirectories."""

    def __init__(self, hub: "HubWindow") -> None:
        super().__init__(hub)
        self._hub = hub
        project = hub._project_dir
        self.setWindowTitle("PyTrackingAnalysis — Batch tools")
        self.setMinimumWidth(420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        header_row = QHBoxLayout()
        header = QLabel(f"Project: <b>{project}</b>" if project else "Project: <i>(not set)</i>")
        header.setWordWrap(True)
        header_row.addWidget(header, 1)
        header_row.addWidget(
            HelpButton("batch_tools", tooltip="What each batch tool does")
        )
        outer.addLayout(header_row)

        btn_convert = ActionButton(
            "Convert subdirectories", Category.TOOLS, icon_name="batch"
        )
        btn_convert.setToolTip(
            "For each subdirectory of the project dir, create a 'data/' folder "
            "and move every non-YAML file at the top level into it. Preps the "
            "subdirectories for a batch run."
        )
        btn_convert.clicked.connect(self._on_convert)

        btn_prepend = ActionButton(
            "Prepend to subdir names", Category.TOOLS, icon_name="add"
        )
        btn_prepend.setToolTip("Add a substring to the start of every subdirectory name.")
        btn_prepend.clicked.connect(lambda: self._on_rename("prepend"))

        btn_append = ActionButton(
            "Append to subdir names", Category.TOOLS, icon_name="add"
        )
        btn_append.setToolTip("Add a substring to the end of every subdirectory name.")
        btn_append.clicked.connect(lambda: self._on_rename("append"))

        btn_remove = ActionButton(
            "Remove from subdir names", Category.TOOLS, icon_name="remove"
        )
        btn_remove.setToolTip("Remove a substring from every subdirectory name.")
        btn_remove.clicked.connect(lambda: self._on_rename("remove"))

        btn_combine = ActionButton(
            "Combine summary CSVs", Category.TOOLS, icon_name="csv"
        )
        btn_combine.setToolTip(
            "Stack every analysis/*_Summary.csv and *_Summary_Facet.csv under "
            "each subdirectory into <project>_combined.csv (and "
            "<project>_combined_facet.csv) at the project root. Adds a "
            "'subdirectory' column to track origin."
        )
        btn_combine.clicked.connect(self._on_combine)

        btn_copy_yaml = ActionButton(
            "Copy YAML to subdirs", Category.TOOLS, icon_name="config"
        )
        btn_copy_yaml.setToolTip(
            "Pick a YAML file from the project directory and copy it into "
            "every subdirectory (overwrites if already present)."
        )
        btn_copy_yaml.clicked.connect(self._on_copy_yaml)

        for b in (btn_convert, btn_prepend, btn_append, btn_remove, btn_combine, btn_copy_yaml):
            outer.addWidget(b)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = QToolButton()
        btn_close.setText("Close")
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)
        outer.addLayout(close_row)

    def _on_convert(self) -> None:
        self._hub._convert_subdirectories()

    def _on_rename(self, mode: str) -> None:
        prompts = {
            "prepend": ("Prepend to subdir names", "Substring to prepend:"),
            "append": ("Append to subdir names", "Substring to append:"),
            "remove": ("Remove from subdir names", "Substring to remove:"),
        }
        title, label = prompts[mode]
        text, ok = QInputDialog.getText(self, title, label)
        if not ok:
            return
        text = text.strip()
        if not text:
            QMessageBox.warning(self, "Batch tools", "Enter a non-empty substring.")
            return
        self._hub._rename_subdirectories(mode, text)

    def _on_combine(self) -> None:
        self._hub._combine_summaries()

    def _on_copy_yaml(self) -> None:
        project = self._hub._project_dir
        if project is None:
            QMessageBox.warning(self, "Batch tools", "Choose a project directory first.")
            return
        yamls = sorted(
            [p.name for p in project.iterdir()
             if p.is_file() and p.suffix.lower() in (".yaml", ".yml")]
        )
        if not yamls:
            QMessageBox.warning(
                self, "Batch tools",
                f"No YAML files found at the top of {project}."
            )
            return
        choice, ok = QInputDialog.getItem(
            self, "Copy YAML to subdirs",
            "YAML file to copy into every subdirectory:",
            yamls, 0, False,
        )
        if not ok or not choice:
            return
        self._hub._copy_yaml_to_subdirectories(project / choice)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    # Wayland uses the desktop-file name as the app id for taskbar icons;
    # setWindowIcon covers X11/Windows/macOS and window title bars.
    app.setDesktopFileName("pytrack-hub")
    app.setWindowIcon(app_icon())
    mode = ui_settings.get("theme", "auto")
    apply_theme(app, mode=mode)

    initial = sys.argv[1] if len(sys.argv) > 1 else None
    win = HubWindow(initial_project=initial)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
