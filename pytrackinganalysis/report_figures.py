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

    # Named phase labels come from the Experiment Type when present (e.g.
    # Valence: Acclimation/Experiment/Cooldown); else minute ranges.
    exp_type = getattr(experiment, "experiment_type", None)
    if exp_type is not None:
        phase_labels = exp_type.phase_labels_for(phases)
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
        fig, ax = plt.subplots(figsize=(9, max(2.4, 0.22 * n + 1.0)))
        _style_ax(ax)
        ax.grid(True, axis="x", color=_GRID, linewidth=0.7)
        ax.barh(range(n), hq_sorted.fillna(0).values, color=colors,
                edgecolor="white", linewidth=0.4)
        ax.axvline(0.90, color="#94a3b8", linewidth=0.9, linestyle="--")
        ax.set_yticks(range(n))
        ax.set_yticklabels(labels.values, fontsize=6.5)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Fraction high-quality frames", fontsize=9, color=_INK)
        ax.set_title("Per-tracker data quality", fontsize=10, color=_INK)
        fig.tight_layout()
        blocks.append(_fig_to_block(
            fig, title="Data quality",
            caption="High-quality frame fraction per tracker. Dashed line = "
                    "0.90 threshold; green ≥ 0.90, amber ≥ 0.80, red below."))
    except Exception:  # noqa: BLE001
        plt.close("all")
    return blocks
