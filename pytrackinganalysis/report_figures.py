"""Report-native figures: consolidated multi-panel plots built for the page.

These replace the old approach of re-embedding the interactive ``save_plots``
PNGs (which looked "pasted in" — duplicated titles, mismatched aspect, soft at
print scale). Each function here draws a clean multi-panel matplotlib figure
straight from the arena summary and hands it back as a backend-agnostic
:class:`pytrackinganalysis.report.model.Figure` (image bytes + intrinsic size),
so the reporting engine never touches matplotlib and the analysis core never
touches the reporting engine.

Everything is defensive: a panel that cannot be built (missing column, empty
group) is skipped, and a figure that raises is dropped rather than aborting the
report.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg", force=False)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import Parameters
from .report import model as m

# One place for the report's plot look, so every figure reads as a set.
_TREAT_PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"]
_MEAN_COLOR = "#dc2626"
_GRID = "#e2e8f0"
_INK = "#0f172a"
_MUTED = "#64748b"
_DPI = 200


def _style_ax(ax):
    ax.set_facecolor("white")
    ax.grid(True, axis="y", color=_GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#cbd5e1")
    ax.tick_params(colors=_MUTED, labelsize=8)


def _fig_to_block(fig, title=None, caption=None) -> m.Figure:
    """Rasterize *fig* to PNG bytes and wrap it as a model Figure block."""
    from PIL import Image

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    data = buf.getvalue()
    w, h = Image.open(io.BytesIO(data)).size
    return m.Figure(data=data, fmt="png", width_in=w / _DPI, height_in=h / _DPI,
                    title=title, caption=caption)


def _treatments(summary: pd.DataFrame) -> list[str]:
    """Ordered, non-blank treatment levels present in the summary."""
    if "Treatment" not in summary.columns:
        return []
    seen: list[str] = []
    for value in summary["Treatment"].astype(str):
        v = value.strip()
        if v and v not in seen:
            seen.append(v)
    return seen


def _numeric(summary: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(summary.get(col), errors="coerce")


def _strip_panel(ax, summary, metric, treatments, ylabel, ylim=None,
                 ref_line=None):
    """One metric-by-treatment panel: jittered points plus a mean bar per group."""
    _style_ax(ax)
    rng = np.random.default_rng(0)
    for i, treat in enumerate(treatments):
        mask = summary["Treatment"].astype(str).str.strip() == treat
        vals = _numeric(summary[mask], metric).dropna().values
        color = _TREAT_PALETTE[i % len(_TREAT_PALETTE)]
        if len(vals):
            x = i + (rng.random(len(vals)) - 0.5) * 0.28
            ax.scatter(x, vals, s=16, color=color, alpha=0.65,
                       edgecolor="white", linewidth=0.4, zorder=3)
            mean = float(np.mean(vals))
            ax.hlines(mean, i - 0.28, i + 0.28, color=_MEAN_COLOR,
                      linewidth=2.2, zorder=4)
            # Label just above the right end of the mean bar so it never sits on
            # top of the jittered points or the line itself.
            ax.annotate(f"{mean:.3g}", xy=(i + 0.3, mean), fontsize=7,
                        color=_MEAN_COLOR, va="bottom", ha="left", zorder=5)
    if ref_line is not None:
        ax.axhline(ref_line, color="#94a3b8", linewidth=0.8, linestyle="--")
    ax.set_xticks(range(len(treatments)))
    ax.set_xticklabels([f"{t}\n(n={int(_numeric(summary[summary['Treatment'].astype(str).str.strip()==t], metric).notna().sum())})"
                        for t in treatments])
    ax.set_ylabel(ylabel, fontsize=9, color=_INK)
    if ylim is not None:
        ax.set_ylim(*ylim)


def _activity_panel(ax, summary, treatments):
    """Stacked mean activity composition per treatment."""
    _style_ax(ax)
    parts = [("PercWalking", "#2563eb"), ("PercMicro", "#38bdf8"),
             ("PercResting", "#94a3b8"), ("PercSleeping", "#1e293b")]
    present = [(c, col) for c, col in parts if c in summary.columns]
    if not present:
        return False
    bottoms = np.zeros(len(treatments))
    for col, color in present:
        heights = []
        for treat in treatments:
            mask = summary["Treatment"].astype(str).str.strip() == treat
            heights.append(float(_numeric(summary[mask], col).mean()))
        heights = np.nan_to_num(np.array(heights))
        ax.bar(range(len(treatments)), heights, bottom=bottoms, width=0.6,
               color=color, label=col.replace("Perc", ""), edgecolor="white",
               linewidth=0.5)
        bottoms += heights
    ax.set_xticks(range(len(treatments)))
    ax.set_xticklabels(treatments)
    ax.set_ylabel("Mean activity fraction", fontsize=9, color=_INK)
    ax.set_ylim(0, 1)
    # Legend below the panel so it never collides with the panel title above.
    ax.legend(fontsize=7, frameon=False, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, -0.08), columnspacing=1.0, handlelength=1.2)
    return True


def _phase_label(window) -> str:
    """Human phase label for a ``(start, end)`` facet window, e.g. '10–70', '70+'."""
    start, end = window

    def fmt(v):
        return f"{int(v)}" if float(v) == int(v) else f"{v:g}"

    if end == float("inf"):
        return f"{fmt(start)}+"
    return f"{fmt(start)}–{fmt(end)}"


def _phase_panel(ax, fsummary, metric, treatments, phases, ylabel, ylim=None,
                 ref_line=None, phase_labels=None):
    """A metric-by-phase panel: for each phase, one dodged, jittered cluster of
    points per treatment with a mean bar. The x-axis is the facet phase.

    ``phase_labels`` (aligned to ``phases``) overrides the default minute-range
    tick labels — an Experiment Type supplies named phases (e.g. Acclimation).
    """
    _style_ax(ax)
    rng = np.random.default_rng(0)
    n_t = max(1, len(treatments))
    slot = 0.8 / n_t
    for ti, treat in enumerate(treatments):
        color = _TREAT_PALETTE[ti % len(_TREAT_PALETTE)]
        offset = (ti - (n_t - 1) / 2) * slot
        drew_label = False
        for pi, phase in enumerate(phases):
            mask = ((fsummary["Treatment"].astype(str).str.strip() == treat)
                    & (fsummary["FacetRange"] == phase))
            vals = _numeric(fsummary[mask], metric).dropna().values
            x0 = pi + offset
            if len(vals):
                x = x0 + (rng.random(len(vals)) - 0.5) * slot * 0.7
                ax.scatter(x, vals, s=13, color=color, alpha=0.6,
                           edgecolor="white", linewidth=0.3, zorder=3,
                           label=treat if not drew_label else None)
                drew_label = True
                mean = float(np.mean(vals))
                ax.hlines(mean, x0 - slot * 0.42, x0 + slot * 0.42,
                          color=_MEAN_COLOR, linewidth=1.8, zorder=4)
    if ref_line is not None:
        ax.axhline(ref_line, color="#94a3b8", linewidth=0.8, linestyle="--")
    labels = phase_labels if phase_labels is not None else [_phase_label(p) for p in phases]
    ax.set_xticks(range(len(phases)))
    ax.set_xticklabels(labels)
    ax.set_xlabel("Phase (min)", fontsize=8, color=_MUTED)
    ax.set_ylabel(ylabel, fontsize=9, color=_INK)
    if ylim is not None:
        ax.set_ylim(*ylim)
    ax.legend(fontsize=7, frameon=False, ncol=n_t, loc="upper center",
              bbox_to_anchor=(0.5, -0.12), columnspacing=1.0, handlelength=1.0)


def build_analysis_figures(experiment) -> list[m.Figure]:
    """Consolidated analysis figures appropriate for the experiment's type."""
    tt = experiment.parameters.get_tracking_type()
    T = Parameters.TrackingType
    blocks: list[m.Figure] = []

    remove_partners = tt in (T.PAIRWISEINTERACTIONTRACKER,
                             T.PAIRWISEINTERACTIONCOUNTER)
    try:
        summary = experiment.arena.summarize(remove_partners=remove_partners)
    except Exception:  # noqa: BLE001
        return blocks
    treatments = _treatments(summary)
    if not treatments:
        return blocks

    # --- Choice / preference (two-choice tracker & counter) ----------------
    if {"FinalPI", "FinalPercentage"} & set(summary.columns):
        try:
            fig, axes = plt.subplots(1, 2, figsize=(9, 4.2))
            _strip_panel(axes[0], summary, "FinalPI", treatments,
                         "Final PI", ylim=(-1.05, 1.05), ref_line=0.0)
            axes[0].set_title("Preference index", fontsize=10, color=_INK)
            _strip_panel(axes[1], summary, "FinalPercentage", treatments,
                         "Final percentage", ylim=(-0.02, 1.02), ref_line=0.5)
            axes[1].set_title("Percentage in region 1", fontsize=10, color=_INK)
            fig.tight_layout()
            blocks.append(_fig_to_block(
                fig, title="Choice",
                caption="Per-animal final preference index and percentage by "
                        "treatment. Red bar = group mean; dashed line = "
                        "indifference."))
        except Exception:  # noqa: BLE001
            plt.close("all")

    # --- Locomotion (any tracker-class type carrying distance) -------------
    if "TotalDistancePerMin" in summary.columns:
        try:
            has_activity = any(c in summary.columns for c in
                               ("PercWalking", "PercResting"))
            ncols = 2 if has_activity else 1
            fig, axes = plt.subplots(1, ncols, figsize=(4.6 * ncols, 4.2),
                                     squeeze=False)
            _strip_panel(axes[0][0], summary, "TotalDistancePerMin", treatments,
                         "Distance (mm/min)")
            axes[0][0].set_title("Locomotion", fontsize=10, color=_INK)
            if has_activity:
                ok = _activity_panel(axes[0][1], summary, treatments)
                axes[0][1].set_title("Activity budget", fontsize=10, color=_INK)
                if not ok:
                    axes[0][1].set_visible(False)
            fig.tight_layout()
            blocks.append(_fig_to_block(
                fig, title="Locomotion & activity",
                caption="Distance travelled per minute (red bar = group mean) "
                        "and mean activity composition by treatment."))
        except Exception:  # noqa: BLE001
            plt.close("all")

    # --- Adjusted X position (x-choice) ------------------------------------
    if "AvgAdjX_mm" in summary.columns:
        try:
            fig, ax = plt.subplots(figsize=(5.2, 4.2))
            _strip_panel(ax, summary, "AvgAdjX_mm", treatments,
                         "Adjusted X (mm)", ref_line=0.0)
            ax.set_title("Position preference", fontsize=10, color=_INK)
            fig.tight_layout()
            blocks.append(_fig_to_block(
                fig, title="Adjusted X position",
                caption="Mean polarity-adjusted X position by treatment."))
        except Exception:  # noqa: BLE001
            plt.close("all")

    # --- Interactions (pairwise) -------------------------------------------
    interacting_cols = [c for c in summary.columns
                        if c.startswith("PercentInteracting_")]
    if interacting_cols:
        try:
            ncols = len(interacting_cols)
            fig, axes = plt.subplots(1, ncols, figsize=(4.6 * ncols, 4.2),
                                     squeeze=False)
            for j, col in enumerate(interacting_cols):
                dist = col.rsplit("_", 1)[-1]
                _strip_panel(axes[0][j], summary, col, treatments,
                             "Fraction of frames", ylim=(-0.02, 1.02))
                axes[0][j].set_title(f"Interacting < {dist} mm", fontsize=10,
                                     color=_INK)
            fig.tight_layout()
            blocks.append(_fig_to_block(
                fig, title="Social interactions",
                caption="Fraction of valid frames spent within each interaction "
                        "distance, by treatment."))
        except Exception:  # noqa: BLE001
            plt.close("all")

    return blocks


