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
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

# Force a non-GUI matplotlib backend before the domain layer imports pyplot.
import matplotlib

matplotlib.use("Agg")

from PyQt6.QtCore import QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
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
from ..ui import (
    ActionButton,
    Card,
    Category,
    OutputLog,
    PlotDock,
    SidebarNav,
    TopBar,
    apply_theme,
    icon,
    resolved_mode,
)
from ..ui import settings as ui_settings
from .common import TaskWorker, capture_figures


class HubWindow(QMainWindow):
    """The Analysis Hub main window."""

    def __init__(self, initial_project: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("PyTrackingAnalysis — Analysis Hub")
        self.resize(1350, 860)

        self._exp: ExperimentMod.Experiment | None = None
        self._project_dir: Path | None = None
        self._worker: TaskWorker | None = None
        # Maps a Plots-card ActionButton to its Arena method name; rebuilt whenever
        # an experiment is loaded so the buttons always reflect the tracking type.
        self._plot_buttons: list[ActionButton] = []
        # Cards we reference by sidebar key so clicking a sidebar item scrolls to it.
        self._cards: dict[str, Card] = {}
        self._scripts: list[dict] = []

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
        self._sidebar.add_item("load", "Load", "load", category=Category.LOAD)
        self._sidebar.add_item("analyze", "Analyze", "basic", category=Category.ANALYZE)
        self._sidebar.add_item("plots", "Plots", "plots", category=Category.PLOTS)
        self._sidebar.add_item("scripts", "Scripts", "scripts", category=Category.SCRIPTS)
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
        self._build_tools_card()
        self._cards_lay.addStretch(1)

        scroll.setWidget(cards_host)
        left_lay.addWidget(scroll, 1)
        left_host.setMinimumWidth(420)
        splitter.addWidget(left_host)

        # Right: plot dock
        self._log = OutputLog()
        self._plot_dock = PlotDock(self._log)
        self._plot_dock.setMinimumWidth(420)
        splitter.addWidget(self._plot_dock)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([500, 850])

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
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._project_edit = QLineEdit()
        self._project_edit.setPlaceholderText("/path/to/experiment/folder")
        self._project_edit.setReadOnly(True)
        browse = ActionButton("Browse…", Category.NEUTRAL, icon_name="browse")
        browse.clicked.connect(self._pick_project_dir)
        reload_btn = ActionButton("Reload", Category.TOOLS, icon_name="clear")
        reload_btn.clicked.connect(self._reload_project)
        row = QHBoxLayout()
        row.addWidget(self._project_edit, 1)
        row.addWidget(browse)
        row.addWidget(reload_btn)
        form.addRow("Project dir:", _wrap_layout(row))

        self._config_combo = QComboBox()
        self._config_combo.setToolTip("YAML configs found in the project dir.")
        form.addRow("Config:", self._config_combo)

        card.add_body(form)

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
        self._mode_batch = QRadioButton("Batch parent")
        self._mode_single.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._mode_single)
        mode_group.addButton(self._mode_batch)
        mode_group.buttonClicked.connect(self._on_mode_changed)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self._mode_single)
        mode_row.addWidget(self._mode_batch)
        mode_row.addStretch(1)
        card.add_body(mode_row)

        self._batch_parent_edit = QLineEdit()
        self._batch_parent_edit.setPlaceholderText(
            "(batch mode) parent folder containing experiment subdirs"
        )
        self._batch_parent_edit.setReadOnly(True)
        self._batch_parent_edit.setEnabled(False)
        batch_browse = ActionButton("Browse…", Category.NEUTRAL, icon_name="browse")
        batch_browse.clicked.connect(self._pick_batch_parent)
        batch_row = QHBoxLayout()
        batch_row.addWidget(self._batch_parent_edit, 1)
        batch_row.addWidget(batch_browse)
        card.add_body(batch_row)
        self._batch_parent_browse = batch_browse
        self._batch_parent_browse.setEnabled(False)

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

        self._btn_run_batch = ActionButton(
            "Run Batch…", Category.LOAD, icon_name="batch"
        )
        self._btn_run_batch.clicked.connect(self._run_batch)
        self._btn_run_batch.setVisible(False)  # shown in batch mode

        for btn in (
            self._btn_run_analysis,
            self._btn_run_qc,
            self._btn_create_report,
            self._btn_run_batch,
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

    # ---------------- Tools card ----------------

    def _build_tools_card(self) -> None:
        card = Card(
            "Tools",
            category=Category.TOOLS,
            subtitle="Housekeeping.",
            icon_name="tools",
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
        for b in (btn_validate, btn_open_analysis, btn_open_qc, btn_clear_cache):
            card.add_body(b)
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

    def _pick_batch_parent(self) -> None:
        start = str(self._project_dir.parent) if self._project_dir else os.getcwd()
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose parent directory of experiments", start
        )
        if chosen:
            self._batch_parent_edit.setText(chosen)

    def _on_mode_changed(self) -> None:
        is_batch = self._mode_batch.isChecked()
        self._batch_parent_edit.setEnabled(is_batch)
        self._batch_parent_browse.setEnabled(is_batch)
        self._btn_run_batch.setVisible(is_batch)
        # Single-project analyses only make sense for single mode
        for btn in (
            self._btn_run_analysis,
            self._btn_run_qc,
            self._btn_create_report,
        ):
            btn.setVisible(not is_batch)

    def _set_project_dir(self, path: str | Path) -> None:
        p = Path(path).expanduser().resolve()
        self._project_dir = p
        self._project_edit.setText(str(p))
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
        self._refresh_scripts()

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

    def _refresh_scripts(self) -> None:
        from ..script_editor.runner import load_scripts

        cfg = self._config_path()
        scripts: list[dict] = []
        if cfg and cfg.exists():
            try:
                scripts = load_scripts(cfg)
            except Exception as err:  # noqa: BLE001
                self._log.append_line(f"[scripts] failed to read {cfg}: {err}")
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
            self._log.append_line(msg)

        # Dispatch through our regular TaskWorker for thread safety + log redirect
        self._spawn_task_with_callbacks("Script run", _run, _on_ok, _on_fail)

    # ==================================================================
    # Behaviour — loading an Experiment
    # ==================================================================

    def _load_experiment(self) -> None:
        if self._mode_batch.isChecked():
            self._log.append_line(
                "Batch mode: Load is not needed — click 'Run Batch…' directly."
            )
            return
        if not self._project_dir:
            self._warn("Choose a project directory first.")
            return
        try:
            self._log.append_line(f"Loading experiment from {self._project_dir}…")
            exp = ExperimentMod.Experiment(str(self._project_dir))
            self._exp = exp
            self._log.append_line(str(exp))
            self._on_experiment_ready()
        except Exception as err:  # noqa: BLE001
            import traceback

            self._log.append_line(traceback.format_exc())
            self._warn(f"Failed to load experiment: {err}")

    def _on_experiment_ready(self) -> None:
        # Enable single-mode analysis buttons
        for btn in (
            self._btn_run_analysis,
            self._btn_run_qc,
            self._btn_create_report,
        ):
            btn.setEnabled(True)
        self._rebuild_plot_buttons()

    def _rebuild_plot_buttons(self) -> None:
        # Clear existing plot buttons
        for btn in self._plot_buttons:
            btn.setParent(None)
            btn.deleteLater()
        self._plot_buttons.clear()
        self._plots_empty.setVisible(False)

        if self._exp is None:
            self._plots_empty.setVisible(True)
            return

        methods = self._exp._plot_methods()
        if not methods:
            self._plots_empty.setText(
                f"No faceted plots registered for tracking type "
                f"{self._exp.parameters.get_tracking_type().name}."
            )
            self._plots_empty.setVisible(True)
            return

        for method_name, kwargs in methods:
            title = _plot_title(method_name)
            btn = ActionButton(title, Category.PLOTS, icon_name=_plot_icon(method_name))
            btn.clicked.connect(
                lambda _=False, m=method_name, k=dict(kwargs), t=title: self._render_plot(m, k, t)
            )
            self._plots_card.add_body(btn)
            self._plot_buttons.append(btn)

    def _render_plot(self, method_name: str, kwargs: dict, title: str) -> None:
        if self._exp is None:
            return
        try:
            fn = getattr(self._exp, method_name)
        except AttributeError:
            self._log.append_line(f"Unknown plot method: {method_name}")
            return
        self._log.append_line(f"[plot] {method_name}({_fmt_kwargs(kwargs)})")
        with capture_figures() as figs:
            try:
                fn(**kwargs)
            except Exception as err:  # noqa: BLE001
                import traceback

                self._log.append_line(traceback.format_exc())
                self._warn(f"Plot failed: {err}")
                return
        if not figs:
            self._log.append_line(f"[plot] {method_name} produced no figures.")
            return
        interactive = self._interactive_checkbox.isChecked()
        for i, fig in enumerate(figs):
            tab_title = title if len(figs) == 1 else f"{title} ({i+1})"
            self._plot_dock.add_figure(tab_title, fig, interactive=interactive)

    # ==================================================================
    # Behaviour — analysis tasks (threaded)
    # ==================================================================

    def _run_full_analysis(self) -> None:
        if self._exp is None:
            return
        exp = self._exp
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
        self._spawn_task("PDF report", lambda: exp.create_report())

    def _run_batch(self) -> None:
        parent = self._batch_parent_edit.text().strip()
        if not parent:
            self._warn("Choose a batch parent directory first.")
            return
        self._spawn_task(
            "Batch analysis",
            lambda: _format_batch_result(ExperimentMod.batch_analyze(parent)),
        )

    def _spawn_task(self, task_name: str, fn: Callable[[], object]) -> None:
        self._spawn_task_with_callbacks(task_name, fn, self._on_task_ok, self._on_task_failed)

    def _spawn_task_with_callbacks(
        self,
        task_name: str,
        fn: Callable[[], object],
        on_ok: Callable[[str], None],
        on_fail: Callable[[str], None],
    ) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._warn("Another task is already running.")
            return
        self._progress.setVisible(True)
        self._set_busy(True)
        worker = TaskWorker(task_name, fn)
        worker.log_text.connect(self._log.append_line)
        worker.finished_ok.connect(on_ok)
        worker.failed.connect(on_fail)
        worker.finished.connect(lambda: self._on_task_finished(worker))
        self._worker = worker
        worker.start()

    def _on_task_ok(self, msg: str) -> None:
        self._log.append_line(msg)

    def _on_task_failed(self, msg: str) -> None:
        self._log.append_line(msg)

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
            self._btn_run_batch,
            self._load_btn,
        ):
            btn.setEnabled(
                (not busy)
                and (
                    btn is self._load_btn
                    or self._exp is not None
                )
            )

    # ==================================================================
    # Behaviour — tools
    # ==================================================================

    def _validate_yaml(self) -> None:
        if not self._project_dir:
            return
        path = self._project_dir / self._config_combo.currentText()
        try:
            import yaml

            with open(path) as f:
                yaml.safe_load(f)
            self._log.append_line(f"[validate] {path} parses cleanly.")
        except Exception as err:  # noqa: BLE001
            self._log.append_line(f"[validate] {path}: {err}")

    def _open_folder(self, subfolder: str) -> None:
        if not self._project_dir:
            return
        target = self._project_dir / subfolder
        if not target.exists():
            self._log.append_line(f"[open] {target} does not exist yet.")
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

    def _launch_subapp(self, which: str) -> None:
        """Launch the Config or QC viewer in a separate process."""
        args = [sys.executable, "-m", "pytrackinganalysis", which]
        if self._project_dir:
            args.append(str(self._project_dir))
        try:
            subprocess.Popen(args, close_fds=True)
            self._log.append_line(f"[tools] launched ptrack-{which}")
        except Exception as err:  # noqa: BLE001
            self._warn(f"Failed to launch {which}: {err}")

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

    def _warn(self, msg: str) -> None:
        QMessageBox.warning(self, "PyTrackingAnalysis", msg)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _wrap_layout(layout) -> QWidget:
    host = QWidget()
    host.setLayout(layout)
    return host


