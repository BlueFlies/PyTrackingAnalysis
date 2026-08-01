"""Rules that every ``range_minutes`` argument in the package obeys."""

from __future__ import annotations

import pandas as pd
import pytest

from pytrackinganalysis import windowing


def frame(minutes):
    return pd.DataFrame({"Minutes": list(minutes), "Value": range(len(minutes))})


def test_full_range_sentinel_is_the_pair_not_the_sum():
    assert windowing.is_full_range((0, 0))
    # (-5, 5) also sums to zero but is a genuine window.
    assert not windowing.is_full_range((-5, 5))


def test_slice_is_half_open():
    data = frame([0, 1, 2, 3])
    got = windowing.slice_by_minutes(data, (1, 3))
    assert list(got["Minutes"]) == [1, 2], "the end boundary belongs to the next window"


def test_slice_returns_an_independent_copy():
    data = frame([0, 1, 2])
    got = windowing.slice_by_minutes(data, (0, 2))
    got.loc[0, "Value"] = 999
    assert data.loc[0, "Value"] == 0


def test_full_range_returns_everything():
    data = frame([0, 1, 2])
    assert len(windowing.slice_by_minutes(data, (0, 0))) == 3


def test_slice_rejects_a_reversed_window():
    with pytest.raises(ValueError):
        windowing.slice_by_minutes(frame([0, 1]), (5, 1))


def test_slice_rejects_a_malformed_range():
    with pytest.raises(ValueError):
        windowing.slice_by_minutes(frame([0, 1]), (1, 2, 3))


def test_facet_windows_tile_the_recording_exactly_once():
    windows = windowing.facet_windows([10, 70])
    assert windows == [(0, 10), (10, 70), (70, float("inf"))]
    # Each window's end is the next window's start: no gaps, no overlaps.
    for earlier, later in zip(windows, windows[1:]):
        assert earlier[1] == later[0]


def test_facet_windows_keep_whole_numbers_as_ints():
    """FacetRange is written to CSV and shown in plot titles as-is."""
    assert str(windowing.facet_windows([10, 70])[0]) == "(0, 10)"
    assert windowing.facet_windows([2.5])[0] == (0, 2.5)


def test_facet_windows_accept_lists_tuples_and_scalars():
    assert windowing.facet_windows([10]) == windowing.facet_windows((10,))
    assert windowing.facet_windows(10) == windowing.facet_windows([10])


def test_facet_windows_sort_and_deduplicate():
    assert windowing.facet_windows([70, 10, 10]) == windowing.facet_windows([10, 70])


def test_normalize_cutoffs_rejects_non_numeric():
    with pytest.raises(ValueError):
        windowing.normalize_cutoffs("10,70")
    with pytest.raises(ValueError):
        windowing.normalize_cutoffs([1, "x"])


def test_safe_rate_reports_a_zero_duration_window_as_missing():
    assert windowing.safe_rate(10, 0) is pd.NA
    assert windowing.safe_rate(10, pd.NA) is pd.NA
    assert windowing.safe_rate(10, 2) == 5


def test_recompute_window_deltas_zeroes_the_leading_delta():
    data = pd.DataFrame({
        "Minutes": [1.0, 2.0],
        "Xpos_mm": [10.0, 20.0],
        "Ypos_mm": [0.0, 0.0],
        "Dist_mm": [10.0, 10.0],   # as computed over the full recording
        "DeltaSec": [60.0, 60.0],
    })
    got = windowing.recompute_window_deltas(data)
    assert list(got["Dist_mm"]) == [0.0, 10.0]
    assert list(got["DeltaSec"]) == [0.0, 60.0]