def build_faceted_figures(experiment) -> list[m.Figure]:
    """Per-phase (faceted) figures, restoring the old report's faceted section.

    Returns an empty list when no ``facet_cutoffs`` are configured. Each metric
    is shown across the configured phases, grouped by treatment, mirroring the
    metrics that ``_TRACKING_TYPE_METRICS`` compares statistically.
    """
    blocks: list[m.Figure] = []
    cutoffs = getattr(experiment, "facet_cutoffs", None)
    if cutoffs is None:
        return blocks

    tt = experiment.parameters.get_tracking_type()
    T = Parameters.TrackingType
    remove_partners = tt in (T.PAIRWISEINTERACTIONTRACKER,
                             T.PAIRWISEINTERACTIONCOUNTER)
    try:
        fsummary = experiment.arena.summarize_facet(
            cutoffs, remove_partners=remove_partners)
    except Exception:  # noqa: BLE001
        return blocks
    if fsummary is None or len(fsummary) == 0 or "FacetRange" not in fsummary.columns:
        return blocks

    treatments = _treatments(fsummary)
    if not treatments:
        return blocks
    # Ordered, de-duplicated phases as they appear.
    phases: list = []
    for w in fsummary["FacetRange"]:
        if w not in phases:
            phases.append(w)

    # Named phase labels: the config's facet_labels first, then the Experiment
    # Type's defaults (e.g. Valence: Acclimation/Experiment/Cooldown), then
    # minute ranges.
    exp_type = getattr(experiment, "experiment_type", None)
    if exp_type is not None:
        global_cfg = (getattr(experiment, "config", None) or {}).get("global") or {}
        phase_labels = exp_type.phase_labels_for(phases, global_cfg)
    else:
        phase_labels = [_phase_label(w) for w in phases]

    def _panels(specs, title, caption):
        """Build a one-row figure of phase panels from (metric, ylabel, ...) specs."""
        specs = [s for s in specs if s[0] in fsummary.columns]
        if not specs:
            return
        try:
            fig, axes = plt.subplots(1, len(specs), figsize=(4.8 * len(specs), 4.4),
                                     squeeze=False)
            for ax, (metric, ylabel, ylim, ref) in zip(axes[0], specs):
                _phase_panel(ax, fsummary, metric, treatments, phases, ylabel,
                             ylim=ylim, ref_line=ref, phase_labels=phase_labels)
                ax.set_title(ylabel, fontsize=10, color=_INK)
            # No matplotlib suptitle: the reportlab block title already labels
            # the figure, so a suptitle would duplicate it and waste space.
            fig.tight_layout()
            blocks.append(_fig_to_block(fig, title=title, caption=caption))
        except Exception:  # noqa: BLE001
            plt.close("all")

    _panels(
        [("FinalPI", "Final PI", (-1.05, 1.05), 0.0),
         ("FinalPercentage", "Final percentage", (-0.02, 1.02), 0.5)],
        "Choice by phase",
        "Final preference index and percentage across phases, by treatment. "
        "Red bar = group mean.")
    _panels(
        [("Transitions", "Transitions", None, None)],
        "Transitions by phase",
        "Region transitions across phases, by treatment.")
    _panels(
        [("TotalDistancePerMin", "Distance (mm/min)", None, None)],
        "Locomotion by phase",
        "Distance travelled per minute across phases, by treatment.")
    _panels(
        [("AvgAdjX_mm", "Adjusted X (mm)", None, 0.0)],
        "Position by phase",
        "Mean polarity-adjusted X position across phases, by treatment.")
    interacting = [(c, f"< {c.rsplit('_', 1)[-1]} mm", (-0.02, 1.02), None)
                   for c in fsummary.columns if c.startswith("PercentInteracting_")]
    if interacting:
        _panels(interacting, "Interactions by phase",
                "Fraction of valid frames interacting, across phases, by treatment.")

    return blocks


