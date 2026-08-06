"""Tests for the ExperimentType hierarchy (Phase 0): registry, derivation,
Valence constraints, and the Custom (permissive) default."""

from __future__ import annotations

import pytest

from pytrackinganalysis import Parameters
from pytrackinganalysis import experiment_types as et


def _valence_config(rig="arena_max", **global_overrides):
    g = {"experiment_type": "Valence", "tracking_rig": rig}
    g.update(global_overrides)
    return {
        "global": g,
        "counting_regions": {
            "Light": {"alias": "Light, L"},
            "NoLight": {"alias": "NoLight, N"},
        },
        "tracking_regions": {"T_0": {"experimental_factors": "control"}},
    }


# ---- registry -------------------------------------------------------------

def test_registry_resolves_names_case_insensitively():
    assert isinstance(et.get_experiment_type("Valence"), et.ValenceExperimentType)
    assert isinstance(et.get_experiment_type("valence"), et.ValenceExperimentType)
    assert isinstance(et.get_experiment_type("VALENCE"), et.ValenceExperimentType)


def test_absent_type_is_custom():
    for value in (None, "", "  "):
        t = et.get_experiment_type(value)
        assert isinstance(t, et.CustomExperimentType)
        assert t.is_custom


def test_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown experiment_type"):
        et.get_experiment_type("Aggression")


def test_available_types_lists_custom_first():
    names = [t.name for t in et.available_experiment_types()]
    assert names[0] == "Custom"
    assert "Valence" in names


# ---- derivation (ADR-0001) ------------------------------------------------

def test_valence_derives_tracking_type_and_facets_ignoring_yaml():
    t = et.get_experiment_type("Valence")
    g = {}  # minimal yaml: neither field present
    assert t.resolve_tracking_type(g) == Parameters.TrackingType.TWOCHOICETRACKER
    assert t.resolve_facet_cutoffs(g) == (10, 70)
    assert t.owned_keys() == {"tracking_type", "facet_cutoffs", "fps", "mm_per_pixel"}


def test_custom_reads_tracking_type_and_facets_from_yaml():
    t = et.get_experiment_type(None)
    g = {"tracking_type": "TWOCHOICECOUNTER", "facet_cutoffs": [5, 30]}
    assert t.resolve_tracking_type(g) == Parameters.TrackingType.TWOCHOICECOUNTER
    assert t.resolve_facet_cutoffs(g) == (5, 30)
    assert t.owned_keys() == set()


def test_valence_phase_labels():
    t = et.get_experiment_type("Valence")
    assert t.phase_label(0, (0, 10)) == "Acclimation"
    assert t.phase_label(1, (10, 70)) == "Experiment"
    assert t.phase_label(2, (70, float("inf"))) == "Cooldown"


# ---- validation -----------------------------------------------------------

def test_valence_accepts_a_well_formed_config():
    t = et.get_experiment_type("Valence")
    assert t.validate(_valence_config()) == []
    assert t.validate(_valence_config(rig="colosseum")) == []


def test_valence_rejects_wrong_rig():
    t = et.get_experiment_type("Valence")
    problems = t.validate(_valence_config(rig="small_arena"))
    assert any("tracking_rig" in p for p in problems)


def test_valence_requires_a_rig():
    t = et.get_experiment_type("Valence")
    problems = t.validate(_valence_config(rig=""))
    assert any("choose a tracking_rig" in p for p in problems)


def test_valence_rejects_conflicting_owned_fields():
    t = et.get_experiment_type("Valence")
    p1 = t.validate(_valence_config(tracking_type="TRACKER"))
    assert any("tracking_type is fixed" in p for p in p1)
    p2 = t.validate(_valence_config(facet_cutoffs=[5, 20]))
    assert any("facets are fixed" in p for p in p2)
    p3 = t.validate(_valence_config(mm_per_pixel=0.05))
    assert any("mm_per_pixel" in p for p in p3)


def test_valence_requires_light_nolight_in_order():
    t = et.get_experiment_type("Valence")
    cfg = _valence_config()
    cfg["counting_regions"] = {"NoLight": {"alias": "N"}, "Light": {"alias": "L"}}
    assert any("in that order" in p for p in t.validate(cfg))

    cfg2 = _valence_config()
    cfg2["counting_regions"] = {"Light": {"alias": "L"}, "Dark": {"alias": "D"}}
    assert any("Light" in p and "NoLight" in p for p in t.validate(cfg2))


