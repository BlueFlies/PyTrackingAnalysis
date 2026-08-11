"""A short, human-readable summary of a ``tracking_config.yaml``.

Given the parsed config dict, :func:`summarize` returns ordered ``(label,
value)`` rows for display when a project is opened — the most important being the
Experiment Type. Pure and dependency-light so it is easy to unit-test; the Hub
renders the rows.
"""

from __future__ import annotations

from collections import Counter


def summarize(config) -> list[tuple[str, str]]:
    """Ordered (label, value) rows summarising *config* (a parsed yaml dict)."""
    from . import experiment_types, windowing

    if not isinstance(config, dict):
        return [("Config", "unreadable")]

    g = config.get("global") or {}
    rows: list[tuple[str, str]] = []

    exp_type = experiment_types.get_experiment_type(g.get("experiment_type"))
    rows.append(("Experiment type", exp_type.display_name))

    try:
        tracking_type = exp_type.resolve_tracking_type(g).name
    except Exception:  # noqa: BLE001 — show whatever the yaml has if unresolved
        tracking_type = str(g.get("tracking_type", "?"))
    rows.append(("Tracking type", tracking_type))
    rows.append(("Rig", str(g.get("tracking_rig") or "—")))

    cutoffs = exp_type.resolve_facet_cutoffs(g)
    if cutoffs:
        labels = exp_type.phase_labels_for(windowing.facet_windows(cutoffs), g)
        cut_str = ", ".join(str(c) for c in cutoffs)
        rows.append(("Phases", f"{cut_str}  ({' / '.join(labels)})"))
    else:
        rows.append(("Phases", "none (flat)"))

    regions = config.get("tracking_regions") or {}
    rows.append(("Tracking regions", str(len(regions))))

    # Treatments: count regions per assigned experimental_factors string.
    counts: Counter = Counter()
    for region in regions.values():
        factors = (str(region.get("experimental_factors", "")).strip()
                   if isinstance(region, dict) else "")
        counts[factors] += 1
    assigned = {k: v for k, v in counts.items() if k}
    if assigned:
        parts = [f"{name} ×{n}" for name, n in sorted(assigned.items())]
        blanks = counts.get("", 0)
        if blanks:
            parts.append(f"unassigned ×{blanks}")
        rows.append(("Treatments", ", ".join(parts)))
    elif regions:
        rows.append(("Treatments", "unassigned"))

    counting = config.get("counting_regions") or {}
    if counting:
        rows.append(("Counting regions", ", ".join(str(k) for k in counting)))

    factors = g.get("experimental_design_factors") or {}
    if factors:
        rows.append(("Design factors", ", ".join(str(k) for k in factors)))

    return rows
