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
    # Tracking types this action is relevant for. ``None`` means "any" — used
    # by Palette.set_experiment_type to hide actions that don't apply to the
    # currently-loaded tracking type.
    applicable_types: tuple[str, ...] | None = None

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

    def applies_to(self, experiment_type: str | None) -> bool:
        """Return True if this action should appear in the palette for *experiment_type*."""
        if self.applicable_types is None or experiment_type is None:
            return True
        return experiment_type in self.applicable_types

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


def _exec_summarize(params: dict, ctx: RunContext) -> None:
    """Mirrors the Hub's Summarize button (with the Faceted checkbox)."""
    _require_exp(ctx, "summarize")
    facet = bool(params.get("facet", True))
    if facet:
        cutoffs = ctx.exp.facet_cutoffs
        if cutoffs is None:
            ctx.log("[summarize] facet=True but no facet_cutoffs in config — running flat only.")
        ctx.log(f"[summarize] facet={facet} cutoffs={cutoffs}")
        ctx.exp.save_summary(cutoffs=cutoffs)
    else:
        ctx.log("[summarize] facet=False")
        ctx.exp.save_summary(cutoffs=None)


def _exec_run_pairwise_comparisons(params: dict, ctx: RunContext) -> None:
    """Mirrors the Hub's Run pairwise comparisons button."""
    _require_exp(ctx, "run_pairwise_comparisons")
    facet = bool(params.get("facet", True))
    if facet:
        cutoffs = ctx.exp.facet_cutoffs
        if cutoffs is None:
            ctx.log(
                "[run_pairwise_comparisons] facet=True but no facet_cutoffs in config — "
                "skipping facet, running flat."
            )
            _run_flat_pairwise(ctx)
            return
        ctx.log(f"[run_pairwise_comparisons] facet=True cutoffs={cutoffs}")
        ctx.exp.stats(cutoffs=cutoffs, save=True)
    else:
        ctx.log("[run_pairwise_comparisons] facet=False")
        _run_flat_pairwise(ctx)


def _run_flat_pairwise(ctx: RunContext) -> None:
    """Run flat (non-faceted) pairwise comparisons for every relevant metric."""
    import io as _io
    import os as _os
    import sys as _sys

    exp = ctx.exp
    metrics = exp._stats_metrics()
    if not metrics:
        ctx.log("[run_pairwise_comparisons] no metrics for this tracking type")
        return

    buf = _io.StringIO()
    saved = _sys.stdout
    _sys.stdout = buf
    try:
        for metric in metrics:
            try:
                exp.arena.run_pairwise_comparisons(metric=metric)
            except Exception as err:  # noqa: BLE001
                print(f"Warning: could not run comparison for '{metric}': {err}")
    finally:
        _sys.stdout = saved

    text = buf.getvalue()
    ctx.log(text)
    path = _os.path.join(
        exp.analysis_path, f"{exp.arena.experiment_name}_Stats_flat.txt"
    )
    with open(path, "w") as f:
        f.write(text)
    ctx.log(f"Saved: {path}")


def _make_plot_executor(base_method: str):
    """Build an executor for a per-type plot action with a ``facet`` boolean."""

    def _exec(params: dict, ctx: RunContext) -> None:
        _require_exp(ctx, base_method)
        facet = bool(params.get("facet", True))
        method_name = f"{base_method}_facet" if facet else base_method
        kwargs: dict[str, Any] = {}
        if facet:
            if ctx.exp.facet_cutoffs is None:
                ctx.log(
                    f"[{base_method}] facet=True but no facet_cutoffs configured — "
                    f"falling back to flat ``{base_method}``."
                )
                method_name = base_method
            else:
                kwargs["cutoffs"] = tuple(ctx.exp.facet_cutoffs)

        arena = ctx.exp.arena
        fn = getattr(arena, method_name, None)
        if fn is None:
            raise ValueError(f"Arena has no method {method_name!r}")

        import matplotlib.pyplot as plt

        figures: list = []
        orig_show = plt.show

        def _capture(*_a, **_k) -> None:  # noqa: ANN002, ANN003
            figures.append(plt.gcf())

        plt.show = _capture  # type: ignore[assignment]
        try:
            ctx.log(f"[{base_method}] arena.{method_name}({kwargs})")
            fn(**kwargs)
        finally:
            plt.show = orig_show  # type: ignore[assignment]

        title = _PLOT_TITLES.get(base_method, base_method.replace("_", " ").title())
        if facet and method_name.endswith("_facet"):
            title = f"{title} (facet)"
        for i, fig in enumerate(figures):
            tab_title = title if len(figures) == 1 else f"{title} ({i+1})"
            ctx.figure(tab_title, fig)

    return _exec


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