def build_qc_figures(experiment) -> list[m.Figure]:
    """A per-tracker data-quality figure, when the type supports it."""
    blocks: list[m.Figure] = []
    arena = experiment.arena
    try:
        if not arena.supports_data_quality():
            return blocks
        dq = arena.get_data_quality()
    except Exception:  # noqa: BLE001
        return blocks
    if dq is None or len(dq) == 0 or "HighQuality" not in dq.columns:
        return blocks

    try:
        hq = pd.to_numeric(dq["HighQuality"], errors="coerce")
        order = hq.sort_values(na_position="first").index
        hq_sorted = hq.loc[order]
        label_col = next((c for c in ("Tracker", "Name") if c in dq.columns), None)
        labels = (dq.loc[order, label_col] if label_col is not None
                  else pd.Series(order, index=order)).astype(str)
        colors = ["#16a34a" if (v == v and v >= 0.90)
                  else "#d97706" if (v == v and v >= 0.80)
                  else "#dc2626" for v in hq_sorted]
        n = len(hq_sorted)
        # Taller rows and larger type than the analysis figures: this chart is
        # read tracker-by-tracker, so the names and scale must stay legible.
        fig, ax = plt.subplots(figsize=(9, max(3.2, 0.32 * n + 1.2)))
        _style_ax(ax)
        ax.grid(True, axis="x", color=_GRID, linewidth=0.7)
        ax.barh(range(n), hq_sorted.fillna(0).values, color=colors,
                edgecolor="white", linewidth=0.4)
        ax.axvline(0.90, color="#94a3b8", linewidth=0.9, linestyle="--")
        ax.set_yticks(range(n))
        ax.set_yticklabels(labels.values, fontsize=10)
        ax.tick_params(axis="x", labelsize=10)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Fraction high-quality frames", fontsize=13, color=_INK)
        ax.set_title("Per-tracker data quality", fontsize=14, color=_INK)
        fig.tight_layout()
        blocks.append(_fig_to_block(
            fig, title="Data quality",
            caption="High-quality frame fraction per tracker. Dashed line = "
                    "0.90 threshold; green ≥ 0.90, amber ≥ 0.80, red below."))
    except Exception:  # noqa: BLE001
        plt.close("all")
    return blocks


