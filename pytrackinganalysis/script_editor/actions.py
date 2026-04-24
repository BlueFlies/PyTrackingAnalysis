"""Action registry for the visual Script Editor.

Each action is a :class:`Action` with:

* a ``key`` (how it's referenced in the saved YAML),
* a ``title`` / ``description`` / ``category`` / ``icon_name`` for the UI,
* a ``params`` list of :class:`ParamSpec` describing the inspector form,
* a ``validate`` callable returning a list of error strings, and
* an ``execute`` callable that runs the action against a :class:`RunContext`.

The starter library is intentionally small — the user flagged actions as
TBD.  Extend this module and register with :data:`ACTIONS`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..ui import Category


# ---------------------------------------------------------------------------
# Parameter specs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParamSpec:
    """Describes one parameter of an action.

    ``kind`` picks the inspector widget:

    * ``"string"`` → QLineEdit
    * ``"int"``    → QSpinBox
    * ``"float"``  → QDoubleSpinBox
    * ``"bool"``   → QCheckBox
    * ``"choice"`` → QComboBox (requires ``choices``)
    * ``"path"``   → QLineEdit + browse button
    * ``"list"``   → QLineEdit (comma-separated; parsed via ``parse_list``)
    """

    name: str
    kind: str
    label: str
    default: Any = None
    help: str = ""
    choices: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None


# ---------------------------------------------------------------------------
# RunContext and Action
# ---------------------------------------------------------------------------

@dataclass
class RunContext:
    """State threaded through a script run.

    ``exp`` is set by :func:`load_experiment` and reused by subsequent
    actions.  ``log`` / ``figure`` receive plain text and matplotlib
    figures respectively so the caller (the Hub) can route them to the
    :class:`OutputLog` and :class:`PlotDock`.
    """

    project_dir: Any = None  # Path-ish
    exp: Any = None  # pytrackinganalysis.Experiment.Experiment | None
    log: Callable[[str], None] = lambda _msg: None
    figure: Callable[[str, Any], None] = lambda _title, _fig: None


@dataclass
class Action:
    key: str
    title: str
    description: str
    category: Category
    icon_name: str
    params: tuple[ParamSpec, ...]
    validate_fn: Callable[[dict, str | None], list[str]] | None = None
    execute_fn: Callable[[dict, RunContext], None] | None = None

    def validate(self, params: dict, experiment_type: str | None = None) -> list[str]:
        errs: list[str] = []
        # Generic required-field check: treat blank strings / None as missing
        # only when no default is provided.
        for spec in self.params:
            if spec.default is None and spec.name not in params:
                errs.append(f"'{spec.label}' is required")
        if self.validate_fn is not None:
            errs.extend(self.validate_fn(params, experiment_type))
        return errs

    def execute(self, params: dict, ctx: RunContext) -> None:
        if self.execute_fn is None:
            raise NotImplementedError(f"Action {self.key!r} has no execute function")
        # Merge defaults so downstream code can rely on every spec'd key existing.
        merged: dict[str, Any] = {}
        for spec in self.params:
            if spec.name in params:
                merged[spec.name] = params[spec.name]
            elif spec.default is not None:
                merged[spec.name] = spec.default
        self.execute_fn(merged, ctx)


# ---------------------------------------------------------------------------
# Helpers reused by actions
# ---------------------------------------------------------------------------

def _parse_cutoffs(s: Any) -> tuple[int, ...] | None:
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    if isinstance(s, (list, tuple)):
        return tuple(int(x) for x in s)
    return tuple(int(x.strip()) for x in str(s).split(",") if x.strip())


def _require_exp(ctx: RunContext, action: str) -> None:
    if ctx.exp is None:
        raise RuntimeError(
            f"{action}: no experiment loaded — add a 'Load experiment' step first."
        )


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def _exec_load_experiment(params: dict, ctx: RunContext) -> None:
    from .. import Experiment as ExperimentMod

    raw = (params.get("path") or "").strip()
    if raw in ("", "."):
        path = str(ctx.project_dir) if ctx.project_dir else "."
    else:
        path = raw
    force = bool(params.get("force_preprocessing", False))
    ctx.log(f"[load_experiment] {path} (force={force})")
    ctx.exp = ExperimentMod.Experiment(path, force_preprocessing=force)
    ctx.log(str(ctx.exp))


def _exec_filter_by_quality(params: dict, ctx: RunContext) -> None:
    _require_exp(ctx, "filter_by_quality")
    threshold = float(params.get("min_high_quality", 0.8))
    arena = ctx.exp.arena
    before = len(arena.trackers)
    keep: dict = {}
    for key, tracker in arena.trackers.items():
        dq = tracker.get_data_quality()
        hq = float(dq.get("HighQuality", 0.0))
        if hq >= threshold:
            keep[key] = tracker
    arena.trackers = type(arena.trackers)(keep.items())  # preserve OrderedDict-ness
    ctx.log(
        f"[filter_by_quality] threshold={threshold:.2f} kept {len(keep)}/{before} trackers"
    )


def _exec_filter_by_region(params: dict, ctx: RunContext) -> None:
    _require_exp(ctx, "filter_by_region")
    regions_raw = params.get("regions", "")
    regions = {r.strip() for r in str(regions_raw).split(",") if r.strip()}
    if not regions:
        raise ValueError("filter_by_region: please list at least one region")
    arena = ctx.exp.arena
    before = len(arena.trackers)
    keep = {
        key: t for key, t in arena.trackers.items()
        if getattr(t, "tracking_region_id", key).split("_")[0] + "_" + getattr(t, "tracking_region_id", key).split("_")[1] in regions
        or getattr(t, "tracking_region_id", None) in regions
    }
    # Fallback simple match: key prefix
    if not keep:
        keep = {k: t for k, t in arena.trackers.items() if any(k.startswith(r) for r in regions)}
    arena.trackers = type(arena.trackers)(keep.items())
    ctx.log(f"[filter_by_region] kept {len(keep)}/{before} trackers matching {regions}")


def _exec_run_qc(params: dict, ctx: RunContext) -> None:
    _require_exp(ctx, "run_qc")
    cutoff = float(params.get("qc_cutoff", 0.9))
    ctx.log(f"[run_qc] cutoff={cutoff:.2f}")
    ctx.exp.qc(cutoff=cutoff)


def _exec_run_analysis(params: dict, ctx: RunContext) -> None:
    _require_exp(ctx, "run_analysis")
    cutoffs = _parse_cutoffs(params.get("cutoffs"))
    qc_cutoff = float(params.get("qc_cutoff", 0.9))
    ctx.log(f"[run_analysis] cutoffs={cutoffs} qc_cutoff={qc_cutoff}")
    ctx.exp.run_analysis(cutoffs=cutoffs, qc_cutoff=qc_cutoff)


def _exec_save_summary_csv(params: dict, ctx: RunContext) -> None:
    _require_exp(ctx, "save_summary_csv")
    cutoffs = _parse_cutoffs(params.get("cutoffs"))
    ctx.log(f"[save_summary_csv] cutoffs={cutoffs}")
    ctx.exp.save_summary(cutoffs=cutoffs)


def _exec_run_tukey_stats(_params: dict, ctx: RunContext) -> None:
    _require_exp(ctx, "run_tukey_stats")
    ctx.log("[run_tukey_stats]")
    ctx.exp.stats()


def _exec_plot(params: dict, ctx: RunContext) -> None:
    _require_exp(ctx, "plot")
    method_name = params.get("method") or ""
    if not method_name:
        raise ValueError("plot: please pick a method")
    # Target Arena directly so Experiment's save-to-disk ``plt.show``
    # override does not swallow the Figure before us.  Fall back to the
    # Experiment wrapper only if Arena has no such method.
    arena = ctx.exp.arena
    fn = getattr(arena, method_name) if hasattr(arena, method_name) else getattr(ctx.exp, method_name)

    import matplotlib.pyplot as plt

    figures: list = []
    orig_show = plt.show

    def _capture(*_a, **_k) -> None:  # noqa: ANN002, ANN003
        figures.append(plt.gcf())

    plt.show = _capture  # type: ignore[assignment]
    try:
        kwargs: dict[str, Any] = {}
        cutoffs = _parse_cutoffs(params.get("cutoffs"))
        if method_name.endswith("_facet") and cutoffs:
            kwargs["cutoffs"] = cutoffs
        elif method_name.endswith("_facet") and ctx.exp.facet_cutoffs is not None:
            kwargs["cutoffs"] = ctx.exp.facet_cutoffs
        ctx.log(f"[plot] {method_name}({kwargs})")
        fn(**kwargs)
    finally:
        plt.show = orig_show  # type: ignore[assignment]

    title = _plot_title(method_name)
    for i, fig in enumerate(figures):
        tab_title = title if len(figures) == 1 else f"{title} ({i+1})"
        ctx.figure(tab_title, fig)


def _exec_create_report(params: dict, ctx: RunContext) -> None:
    _require_exp(ctx, "create_report")
    cutoffs = _parse_cutoffs(params.get("cutoffs"))
    qc_cutoff = float(params.get("qc_cutoff", 0.9))
    ctx.log(f"[create_report] cutoffs={cutoffs} qc_cutoff={qc_cutoff}")
    path = ctx.exp.create_report(cutoffs=cutoffs, qc_cutoff=qc_cutoff)
    ctx.log(f"[create_report] wrote {path}")


def _exec_batch_analyze(params: dict, ctx: RunContext) -> None:
    from .. import Experiment as ExperimentMod

    raw = (params.get("parent_path") or "").strip()
    if raw in ("", "."):
        parent = str(ctx.project_dir) if ctx.project_dir else "."
    else:
        parent = raw
    force = bool(params.get("force_preprocessing", False))
    ctx.log(f"[batch_analyze] parent={parent} force={force}")
    result = ExperimentMod.batch_analyze(parent, force_preprocessing=force)
    ok = sum(1 for v in result.values() if v == "ok")
    ctx.log(f"[batch_analyze] {ok}/{len(result)} succeeded")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _validate_filter_by_quality(params: dict, _exp_type: str | None) -> list[str]:
    errs: list[str] = []
    try:
        thr = float(params.get("min_high_quality", 0.8))
        if not 0.0 <= thr <= 1.0:
            errs.append("min_high_quality must be between 0 and 1")
    except (TypeError, ValueError):
        errs.append("min_high_quality must be a number")
    return errs


def _validate_cutoffs(params: dict, _exp_type: str | None) -> list[str]:
    raw = params.get("cutoffs")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return []
    try:
        _parse_cutoffs(raw)
    except (TypeError, ValueError):
        return ["cutoffs must be a comma-separated list of integers"]
    return []


# Valid plot methods per TrackingType (used for choice validation + inspector dropdown).
_PLOTS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "TRACKER": ("plot_totaldistance_facet",),
    "TWOCHOICETRACKER": (
        "plot_pi_facet",
        "plot_percentage_facet",
        "plot_transitions_facet",
        "plot_totaldistance_facet",
    ),
    "TWOCHOICECOUNTER": ("plot_pi_facet", "plot_percentage_facet"),
    "XCHOICETRACKER": (
        "plot_adjusted_x_position_facet",
        "plot_totaldistance_facet",
    ),
    "PAIRWISEINTERACTIONTRACKER": (
        "plot_interactions_facet",
        "plot_totaldistance_facet",
    ),
    "PAIRWISEINTERACTIONCOUNTER": ("plot_interactions_facet",),
}

_ALL_PLOT_METHODS: tuple[str, ...] = tuple(sorted({
    m for methods in _PLOTS_BY_TYPE.values() for m in methods
}))


def plot_methods_for_type(experiment_type: str | None) -> tuple[str, ...]:
    if experiment_type and experiment_type in _PLOTS_BY_TYPE:
        return _PLOTS_BY_TYPE[experiment_type]
    return _ALL_PLOT_METHODS


_PLOT_TITLES: dict[str, str] = {
    "plot_totaldistance_facet": "Total distance (facet)",
    "plot_pi_facet": "PI (facet)",
    "plot_percentage_facet": "Percentage (facet)",
    "plot_transitions_facet": "Transitions (facet)",
    "plot_adjusted_x_position_facet": "Adjusted X position (facet)",
    "plot_interactions_facet": "Interactions (facet)",
}


def _plot_title(method_name: str) -> str:
    return _PLOT_TITLES.get(method_name, method_name.replace("_", " ").title())


def _validate_plot(params: dict, experiment_type: str | None) -> list[str]:
    method = params.get("method", "")
    if not method:
        return ["method is required"]
    allowed = plot_methods_for_type(experiment_type)
    if experiment_type and method not in allowed:
        return [f"method {method!r} is not valid for tracking type {experiment_type}"]
    return _validate_cutoffs(params, experiment_type)


# ---------------------------------------------------------------------------
# Registered actions
# ---------------------------------------------------------------------------

ACTIONS: dict[str, Action] = {
    "load_experiment": Action(
        key="load_experiment",
        title="Load experiment",
        description="Load an Experiment from a project directory (data/*.xlsx + tracking_config.yaml).",
        category=Category.LOAD,
        icon_name="load",
        params=(
            ParamSpec("path", "path", "Project dir", default=".", help="Defaults to the script's project dir."),
            ParamSpec("force_preprocessing", "bool", "Force preprocessing", default=False),
        ),
        execute_fn=_exec_load_experiment,
    ),
    "filter_by_quality": Action(
        key="filter_by_quality",
        title="Filter trackers by quality",
        description="Drop trackers whose %HighQuality is below the threshold.",
        category=Category.QC,
        icon_name="quality",
        params=(
            ParamSpec("min_high_quality", "float", "min_high_quality", default=0.8, min=0.0, max=1.0),
        ),
        validate_fn=_validate_filter_by_quality,
        execute_fn=_exec_filter_by_quality,
    ),
    "filter_by_region": Action(
        key="filter_by_region",
        title="Filter trackers by region",
        description="Keep only trackers whose tracking_region matches the list.",
        category=Category.QC,
        icon_name="quality",
        params=(
            ParamSpec("regions", "list", "regions (comma-separated)", default="T_0, T_1"),
        ),
        execute_fn=_exec_filter_by_region,
    ),
    "run_qc": Action(
        key="run_qc",
        title="Run QC",
        description="Print a data-quality report and write {exp}_data_quality.csv.",
        category=Category.ANALYZE,
        icon_name="quality",
        params=(
            ParamSpec("qc_cutoff", "float", "qc_cutoff", default=0.9, min=0.0, max=1.0),
        ),
        execute_fn=_exec_run_qc,
    ),
    "run_analysis": Action(
        key="run_analysis",
        title="Run full analysis",
        description="Run QC, write summary/facet CSVs, save plots, and run stats.",
        category=Category.ANALYZE,
        icon_name="basic",
        params=(
            ParamSpec("cutoffs", "list", "cutoffs (minutes, comma-sep)", default=""),
            ParamSpec("qc_cutoff", "float", "qc_cutoff", default=0.9, min=0.0, max=1.0),
        ),
        validate_fn=_validate_cutoffs,
        execute_fn=_exec_run_analysis,
    ),
    "save_summary_csv": Action(
        key="save_summary_csv",
        title="Export Summary CSV",
        description="Write {exp}_Summary.csv and, if cutoffs, {exp}_Summary_Facet.csv.",
        category=Category.ANALYZE,
        icon_name="csv",
        params=(
            ParamSpec("cutoffs", "list", "cutoffs (minutes, comma-sep)", default=""),
        ),
        validate_fn=_validate_cutoffs,
        execute_fn=_exec_save_summary_csv,
    ),
    "run_tukey_stats": Action(
        key="run_tukey_stats",
        title="Run Tukey HSD stats",
        description="Write {exp}_Stats.txt with pairwise comparisons.",
        category=Category.ANALYZE,
        icon_name="compare",
        params=(),
        execute_fn=_exec_run_tukey_stats,
    ),
    "plot": Action(
        key="plot",
        title="Add plot to output",
        description="Run an Arena.plot_* method and send the figure to the Hub's PlotDock.",
        category=Category.PLOTS,
        icon_name="plot",
        params=(
            ParamSpec(
                "method", "choice", "method",
                default="plot_totaldistance_facet",
                choices=_ALL_PLOT_METHODS,
            ),
            ParamSpec("cutoffs", "list", "cutoffs (minutes, comma-sep)", default=""),
        ),
        validate_fn=_validate_plot,
        execute_fn=_exec_plot,
    ),
    "create_report": Action(
        key="create_report",
        title="Create PDF report",
        description="Write {exp}_report.pdf with QC tables, tracker grids, and plots.",
        category=Category.ANALYZE,
        icon_name="report",
        params=(
            ParamSpec("cutoffs", "list", "cutoffs (minutes, comma-sep)", default=""),
            ParamSpec("qc_cutoff", "float", "qc_cutoff", default=0.9, min=0.0, max=1.0),
        ),
        validate_fn=_validate_cutoffs,
        execute_fn=_exec_create_report,
    ),
    "batch_analyze": Action(
        key="batch_analyze",
        title="Run batch analysis",
        description="Run Experiment.run_analysis() + create_report() on every valid subdir.",
        category=Category.LOAD,
        icon_name="batch",
        params=(
            ParamSpec("parent_path", "path", "parent dir", default="."),
            ParamSpec("force_preprocessing", "bool", "Force preprocessing", default=False),
        ),
        execute_fn=_exec_batch_analyze,
    ),
}


def validation_issues(steps: list[dict], experiment_type: str | None) -> list[tuple[int, str]]:
    """Return ``[(step_index, error), …]`` for an entire script.

    *experiment_type* is inferred at runtime by the runner once a
    ``load_experiment`` step has executed; the editor passes ``None`` when
    nothing is loaded, so some validations (e.g. ``plot`` method) are
    deferred until runtime.
    """
    issues: list[tuple[int, str]] = []
    for i, step in enumerate(steps):
        key = step.get("action", "")
        action = ACTIONS.get(key)
        if action is None:
            issues.append((i, f"unknown action {key!r}"))
            continue
        for err in action.validate(step.get("params", {}), experiment_type=experiment_type):
            issues.append((i, err))
    return issues
