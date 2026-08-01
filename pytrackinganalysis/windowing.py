"""Shared time-window slicing for trackers and counters.

Every class that exposes a ``range_minutes`` argument routes through
:func:`slice_by_minutes` so that one rule applies everywhere:

**Windows are half-open — ``[start, end)``.**

That rule is what makes faceted analysis a true partition of the recording.
With inclusive bounds a row landing exactly on a cutoff is counted in the
phase before it *and* the phase after it, which inflates both phases.  The
final facet always ends at ``inf``, so nothing is lost at the tail.

``(0, 0)`` remains the sentinel for "the whole recording".

Per-row deltas (``Dist_mm``, ``DeltaSec``) are *arrival* quantities: the value on
row *i* describes the step from row *i-1* to row *i*.  Two rules follow, and
:func:`slice_with_window_deltas` implements both:

* Each step is attributed to the window containing the row it arrives at, so a
  step that spans a cutoff counts once, in the later phase.
* The first row of a window measures its step against the last row *before* the
  window, not against itself.

Together with half-open windows this makes faceted distances add up: the phase
totals sum to the whole-recording total exactly, with nothing double-counted and
nothing dropped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FULL_RANGE = (0, 0)


def is_full_range(range_minutes) -> bool:
    """True when *range_minutes* is the "whole recording" sentinel ``(0, 0)``.

    Compares the pair directly rather than summing it, so a genuine window
    such as ``(-5, 5)`` is not mistaken for the sentinel.
    """
    return tuple(range_minutes) == FULL_RANGE


def slice_by_minutes(data, range_minutes, minutes_column: str = "Minutes"):
    """Return the rows of *data* whose *minutes_column* falls in ``[start, end)``.

    Always returns a copy with a fresh ``RangeIndex`` so callers can assign to
    it without mutating the source frame or tripping pandas' chained-assignment
    warnings.  ``(0, 0)`` returns a copy of the whole frame.
    """
    if len(range_minutes) != 2:
        raise ValueError(
            f"Invalid range_minutes: {range_minutes}. Must be a (start, end) pair of minutes."
        )
    if is_full_range(range_minutes):
        return data.copy().reset_index(drop=True)

    start, end = range_minutes
    if start > end:
        raise ValueError(
            f"Invalid range_minutes: {range_minutes}. Start minute must not exceed end minute."
        )
    minutes = data[minutes_column]
    mask = (minutes >= start) & (minutes < end)
    return data.loc[mask].copy().reset_index(drop=True)


def recompute_window_deltas(
    data,
    x_column: str = "Xpos_mm",
    y_column: str = "Ypos_mm",
    distance_column: str = "Dist_mm",
    x_distance_column: str = "XDist_mm",
    minutes_column: str = "Minutes",
    delta_seconds_column: str = "DeltaSec",
):
    """Recompute per-row distance and elapsed-time deltas relative to *data* itself.

    Mutates and returns *data* (expected to already be a private copy from
    :func:`slice_by_minutes`).  Columns that are not present are left alone, so
    this is safe to call on counter frames that carry no trajectory.
    """
    if len(data) == 0:
        return data

    if distance_column in data.columns and {x_column, y_column} <= set(data.columns):
        dx = data[x_column].diff()
        dy = data[y_column].diff()
        data[distance_column] = np.hypot(dx, dy)
        data.loc[data.index[0], distance_column] = 0.0
        if x_distance_column in data.columns:
            data[x_distance_column] = dx.abs()
            data.loc[data.index[0], x_distance_column] = 0.0

    if delta_seconds_column in data.columns and minutes_column in data.columns:
        data[delta_seconds_column] = data[minutes_column].diff() * 60
        data.loc[data.index[0], delta_seconds_column] = 0.0

    return data


def slice_with_window_deltas(data, range_minutes, minutes_column: str = "Minutes", **delta_columns):
    """Slice to ``[start, end)`` and recompute deltas across the window's opening edge.

    The row immediately before the window is pulled in only to measure the first
    in-window step, then dropped.  Without it that step would either be zeroed
    (losing movement that crosses a cutoff) or left carrying the raw whole-recording
    delta (double-counting it in both adjacent phases).
    """
    if is_full_range(range_minutes):
        return recompute_window_deltas(
            slice_by_minutes(data, range_minutes, minutes_column), **delta_columns
        )

    subset = slice_by_minutes(data, range_minutes, minutes_column)
    if len(subset) == 0:
        return subset

    minutes = data[minutes_column]
    start, end = range_minutes
    positions = np.flatnonzero(((minutes >= start) & (minutes < end)).to_numpy())
    first, last = positions[0], positions[-1]

    lead = 1 if first > 0 else 0
    block = data.iloc[first - lead:last + 1].copy()
    block = recompute_window_deltas(block, **delta_columns)
    if lead:
        block = block.iloc[lead:]
    return block.reset_index(drop=True)


def observed_minutes(data, minutes_column: str = "Minutes"):
    """Elapsed minutes spanned by *data*, or ``pd.NA`` when it is empty."""
    if len(data) == 0:
        return pd.NA
    return data[minutes_column].iat[-1] - data[minutes_column].iat[0]


def safe_rate(total, minutes):
    """``total / minutes`` guarded against empty or zero-duration windows.

    Returns ``pd.NA`` rather than raising or producing ``inf`` so a degenerate
    window is visibly missing in the output instead of silently poisoning
    downstream means.
    """
    if total is pd.NA or minutes is pd.NA:
        return pd.NA
    try:
        if minutes == 0 or pd.isna(minutes) or pd.isna(total):
            return pd.NA
    except (TypeError, ValueError):
        return pd.NA
    return total / minutes


def normalize_cutoffs(cutoffs):
    """Coerce a facet-cutoff argument into a list of floats.

    Accepts a single number or any numeric sequence (list, tuple, ndarray,
    …).  The guide and ``tracking_config.yaml`` both use lists, so rejecting
    them — as the old tuple-or-int check did — broke documented usage.
    """
    if cutoffs is None:
        raise ValueError("cutoffs must be a number or a sequence of numbers, not None.")
    if isinstance(cutoffs, (int, float)) and not isinstance(cutoffs, bool):
        values = [cutoffs]
    elif isinstance(cutoffs, (str, bytes)):
        raise ValueError(f"Invalid cutoffs: {cutoffs!r}. Must be a number or a sequence of numbers.")
    else:
        try:
            values = list(cutoffs)
        except TypeError as err:
            raise ValueError(
                f"Invalid cutoffs: {cutoffs!r}. Must be a number or a sequence of numbers."
            ) from err
    if not values:
        raise ValueError("cutoffs must contain at least one value.")
    try:
        return [float(v) for v in values]
    except (TypeError, ValueError) as err:
        raise ValueError(f"Invalid cutoffs: {cutoffs!r}. Every value must be numeric.") from err


def _tidy_bound(value):
    """Render a whole-number boundary as an int.

    The ``FacetRange`` column and the faceted plot titles show these values, so
    ``10`` must not become ``10.0`` just because the input passed through a
    float normalisation step.
    """
    if value == float("inf") or value != int(value):
        return value
    return int(value)


def facet_windows(cutoffs):
    """Return the ``[(start, end), …]`` windows implied by *cutoffs*.

    Boundaries are sorted and de-duplicated, the first window opens at 0 and
    the last one runs to infinity.  Combined with the half-open rule in
    :func:`slice_by_minutes` the windows tile the recording exactly once.
    """
    values = sorted(set(normalize_cutoffs(cutoffs)))
    bounds = [0.0] + [v for v in values if v > 0.0] + [float("inf")]
    tidied = [_tidy_bound(b) for b in bounds]
    return [(tidied[i], tidied[i + 1]) for i in range(len(tidied) - 1)]
