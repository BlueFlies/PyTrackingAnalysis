"""Numerical behaviour of Tracker and its subclasses."""

from __future__ import annotations

import pandas as pd
import pytest

from conftest import FakeDesign, make_raw, make_regions
from pytrackinganalysis import Parameters, Tracker, TwoChoiceTracker, XChoiceTracker


# --------------------------------------------------------------------------
# Time base
# --------------------------------------------------------------------------

def test_fps_based_minutes_do_not_lose_the_frame_column(parameters):
    """A movie/fps experiment derives Minutes from Frame.

    Frame becomes the index during __init__; dropping the column made every
    fps-driven experiment fail with KeyError: 'Frame'.
    """
    parameters.fps = 30
    tracker = Tracker.Tracker(
        "T_1", 0, make_regions(), pd.DataFrame(), parameters, FakeDesign(),
        make_raw(minutes=(0, 1, 2)),
    )
    # Frames 0,1,2 at 30 fps → 0, 1/1800, 2/1800 minutes.
    assert tracker.rawdata["Minutes"].iloc[1] == pytest.approx(1 / (30 * 60))


def test_invalid_fps_is_rejected(parameters):
    parameters.fps = -7
    with pytest.raises(ValueError, match="Invalid fps"):
        Tracker.Tracker(
            "T_1", 0, make_regions(), pd.DataFrame(), parameters, FakeDesign(), make_raw(),
        )


def test_single_row_tracker_does_not_divide_by_zero(parameters):
    """One frame gives no sampling interval to build a rolling window from."""
    tracker = Tracker.Tracker(
        "T_1", 0, make_regions(), pd.DataFrame(), parameters, FakeDesign(),
        make_raw(minutes=(0.0,), xs=(0.0,)),
    )
    assert len(tracker.rawdata) == 1


# --------------------------------------------------------------------------
# Windowed distance
# --------------------------------------------------------------------------

def test_full_range_distance_is_the_whole_trajectory(make_tracker):
    tracker = make_tracker(make_raw(minutes=(0, 1, 2), xs=(0, 10, 20)))
    assert tracker.summarize()["TotalDistance"] == pytest.approx(20.0)


def test_windowed_distance_excludes_movement_before_the_window(make_tracker):
    """Positions 0 → 10 → 20 → 30 at minutes 0, 1, 2, 3.

    The window [2, 4) covers the steps arriving at minutes 2 and 3, i.e. 20 mm.
    The first 10 mm, travelled before the window opened, is not included —
    summing the raw whole-recording column over the slice would report 30.
    """
    tracker = make_tracker(make_raw(minutes=(0, 1, 2, 3), xs=(0, 10, 20, 30)))
    assert tracker.summarize((2, 4))["TotalDistance"] == pytest.approx(20.0)


def test_facet_phases_sum_to_the_whole_recording(make_tracker):
    """The core invariant: a facet split partitions distance, it does not inflate it.

    Under the old inclusive windows the boundary row's movement landed in both
    adjacent phases, so the phases summed to more than the recording total.
    """
    tracker = make_tracker(make_raw(minutes=(0, 1, 2, 3, 4), xs=(0, 10, 20, 30, 40)))
    total = tracker.summarize()["TotalDistance"]
    phases = [(0.0, 2.0), (2.0, 4.0), (4.0, float("inf"))]
    parts = [tracker.summarize(w)["TotalDistance"] for w in phases]
    assert sum(parts) == pytest.approx(total)
    assert total == pytest.approx(40.0)


def test_movement_across_a_cutoff_is_counted_once_in_the_later_phase(make_tracker):
    tracker = make_tracker(make_raw(minutes=(0, 1, 2, 3), xs=(0, 10, 20, 30)))
    first = tracker.summarize((0, 2))["TotalDistance"]
    second = tracker.summarize((2, float("inf")))["TotalDistance"]
    # The 1→2 step spans the cutoff: it belongs to the phase it arrives in.
    assert first == pytest.approx(10.0)
    assert second == pytest.approx(20.0)


def test_diagonal_movement_uses_euclidean_distance(make_tracker):
    tracker = make_tracker(make_raw(minutes=(0, 1), xs=(0, 3), ys=(0, 4)))
    assert tracker.summarize()["TotalDistance"] == pytest.approx(5.0)


def test_distance_per_minute_is_rate_over_the_window(make_tracker):
    tracker = make_tracker(make_raw(minutes=(0, 1, 2), xs=(0, 10, 20)))
    summary = tracker.summarize()
    assert summary["ObsMinutes"] == pytest.approx(2.0)
    assert summary["TotalDistancePerMin"] == pytest.approx(10.0)