# --------------------------------------------------------------------------
# Valence-specific sections (served through ExperimentType.report_sections)
# --------------------------------------------------------------------------

# Sliding-window PI, matching the old notebooks' plot_trackers_pis defaults.
_PI_WINDOW_MIN = 10
_PI_STEP_MIN = 5


def _global_cfg(experiment) -> dict:
    return (getattr(experiment, "config", None) or {}).get("global") or {}


def _facet_windows_and_labels(experiment):
    """The experiment's facet windows with display labels, or ``([], [])``."""
    cutoffs = getattr(experiment, "facet_cutoffs", None)
    if not cutoffs:
        return [], []
    from . import windowing
    windows = list(windowing.facet_windows(cutoffs))
    exp_type = getattr(experiment, "experiment_type", None)
    if exp_type is not None:
        labels = exp_type.phase_labels_for(windows, _global_cfg(experiment))
    else:
        labels = [_phase_label(w) for w in windows]
    return windows, labels


def build_valence_sections(experiment) -> list:
    """Valence-first report blocks, in reading order: the headline
    Experiment-phase result (figure, sentence, pairwise-stats table), the
    treatment-level PI-over-time trace, and per-animal phase persistence.

    Defensive like the generic builders: each section is skipped when its data
    cannot be built, so a thin dataset degrades to a shorter report rather than
    no report.
    """
    blocks: list = []
    blocks += _valence_headline(experiment)
    blocks += _valence_pi_over_time(experiment)
    blocks += _valence_persistence(experiment)
    return blocks