# Per-tracking-type plot button mapping. Each entry is (base_method, label,
# applicable_types). The executor uses ``base_method`` for flat and
# ``base_method + "_facet"`` for the faceted variant. ``label`` is the user-facing
# title in the palette and the resulting PlotDock tab.
_PLOT_BUTTON_DEFS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "plot_pi", "PI",
        ("TWOCHOICETRACKER", "TWOCHOICECOUNTER"),
    ),
    (
        "plot_percentage", "Percentage",
        ("TWOCHOICETRACKER", "TWOCHOICECOUNTER"),
    ),
    (
        "plot_transitions", "Transitions",
        ("TWOCHOICETRACKER",),
    ),
    (
        "plot_totaldistance", "Total distance",
        (
            "TRACKER", "TWOCHOICETRACKER", "XCHOICETRACKER",
            "PAIRWISEINTERACTIONTRACKER",
        ),
    ),
    (
        "plot_adjusted_x_position", "Adjusted X position",
        ("XCHOICETRACKER",),
    ),
    (
        "plot_interactions", "Interactions",
        ("PAIRWISEINTERACTIONTRACKER", "PAIRWISEINTERACTIONCOUNTER"),
    ),
)

_PLOT_TITLES: dict[str, str] = {base: label for base, label, _ in _PLOT_BUTTON_DEFS}

_PLOT_ICON_BY_LABEL: dict[str, str] = {
    "Total distance": "distance",
    "PI": "plot",
    "Percentage": "plot",
    "Transitions": "transition",
    "Adjusted X position": "xy",
    "Interactions": "plot",
}


# ---------------------------------------------------------------------------
# Registered actions
# ---------------------------------------------------------------------------

def _build_actions() -> dict[str, Action]:
    actions: dict[str, Action] = {
        "load_experiment": Action(
            key="load_experiment",
            title="Load experiment",
            description=(
                "Load an Experiment from a project directory "
                "(data/*.xlsx + tracking_config.yaml)."
            ),
            category=Category.LOAD,
            icon_name="load",
            params=(
                ParamSpec(
                    "path", "path", "Project dir",
                    default=".", help="Defaults to the script's project dir.",
                ),
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
                ParamSpec(
                    "min_high_quality", "float", "min_high_quality",
                    default=0.8, min=0.0, max=1.0,
                ),
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
            title="Run Analysis",
            description=(
                "Run QC, write summary/facet CSVs, save plots, and run stats. "
                "Mirrors the Hub's Run Analysis button."
            ),
            category=Category.ANALYZE,
            icon_name="basic",
            params=(
                ParamSpec("cutoffs", "list", "cutoffs (minutes, comma-sep)", default=""),
                ParamSpec("qc_cutoff", "float", "qc_cutoff", default=0.9, min=0.0, max=1.0),
            ),
            validate_fn=_validate_cutoffs,
            execute_fn=_exec_run_analysis,
        ),
        "summarize": Action(
            key="summarize",
            title="Summarize",
            description=(
                "Write {exp}_Summary.csv (and, when faceted, {exp}_Summary_Facet.csv). "
                "Mirrors the Hub's Summarize button."
            ),
            category=Category.ANALYZE,
            icon_name="csv",
            params=(
                ParamSpec(
                    "facet", "bool", "Faceted (use config cutoffs)", default=True,
                    help="When checked, also writes the per-facet summary using "
                         "the project's facet_cutoffs.",
                ),
            ),
            execute_fn=_exec_summarize,
        ),
        "run_pairwise_comparisons": Action(
            key="run_pairwise_comparisons",
            title="Run pairwise comparisons",
            description=(
                "Run treatment-vs-treatment comparisons for every metric appropriate "
                "to the tracking type. Mirrors the Hub's Run pairwise comparisons button."
            ),
            category=Category.ANALYZE,
            icon_name="compare",
            params=(
                ParamSpec(
                    "facet", "bool", "Faceted (use config cutoffs)", default=True,
                    help="When checked, runs Tukey HSD per facet using the project's "
                         "facet_cutoffs; otherwise runs over the full recording.",
                ),
            ),
            execute_fn=_exec_run_pairwise_comparisons,
        ),
        "create_report": Action(
            key="create_report",
            title="Create PDF Report",
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

    # Per-tracking-type plot actions. One palette tile per Hub Plots-card button,
    # filtered by the current experiment's tracking type.
    for base_method, label, applies in _PLOT_BUTTON_DEFS:
        actions[base_method] = Action(
            key=base_method,
            title=label,
            description=(
                f"Render the {label} plot. When ``Faceted`` is checked, calls the "
                f"_facet variant using the project's facet_cutoffs; otherwise plots "
                f"over the full recording."
            ),
            category=Category.PLOTS,
            icon_name=_PLOT_ICON_BY_LABEL.get(label, "plot"),
            params=(
                ParamSpec(
                    "facet", "bool", "Faceted (use config cutoffs)", default=True,
                ),
            ),
            execute_fn=_make_plot_executor(base_method),
            applicable_types=applies,
        )

    return actions


ACTIONS: dict[str, Action] = _build_actions()


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
