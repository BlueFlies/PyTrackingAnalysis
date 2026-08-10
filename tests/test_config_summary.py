"""Tests for the project-summary builder (pure; no Qt)."""

from __future__ import annotations

from pytrackinganalysis import config_summary


def _rows(cfg):
    return dict(config_summary.summarize(cfg))


def test_valence_summary_shows_type_phases_and_treatments():
    cfg = {
        "global": {"experiment_type": "Valence", "tracking_rig": "arena_max"},
        "counting_regions": {"Light": {"alias": "L"}, "NoLight": {"alias": "N"}},
        "tracking_regions": {
            f"T_{i}": {"experimental_factors": "control" if i < 18 else "chr"}
            for i in range(36)
        },
    }
    d = _rows(cfg)
    assert d["Experiment type"] == "Valence Experiment"
    assert d["Tracking type"] == "TWOCHOICETRACKER"     # derived, not in the yaml
    assert d["Rig"] == "arena_max"
    assert "10, 70" in d["Phases"] and "Acclimation" in d["Phases"]
    assert d["Tracking regions"] == "36"
    assert "control ×18" in d["Treatments"] and "chr ×18" in d["Treatments"]
    assert d["Counting regions"] == "Light, NoLight"


def test_unassigned_treatments_are_reported():
    cfg = {"global": {"experiment_type": "Valence", "tracking_rig": "colosseum"},
           "tracking_regions": {f"T_{i}": {} for i in range(24)}}
    d = _rows(cfg)
    assert d["Tracking regions"] == "24"
    assert d["Treatments"] == "unassigned"


def test_partially_assigned_treatments():
    cfg = {"global": {"experiment_type": "Valence", "tracking_rig": "colosseum"},
           "tracking_regions": {"T_0": {"experimental_factors": "A"},
                                "T_1": {}, "T_2": {}}}
    assert "A ×1" in _rows(cfg)["Treatments"]
    assert "unassigned ×2" in _rows(cfg)["Treatments"]


def test_custom_summary_reads_yaml_tracking_type_and_flat_phases():
    cfg = {"global": {"tracking_type": "TRACKER", "tracking_rig": "small_arena"},
           "tracking_regions": {"T_0": {"experimental_factors": "A"}}}
    d = _rows(cfg)
    assert d["Experiment type"] == "Custom"
    assert d["Tracking type"] == "TRACKER"
    assert d["Phases"] == "none (flat)"


def test_non_dict_config_is_handled():
    assert config_summary.summarize(None) == [("Config", "unreadable")]