def _primary_phase(windows, labels):
    """The phase the primary result is read from: the second window of the
    Valence structure (Experiment), else the only window there is."""
    idx = 1 if len(windows) >= 2 else 0
    return windows[idx], labels[idx]


def _valence_headline(experiment) -> list:
    """Experiment-phase PI: the report's first, headline answer."""
    windows, labels = _facet_windows_and_labels(experiment)
    if windows:
        window, label = _primary_phase(windows, labels)
        where = f"{label} phase ({_phase_label(window)} min)"
    else:
        window, where = None, "whole recording"
    try:
        summary = (experiment.arena.summarize(range_minutes=window)
                   if window is not None else experiment.arena.summarize())
    except Exception:  # noqa: BLE001
        return []
    if summary is None or "FinalPI" not in getattr(summary, "columns", []):
        return []
    treatments = _treatments(summary)
    if not treatments:
        return []

    blocks: list = []
    try:
        fig, ax = plt.subplots(figsize=(5.2, 4.2))
        _strip_panel(ax, summary, "FinalPI", treatments, "Final PI",
                     ylim=(-1.05, 1.05), ref_line=0.0)
        ax.set_title(f"Preference index — {where}", fontsize=10, color=_INK)
        fig.tight_layout()
        blocks.append(_fig_to_block(
            fig, title="Headline result",
            caption=f"Per-animal preference index during the {where} — the "
                    "phase the primary result is read from. Positive PI = "
                    "preference for Light. Red bar = group mean; dashed line "
                    "= indifference."))
    except Exception:  # noqa: BLE001
        plt.close("all")
        return []

    parts = []
    for treat in treatments:
        mask = summary["Treatment"].astype(str).str.strip() == treat
        vals = _numeric(summary[mask], "FinalPI").dropna()
        if len(vals):
            parts.append(f"{treat} {float(vals.mean()):+.2f} (n={len(vals)})")
    if parts:
        blocks.append(m.Paragraph(
            f"Mean preference index during the {where}: {'; '.join(parts)}. "
            "Positive PI indicates preference for Light over NoLight."))

    table = _pairwise_table(summary, "FinalPI", treatments, where)
    if table is not None:
        blocks.append(table)
    return blocks