def test_valence_requires_nonempty_aliases():
    t = et.get_experiment_type("Valence")
    cfg = _valence_config()
    cfg["counting_regions"]["Light"] = {"alias": ""}
    assert any("alias" in p for p in t.validate(cfg))


def test_valence_requires_tracking_regions():
    t = et.get_experiment_type("Valence")
    cfg = _valence_config()
    cfg["tracking_regions"] = {}
    assert any("tracking_regions" in p for p in t.validate(cfg))


def test_custom_validate_is_permissive():
    t = et.get_experiment_type(None)
    assert t.validate({"global": {"tracking_type": "TRACKER"}}) == []


# ---- scaffold / report ----------------------------------------------------

def test_valence_scaffold_is_shaped_but_incomplete():
    t = et.get_experiment_type("Valence")
    cfg = t.scaffold_config()
    assert cfg["global"]["experiment_type"] == "Valence"
    assert list(cfg["counting_regions"]) == ["Light", "NoLight"]
    # Rig blank on purpose → scaffold does not yet validate.
    assert any("tracking_rig" in p for p in t.validate(cfg))


def test_report_title_and_intro():
    assert et.get_experiment_type("Valence").report_title() == "Valence Experiment Report"
    assert et.get_experiment_type("Valence").report_intro()
    assert et.get_experiment_type(None).report_title() == "Tracking Analysis Report"
    assert et.get_experiment_type(None).report_intro() is None


# ---- config_validation integration (Phase 4) ------------------------------

def test_validate_config_consults_the_type():
    from pytrackinganalysis import config_validation
    assert config_validation.validate_config(_valence_config()) == []
    assert config_validation.validate_config(_valence_config(rig="colosseum")) == []
    bad = config_validation.validate_config(_valence_config(rig="small_arena"))
    assert any("tracking_rig" in p for p in bad)


def test_validate_config_reports_unknown_experiment_type():
    cfg = _valence_config()
    cfg["global"]["experiment_type"] = "Nope"
    assert any("Unknown experiment_type" in p
               for p in __import__("pytrackinganalysis.config_validation",
                                   fromlist=["x"]).validate_config(cfg))


def test_custom_config_validation_unchanged():
    # A two-choice Custom config with only one counting group still trips the
    # generic 'exactly two' rule (unchanged behaviour).
    from pytrackinganalysis import config_validation
    cfg = {"global": {"tracking_type": "TWOCHOICECOUNTER", "tracking_rig": "small_arena"},
           "counting_regions": {"Light": {"alias": "L"}},
           "tracking_regions": {"T_0": {}}}
    assert any("exactly two" in p for p in config_validation.validate_config(cfg))


# ---- Experiment fail-hard-at-load (Phase 1) -------------------------------

def _exp_stub(config, exp_type_name):
    """An Experiment with just the attributes _validate_config touches."""
    from pytrackinganalysis.Experiment import Experiment
    exp = Experiment.__new__(Experiment)
    exp.config = config
    exp.config_path = "tracking_config.yaml"
    exp.experiment_type = et.get_experiment_type(exp_type_name)
    return exp


def test_typed_experiment_fails_hard_on_bad_config():
    exp = _exp_stub(_valence_config(rig="small_arena"), "Valence")
    with pytest.raises(ValueError, match="Valence Experiment configuration"):
        exp._validate_config()


def test_typed_experiment_accepts_valid_config():
    _exp_stub(_valence_config(), "Valence")._validate_config()  # must not raise


def test_custom_experiment_warns_but_does_not_raise(capsys):
    cfg = {"global": {"tracking_type": "TWOCHOICECOUNTER", "tracking_rig": "small_arena"},
           "counting_regions": {"Light": {"alias": "L"}},  # only one -> a problem
           "tracking_regions": {"T_0": {}}}
    _exp_stub(cfg, None)._validate_config()  # lenient: no raise
    assert "Warning" in capsys.readouterr().out