def test_zero_duration_window_reports_no_rate(make_tracker):
    """A window holding one row spans no time, so mm/min is unanswerable."""
    tracker = make_tracker(make_raw(minutes=(0, 1, 2), xs=(0, 10, 20)))
    summary = tracker.summarize((1, 1.5))
    assert summary["ObsMinutes"] == pytest.approx(0.0)
    assert pd.isna(summary["TotalDistancePerMin"])


def test_empty_window_summarizes_as_missing(make_tracker):
    tracker = make_tracker(make_raw(minutes=(0, 1, 2), xs=(0, 10, 20)))
    summary = tracker.summarize((100, 200))
    assert pd.isna(summary["TotalDistance"])
    assert summary["Name"] == "T_1_0"


def test_data_subset_does_not_mutate_rawdata(make_tracker):
    tracker = make_tracker(make_raw(minutes=(0, 1, 2), xs=(0, 10, 20)))
    subset = tracker.get_data_subset((1, 3))
    subset.loc[0, "Dist_mm"] = 12345.0
    assert tracker.rawdata["Dist_mm"].sum() == pytest.approx(20.0)


# --------------------------------------------------------------------------
# Data quality
# --------------------------------------------------------------------------

def test_data_quality_fractions(make_tracker):
    tracker = make_tracker(
        make_raw(minutes=(0, 1, 2, 3), xs=(0, 1, 2, 3),
                 quality=("High", "High", "NotFound", "Indiscernible"))
    )
    dq = tracker.get_data_quality()
    assert dq["HighQuality"].iloc[0] == pytest.approx(0.5)
    assert dq["NotFound"].iloc[0] == pytest.approx(0.25)
    assert dq["Indiscernible"].iloc[0] == pytest.approx(0.25)


def test_data_quality_on_an_empty_window_is_na_not_a_crash(make_tracker):
    tracker = make_tracker()
    dq = tracker.get_data_quality((100, 200))
    assert len(dq) == 1
    assert pd.isna(dq["HighQuality"].iloc[0])


# --------------------------------------------------------------------------
# XChoiceTracker
# --------------------------------------------------------------------------

def test_xchoice_total_x_distance_respects_the_window(parameters):
    parameters.set_tracking_type(Parameters.TrackingType.XCHOICETRACKER)
    tracker = XChoiceTracker.XChoiceTracker(
        "T_1", 0, make_regions(), pd.DataFrame(), parameters, FakeDesign(),
        make_raw(minutes=(0, 1, 2, 3), xs=(0, 10, 20, 30)),
    )
    # Steps arriving at minutes 2 and 3 only.
    assert tracker.summarize((2, 4))["TotalXDistance_mm"] == pytest.approx(20.0)


# --------------------------------------------------------------------------
# TwoChoiceTracker
# --------------------------------------------------------------------------

def two_choice_tracker(parameters, raw):
    parameters.set_tracking_type(Parameters.TrackingType.TWOCHOICETRACKER)
    design = FakeDesign(counting_regions={"Light": ["Light", "LL"], "NoLight": ["NoLight", "NL"]})
    return TwoChoiceTracker.TwoChoiceTracker(
        "T_1", 0, make_regions(), pd.DataFrame(), parameters, design, raw,
    )


def test_two_choice_pi_is_plus_one_when_always_in_the_first_region(parameters):
    tracker = two_choice_tracker(
        parameters,
        make_raw(minutes=(0, 1, 2), xs=(0, 1, 2), counting_region=("Light",) * 3),
    )
    assert tracker.get_final_pi() == pytest.approx(1.0)


def test_two_choice_pi_counts_aliases_of_the_same_group(parameters):
    """'LL' is an alias of Light, so a Light/LL mix is still a pure Light preference."""
    tracker = two_choice_tracker(
        parameters,
        make_raw(minutes=(0, 1, 2), xs=(0, 1, 2), counting_region=("Light", "LL", "Light")),
    )
    assert tracker.get_final_pi() == pytest.approx(1.0)


def test_two_choice_summary_on_an_empty_window_is_na(parameters):
    tracker = two_choice_tracker(
        parameters,
        make_raw(minutes=(0, 1, 2), xs=(0, 1, 2), counting_region=("Light",) * 3),
    )
    summary = tracker.summarize((100, 200))
    assert pd.isna(summary["FinalPI"])
    assert pd.isna(summary["Transitions"])


def test_two_choice_counting_region_counts_use_named_columns(parameters):
    tracker = two_choice_tracker(
        parameters,
        make_raw(minutes=(0, 1, 2, 3), xs=(0, 1, 2, 3),
                 counting_region=("Light", "Light", "NoLight", "None")),
    )
    counts = tracker.get_counting_region_counts()
    assert counts["Light"] == 2
    assert counts["NoLight"] == 1