def _pairwise_table(summary, metric, treatments, where):
    """Pairwise treatment comparisons as a semantic Table — Welch's t-test for
    two groups, Tukey HSD beyond, the same policy as ``Experiment.stats``.
    Returns ``None`` when fewer than two groups have enough data."""
    groups: dict[str, np.ndarray] = {}
    for treat in treatments:
        mask = summary["Treatment"].astype(str).str.strip() == treat
        vals = _numeric(summary[mask], metric).dropna().values
        if len(vals) >= 2:
            groups[treat] = vals
    if len(groups) < 2:
        return None
    rows, levels = [], []
    try:
        if len(groups) == 2:
            from scipy import stats as sstats
            (name_a, vals_a), (name_b, vals_b) = groups.items()
            _stat, p = sstats.ttest_ind(vals_a, vals_b, equal_var=False)
            significant = bool(p < 0.05)
            rows.append([name_a, name_b,
                         f"{float(np.mean(vals_b) - np.mean(vals_a)):+.3f}",
                         f"{float(p):.4g}", "yes" if significant else "no"])
            levels.append(m.Level.OK if significant else None)
            method = "Welch's t-test"
        else:
            import itertools

            from statsmodels.stats.multicomp import pairwise_tukeyhsd
            endog = np.concatenate(list(groups.values()))
            group_labels = np.concatenate(
                [[t] * len(v) for t, v in groups.items()])
            res = pairwise_tukeyhsd(endog=endog, groups=group_labels, alpha=0.05)
            pairs = list(itertools.combinations(res.groupsunique, 2))
            for (ga, gb), diff, p, rej in zip(pairs, res.meandiffs,
                                             res.pvalues, res.reject):
                rows.append([str(ga), str(gb), f"{float(diff):+.3f}",
                             f"{float(p):.4g}", "yes" if rej else "no"])
                levels.append(m.Level.OK if rej else None)
            method = "Tukey HSD"
    except Exception:  # noqa: BLE001
        return None
    return m.Table(
        columns=["Group A", "Group B", "Mean diff (B − A)", "p-value",
                 "Significant"],
        rows=rows, row_levels=levels,
        title=f"{metric} — pairwise comparisons",
        caption=f"{method} on per-animal {metric} during the {where}; "
                f"α = 0.05.")


