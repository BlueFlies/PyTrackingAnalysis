"""QC Viewer — standalone window for per-tracker data quality.

Loads an :class:`Experiment` from a project directory and renders:

* a sortable table of all trackers with %HighQuality, %NotFound,
  %Indiscernible, start/end minutes (colour-coded green / red against a
  user-configurable qc_cutoff);
* on tracker selection, :class:`PlotDock` tabs with XY trajectory, X/Y
  vs time, cumulative distance, and a data-quality timeline.

Heavy reuse of :meth:`Arena.get_data_quality` and per-tracker
``rawdata``; new per-tracker plots are built locally (not through
:meth:`Experiment.save_tracker_grid_plots`) so the QC viewer stays
independent of the report-generation code path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Force non-GUI mpl backend before the domain imports pyplot.
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTableView,
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
    TopBar,
    ZoomableImageView,
    app_icon,
    apply_theme,
    icon,
    resolved_mode,
)
from ..ui import settings as ui_settings
from ..ui.table_model import DataFrameModel



class QcViewerWindow(QMainWindow):
    # Fixed thresholds for row colouring (HighQuality column).
    _THR_GREEN = 0.90
    _THR_YELLOW = 0.80

    def __init__(self, initial_project: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("PyTrackingAnalysis — QC Viewer")
        self.resize(1430, 860)
        self._exp: ExperimentMod.Experiment | None = None
        self._project_dir: Optional[Path] = None
        self._dq: pd.DataFrame = pd.DataFrame()

        self._build_ui()

        if initial_project:
            self._load_project(Path(initial_project).expanduser().resolve())

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
        self._top_bar = TopBar("QC Viewer")
        self._path_lbl = QLabel("(no project)")
        self._top_bar.add_right(self._path_lbl)

        btn_reload = QToolButton()
        btn_reload.setIcon(icon("refresh"))
        btn_reload.setIconSize(QSize(18, 18))
        btn_reload.setAutoRaise(True)
        btn_reload.setToolTip("Reload")
        btn_reload.clicked.connect(self._reload)
        self._top_bar.add_right(btn_reload)

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

        # ── Splitter: left (trackers + tools) / right (PlotDock) ────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left
        left_host = QWidget()
        left_lay = QVBoxLayout(left_host)
        left_lay.setContentsMargins(12, 12, 12, 12)
        left_lay.setSpacing(12)

        trackers_card = Card(
            "Trackers",
            category=Category.QC,
            subtitle="Rows tinted by %HighQuality: green ≥ 0.90, yellow 0.80–0.90, red < 0.80.",
            icon_name="qc",
        )

        header_row = QHBoxLayout()
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter by tracker name…")
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._apply_filter)
        header_row.addWidget(self._filter_edit, 1)
        trackers_card.add_body(header_row)

        self._model = DataFrameModel(row_color=self._color_for_row)
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        # We supply our own per-row tints (band + alternating shade) via
        # _color_for_row, so let Qt skip its default alternateBase fill.
        self._table.setAlternatingRowColors(False)
        self._table.setMinimumHeight(300)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.selectionModel().selectionChanged.connect(self._on_row_selected)
        trackers_card.add_body(self._table)

        self._summary_lbl = QLabel("(load a project to see trackers)")
        self._summary_lbl.setStyleSheet("color: palette(mid); font-size: 9pt;")
        trackers_card.add_body(self._summary_lbl)

        left_lay.addWidget(trackers_card, 1)

        tools_card = Card(
            "Export",
            category=Category.TOOLS,
            icon_name="csv",
        )
        btn_export = ActionButton(
            "Export data_quality.csv", Category.TOOLS, icon_name="csv"
        )
        btn_export.clicked.connect(self._export_csv)
        tools_card.add_body(btn_export)
        left_lay.addWidget(tools_card)

        left_host.setMinimumWidth(560)
        splitter.addWidget(left_host)

        # Right: PlotDock
        self._log = OutputLog()
        self._err_log = OutputLog()
        self._plot_dock = PlotDock(self._log, self._err_log)
        self._plot_dock.setMinimumWidth(520)
        splitter.addWidget(self._plot_dock)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([620, 810])
        outer.addWidget(splitter, 1)

        self._apply_text_styles()

    def _apply_text_styles(self) -> None:
        """Force high-contrast text on the trackers table and project path label.

        qdarktheme's palette(text)/palette(mid) read as muted greys; the row
        tints in the trackers grid wash them out further. We override with
        explicit colors per theme and re-apply on theme toggle.
        """
        if resolved_mode() == "dark":
            table_fg = "#ffffff"
            path_fg = "#e2e8f0"
        else:
            table_fg = "#0f172a"
            path_fg = "#1e293b"
        self._table.setStyleSheet(f"QTableView {{ color: {table_fg}; }}")
        self._path_lbl.setStyleSheet(
            f"color: {path_fg}; padding-right: 8px; font-weight: 500;"
        )

    # ==================================================================
    # Project loading
    # ==================================================================

    def _log_issue(self, msg: str) -> None:
        """Log *msg* to the Errors tab as well as the chronological Output tab."""
        self._log.append_line(msg)
        self._err_log.append_line(msg)

    def _reload(self) -> None:
        if self._project_dir:
            self._load_project(self._project_dir)

    def _load_project(self, path: Path) -> None:
        self._project_dir = path
        self._path_lbl.setText(path.name or str(path))
        self._path_lbl.setToolTip(str(path))
        self.setWindowTitle(f"PyTrackingAnalysis — QC Viewer — {path.name}")
        self._log.append_line(f"Loading experiment from {path}…")
        try:
            self._exp = ExperimentMod.Experiment(str(path))
        except Exception as err:  # noqa: BLE001
            import traceback

            self._log_issue(traceback.format_exc())
            QMessageBox.critical(self, "Load failed", str(err))
            return
        ui_settings.add_recent_project(path)
        self._log.append_line(str(self._exp))
        self._refresh_table()
        self._show_qc_artifacts()

    def _show_qc_artifacts(self) -> None:
        """Add a PlotDock tab for every ``*_qc_*.png`` in the project's qc/ folder."""
        if self._exp is None:
            return
        qc_dir = Path(self._exp.qc_path)
        if not qc_dir.exists():
            return
        pngs = sorted(qc_dir.glob("*_qc_*.png"))
        if not pngs:
            self._log_issue(
                f"[qc] no QC artifacts found in {qc_dir} "
                "(re-load via the Hub to regenerate)"
            )
            return
        for png in pngs:
            self._add_png_tab(png)

    def _add_png_tab(self, png_path: Path) -> None:
        """Embed a PNG as a zoomable tab in the PlotDock."""
        view = ZoomableImageView(png_path)
        if view.is_empty():
            self._log_issue(f"[qc] failed to load {png_path}")
            return
        # Drop the leading "<exp>_qc_" prefix and the ".png" suffix to keep tab titles short.
        title = png_path.stem
        prefix = f"{self._exp.arena.experiment_name}_qc_"
        if title.startswith(prefix):
            title = title[len(prefix):]
        idx = self._plot_dock.addTab(view, icon("qc", category=Category.QC), title)
        self._plot_dock.setCurrentIndex(idx)

    def _refresh_table(self) -> None:
        if self._exp is None:
            return
        df = self._exp.arena.get_data_quality().copy()
        df.reset_index(drop=True, inplace=True)
        self._dq = df
        self._model.set_dataframe(df)
        n = len(df)
        green = int((df["HighQuality"] >= self._THR_GREEN).sum())
        yellow = int(((df["HighQuality"] >= self._THR_YELLOW)
                      & (df["HighQuality"] < self._THR_GREEN)).sum())
        red = n - green - yellow
        self._summary_lbl.setText(
            f"{green} green (≥ {self._THR_GREEN:.2f})  ·  "
            f"{yellow} yellow ({self._THR_YELLOW:.2f}–{self._THR_GREEN:.2f})  ·  "
            f"{red} red (< {self._THR_YELLOW:.2f})  ·  {n} total"
        )

    # ==================================================================
    # Row colouring + selection
    # ==================================================================

    def _color_for_row(self, row_idx: int) -> QColor | None:
        df = self._model.dataframe()
        if df.empty or not (0 <= row_idx < len(df)):
            return None
        hq = float(df.iloc[row_idx].get("HighQuality", 0.0))
        # Two alpha shades per band keep the visual cue of alternating rows
        # without leaking the default palette(alternateBase) through the tint.
        alpha = 42 if (row_idx % 2) else 22
        if hq >= self._THR_GREEN:
            return QColor(34, 197, 94, alpha)    # analyze-green
        if hq >= self._THR_YELLOW:
            return QColor(245, 158, 11, alpha)   # amber/yellow
        return QColor(220, 38, 38, alpha)        # qc-red

    def _apply_filter(self, text: str) -> None:
        if self._dq.empty:
            return
        needle = text.strip().lower()
        if not needle:
            self._model.set_dataframe(self._dq)
            return
        mask = self._dq["Tracker"].astype(str).str.lower().str.contains(needle, regex=False)
        self._model.set_dataframe(self._dq[mask].reset_index(drop=True))

    def _on_row_selected(self, *_args) -> None:
        sel = self._table.selectionModel().selectedRows()
        if not sel:
            return
        df = self._model.dataframe()
        if df.empty:
            return
        tracker_name = str(df.iloc[sel[0].row()]["Tracker"])
        self._show_tracker_plots(tracker_name)

    # ==================================================================
    # Per-tracker plots
    # ==================================================================

    def _show_tracker_plots(self, tracker_name: str) -> None:
        if self._exp is None:
            return
        trackers = self._exp.arena.trackers
        tracker = trackers.get(tracker_name)
        if tracker is None:
            # Arena keys can be "region_objectid" or just the region; try a
            # fuzzy prefix match.
            for k, t in trackers.items():
                if k == tracker_name or k.startswith(tracker_name):
                    tracker = t
                    break
        if tracker is None:
            self._log_issue(f"[qc] tracker {tracker_name!r} not found")
            return

        rawdata = getattr(tracker, "rawdata", None)
        if rawdata is None or rawdata.empty:
            self._log_issue(f"[qc] tracker {tracker_name} has no raw data")
            return

        dq = tracker.get_data_quality()
        hq = _scalar(dq.get("HighQuality", 0.0))
        nf = _scalar(dq.get("NotFound", 0.0))
        ind = _scalar(dq.get("Indiscernible", 0.0))
        self._log.append_line(
            f"[qc] {tracker_name}: HighQuality={hq:.2%}  "
            f"NotFound={nf:.2%}  Indiscernible={ind:.2%}"
        )

        self._plot_xy(tracker_name, rawdata)
        self._plot_distance(tracker_name, rawdata)
        self._plot_xy_vs_time(tracker_name, rawdata)
        self._plot_quality_timeline(tracker_name, rawdata)

    def _plot_xy(self, name: str, df: pd.DataFrame) -> None:
        if not {"RelX", "RelY", "Minutes"}.issubset(df.columns):
            return
        fig = plt.figure(figsize=(6, 6))
        ax = fig.add_subplot(111)
        sc = ax.scatter(
            df["RelX"], df["RelY"], c=df["Minutes"],
            cmap="viridis", s=3, alpha=0.7,
        )
        ax.set_xlabel("RelX")
        ax.set_ylabel("RelY")
        ax.set_title(f"{name} — XY trajectory")
        ax.set_aspect("equal", adjustable="datalim")
        fig.colorbar(sc, ax=ax, label="Minutes")
        fig.tight_layout()
        self._plot_dock.add_figure(f"{name} — XY", fig)

    def _plot_distance(self, name: str, df: pd.DataFrame) -> None:
        if not {"Minutes", "Dist_mm"}.issubset(df.columns):
            return
        fig = plt.figure(figsize=(7, 3.5))
        ax = fig.add_subplot(111)
        ax.plot(df["Minutes"], df["Dist_mm"].cumsum(), linewidth=1.0)
        ax.set_xlabel("Minutes")
        ax.set_ylabel("Cumulative distance (mm)")
        ax.set_title(f"{name} — Total distance over time")
        fig.tight_layout()
        self._plot_dock.add_figure(f"{name} — Distance", fig)

    def _plot_xy_vs_time(self, name: str, df: pd.DataFrame) -> None:
        if not {"Minutes", "RelX", "RelY"}.issubset(df.columns):
            return
        fig = plt.figure(figsize=(7, 4))
        ax1 = fig.add_subplot(211)
        ax1.plot(df["Minutes"], df["RelX"], linewidth=0.8)
        ax1.set_ylabel("RelX")
        ax1.set_title(f"{name} — X / Y vs time")
        ax2 = fig.add_subplot(212, sharex=ax1)
        ax2.plot(df["Minutes"], df["RelY"], linewidth=0.8)
        ax2.set_ylabel("RelY")
        ax2.set_xlabel("Minutes")
        fig.tight_layout()
        self._plot_dock.add_figure(f"{name} — X/Y(t)", fig)

    def _plot_quality_timeline(self, name: str, df: pd.DataFrame) -> None:
        if not {"Minutes", "DataQuality"}.issubset(df.columns):
            return
        fig = plt.figure(figsize=(7, 2.3))
        ax = fig.add_subplot(111)
        cats = list(dict.fromkeys(df["DataQuality"].astype(str).tolist()))
        code_map = {c: i for i, c in enumerate(cats)}
        codes = df["DataQuality"].astype(str).map(code_map).to_numpy()
        ax.scatter(df["Minutes"], codes, c=codes, cmap="viridis", s=2)
        ax.set_yticks(range(len(cats)))
        ax.set_yticklabels(cats)
        ax.set_xlabel("Minutes")
        ax.set_title(f"{name} — Data quality timeline")
        fig.tight_layout()
        self._plot_dock.add_figure(f"{name} — Quality", fig)

    # ==================================================================
    # Export / theme toggle
    # ==================================================================

    def _export_csv(self) -> None:
        if self._dq.empty or self._exp is None:
            return
        start = str(
            Path(self._exp.qc_path)
            / f"{self._exp.arena.experiment_name}_data_quality.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export data_quality.csv", start, "CSV (*.csv)"
        )
        if not path:
            return
        try:
            self._dq.to_csv(path, index=False)
        except Exception as err:  # noqa: BLE001
            self._log_issue(f"[qc] export failed: {err}")
            QMessageBox.critical(self, "Export failed", str(err))
            return
        self._log.append_line(f"[qc] wrote {path}")

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
        self._apply_text_styles()


def _scalar(value) -> float:
    """Coerce a scalar or 1-element pandas Series to a plain float."""
    if hasattr(value, "iloc"):
        try:
            return float(value.iloc[0])
        except (IndexError, ValueError, TypeError):
            return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    # Wayland uses the desktop-file name as the app id for taskbar icons;
    # setWindowIcon covers X11/Windows/macOS and window title bars.
    app.setDesktopFileName("pytrack-qc")
    app.setWindowIcon(app_icon())
    mode = ui_settings.get("theme", "auto")
    apply_theme(app, mode=mode)

    initial = sys.argv[1] if len(sys.argv) > 1 else None
    win = QcViewerWindow(initial_project=initial)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