# Human-friendly titles for Arena.plot_* methods.
_PLOT_TITLES: dict[str, str] = {
    "plot_totaldistance_facet": "Total distance (facet)",
    "plot_pi_facet": "PI (facet)",
    "plot_percentage_facet": "Percentage (facet)",
    "plot_transitions_facet": "Transitions (facet)",
    "plot_adjusted_x_position_facet": "Adjusted X position (facet)",
    "plot_interactions_facet": "Interactions (facet)",
}

_PLOT_ICONS: dict[str, str] = {
    "plot_totaldistance_facet": "distance",
    "plot_pi_facet": "plot",
    "plot_percentage_facet": "plot",
    "plot_transitions_facet": "transition",
    "plot_adjusted_x_position_facet": "xy",
    "plot_interactions_facet": "plot",
}


def _plot_title(method_name: str) -> str:
    return _PLOT_TITLES.get(method_name, method_name.replace("_", " ").title())


def _plot_icon(method_name: str) -> str:
    return _PLOT_ICONS.get(method_name, "plot")


def _fmt_kwargs(kwargs: dict) -> str:
    if not kwargs:
        return ""
    return ", ".join(f"{k}={v!r}" for k, v in kwargs.items())


def _format_batch_result(result: dict[str, str]) -> str:
    ok = sum(1 for v in result.values() if v == "ok")
    lines = [f"Batch complete: {ok}/{len(result)} succeeded."]
    for path, status in result.items():
        tag = "OK  " if status == "ok" else "FAIL"
        lines.append(f"  {tag}  {path}")
        if status != "ok":
            lines.append(f"       {status}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    mode = ui_settings.get("theme", "auto")
    apply_theme(app, mode=mode)

    initial = sys.argv[1] if len(sys.argv) > 1 else None
    win = HubWindow(initial_project=initial)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