def _valence_pi_over_time(experiment) -> list:
    """Treatment-mean sliding-window PI across the recording, phases marked."""
    trackers = getattr(getattr(experiment, "arena", None), "trackers", None)
    if not trackers:
        return []
    # treatment -> window end minute -> per-animal PIs in that window.
    series: dict[str, dict[float, list[float]]] = {}
    for tracker in trackers.values():
        try:
            treat = str(tracker.get_treatment() or "").strip()
            td = tracker.get_time_dependent_pi(_PI_WINDOW_MIN, _PI_STEP_MIN)
        except Exception:  # noqa: BLE001
            continue
        if not treat or td is None or len(td) == 0:
            continue
        for end, pi in zip(td["EndMin"], td["PI"]):
            if pi == pi:  # drop NaN (no occupancy data in the window)
                series.setdefault(treat, {}).setdefault(
                    float(end), []).append(float(pi))
    if not series:
        return []

    windows, labels = _facet_windows_and_labels(experiment)
    try:
        fig, ax = plt.subplots(figsize=(9, 4.2))
        _style_ax(ax)
        for i, (treat, per_end) in enumerate(series.items()):
            ends = sorted(per_end)
            means = np.array([np.mean(per_end[e]) for e in ends])
            sems = np.array([
                np.std(per_end[e], ddof=1) / np.sqrt(len(per_end[e]))
                if len(per_end[e]) > 1 else 0.0
                for e in ends])
            color = _TREAT_PALETTE[i % len(_TREAT_PALETTE)]
            n = max(len(v) for v in per_end.values())
            ax.plot(ends, means, color=color, linewidth=1.8,
                    label=f"{treat} (n={n})")
            ax.fill_between(ends, means - sems, means + sems,
                            color=color, alpha=0.15, linewidth=0)
        ax.axhline(0.0, color="#94a3b8", linewidth=0.8, linestyle="--")
        for cutoff in (getattr(experiment, "facet_cutoffs", None) or []):
            ax.axvline(float(cutoff), color="#cbd5e1", linewidth=0.9)
        if windows:
            x_right = ax.get_xlim()[1]
            for win, label in zip(windows, labels):
                lo = float(win[0])
                hi = x_right if win[1] == float("inf") else float(win[1])
                if min(hi, x_right) > lo:
                    ax.text((lo + min(hi, x_right)) / 2, 1.02, label,
                            fontsize=8, color=_MUTED, ha="center",
                            transform=ax.get_xaxis_transform())
        ax.set_ylim(-1.05, 1.05)
        ax.set_xlabel("Minutes", fontsize=9, color=_INK)
        ax.set_ylabel("PI", fontsize=9, color=_INK)
        ax.legend(fontsize=8, frameon=False, loc="lower right")
        fig.tight_layout()
        return [_fig_to_block(
            fig, title="Preference over time",
            caption=f"Sliding-window preference index (window "
                    f"{_PI_WINDOW_MIN} min, step {_PI_STEP_MIN} min), mean ± "
                    "SEM per treatment. Vertical lines mark phase boundaries; "
                    "positive PI = toward Light.")]
    except Exception:  # noqa: BLE001
        plt.close("all")
        return []


def _valence_persistence(experiment) -> list:
    """Per-animal PI across phases: emergence of the light response and its
    persistence, plus the within-animal change from baseline."""
    windows, labels = _facet_windows_and_labels(experiment)
    if len(windows) < 2:
        return []
    try:
        fsummary = experiment.arena.summarize_facet(
            getattr(experiment, "facet_cutoffs", None))
    except Exception:  # noqa: BLE001
        return []
    needed = {"FinalPI", "Treatment", "FacetRange"}
    if fsummary is None or len(fsummary) == 0 \
            or not needed <= set(fsummary.columns):
        return []

    # One column per phase, one row per animal. Every phase's rows come from
    # the same per-tracker summarize, so identity is the Name column when
    # present, else the row's position within its phase.
    per_phase = []
    for win in windows:
        sub = fsummary[fsummary["FacetRange"] == win].reset_index(drop=True)
        if len(sub) == 0:
            return []
        animal = (sub["Name"].astype(str) if "Name" in sub.columns
                  else sub.index.astype(str))
        per_phase.append(pd.DataFrame({
            "animal": animal,
            "Treatment": sub["Treatment"].astype(str).str.strip(),
            "pi": _numeric(sub, "FinalPI"),
        }))
    treatments = [t for t in _treatments(per_phase[0]) if t]
    if not treatments:
        return []
    wide = per_phase[0][["animal", "Treatment"]].copy()
    for j, frame in enumerate(per_phase):
        wide = wide.merge(frame[["animal", "pi"]].rename(columns={"pi": f"p{j}"}),
                          on="animal", how="left")

    _primary_win, primary_label = _primary_phase(windows, labels)
    primary_col = f"p{1 if len(windows) >= 2 else 0}"
    try:
        fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.2))
        # Left: per-animal slope lines with treatment means.
        ax = axes[0]
        _style_ax(ax)
        xs = range(len(windows))
        for i, treat in enumerate(treatments):
            color = _TREAT_PALETTE[i % len(_TREAT_PALETTE)]
            rows = wide[wide["Treatment"] == treat]
            for _, row in rows.iterrows():
                ax.plot(xs, [row[f"p{j}"] for j in xs], color=color,
                        alpha=0.3, linewidth=0.9, zorder=2)
            means = [float(_numeric(rows, f"p{j}").mean()) for j in xs]
            ax.plot(xs, means, color=color, linewidth=2.4, marker="o",
                    markersize=4, zorder=4, label=treat)
        ax.axhline(0.0, color="#94a3b8", linewidth=0.8, linestyle="--")
        ax.set_xticks(list(xs))
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylim(-1.05, 1.05)
        ax.set_ylabel("Final PI", fontsize=9, color=_INK)
        ax.set_title("PI across phases", fontsize=10, color=_INK)
        ax.legend(fontsize=7, frameon=False, ncol=len(treatments),
                  loc="upper center", bbox_to_anchor=(0.5, -0.08))

        # Right: within-animal change from baseline to the primary phase.
        delta = pd.DataFrame({
            "Treatment": wide["Treatment"],
            "DeltaPI": _numeric(wide, primary_col) - _numeric(wide, "p0"),
        })
        _strip_panel(axes[1], delta, "DeltaPI", treatments,
                     f"Δ PI ({primary_label} − {labels[0]})", ref_line=0.0)
        axes[1].set_title("Change from baseline", fontsize=10, color=_INK)
        fig.tight_layout()
        return [_fig_to_block(
            fig, title="Emergence & persistence",
            caption=f"Left: each animal's PI across phases (thin lines) with "
                    f"treatment means (bold). Right: within-animal change from "
                    f"{labels[0]} to {primary_label}; positive = toward "
                    "Light.")]
    except Exception:  # noqa: BLE001
        plt.close("all")
        return []
