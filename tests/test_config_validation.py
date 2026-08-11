"""Semantic checks on tracking_config.yaml."""

from __future__ import annotations

import yaml

from pytrackinganalysis.config_validation import validate_config, validate_config_file


def base_config(**global_overrides):
    global_cfg = {
        "tracking_type": "TRACKER",
        "tracking_rig": "small_arena",
    }
    global_cfg.update(global_overrides)
    return {
        "global": global_cfg,
        "tracking_regions": {"T_1": {"experimental_factors": "A"}},
    }


def problems_for(config):
    return " | ".join(validate_config(config))


def test_a_minimal_valid_config_has_no_problems():
    assert validate_config(base_config()) == []


def test_unknown_rig_is_reported():
    assert "Unknown tracking_rig" in problems_for(base_config(tracking_rig="teleporter"))


def test_unknown_tracking_type_is_reported():
    assert "Unknown tracking_type" in problems_for(base_config(tracking_type="WOBBLER"))


def test_movie_rig_requires_its_calibration():
    found = problems_for(base_config(tracking_rig="movie"))
    assert "fps" in found and "mm_per_pixel" in found


def test_movie_rig_with_calibration_is_accepted():
    assert validate_config(base_config(tracking_rig="movie", fps=30, mm_per_pixel=0.05)) == []


def test_missing_tracking_regions_is_reported():
    config = base_config()
    del config["tracking_regions"]
    assert "No tracking_regions" in problems_for(config)


def test_location_multiplier_must_be_plus_or_minus_one():
    config = base_config()
    config["tracking_regions"]["T_1"]["x_location_multiplier"] = 2
    assert "x_location_multiplier" in problems_for(config)


def test_two_choice_requires_exactly_two_counting_groups():
    config = base_config(tracking_type="TWOCHOICETRACKER")
    config["counting_regions"] = {"Light": {"alias": "Light"}}
    assert "exactly two counting_regions" in problems_for(config)


def test_two_choice_with_two_groups_is_accepted():
    config = base_config(tracking_type="TWOCHOICETRACKER")
    config["counting_regions"] = {
        "Light": {"alias": "Light, LL"},
        "NoLight": {"alias": "NoLight"},
    }
    assert validate_config(config) == []


def test_counting_group_without_an_alias_is_reported():
    config = base_config(tracking_type="TWOCHOICETRACKER")
    config["counting_regions"] = {"Light": {}, "NoLight": {"alias": "NoLight"}}
    assert "missing its 'alias' key" in problems_for(config)


def test_facet_cutoffs_must_increase_and_be_distinct():
    assert "increase" in problems_for(base_config(facet_cutoffs=[70, 10]))
    assert "distinct" in problems_for(base_config(facet_cutoffs=[10, 10]))


def test_facet_cutoffs_must_be_numeric():
    assert "must be numbers" in problems_for(base_config(facet_cutoffs=["ten"]))


def test_facet_labels_must_name_every_phase():
    ok = base_config(facet_cutoffs=[10, 70],
                     facet_labels=["Warmup", "Assay", "Rest"])
    assert validate_config(ok) == []
    bad = base_config(facet_cutoffs=[10, 70], facet_labels=["Warmup", "Assay"])
    assert "3 phases" in problems_for(bad)


def test_facet_labels_require_cutoffs_and_real_names():
    assert "requires facet_cutoffs" in problems_for(
        base_config(facet_labels=["A", "B"]))
    assert "non-empty list" in problems_for(
        base_config(facet_cutoffs=[10], facet_labels="Warmup, Assay"))
    assert "non-empty strings" in problems_for(
        base_config(facet_cutoffs=[10], facet_labels=["Warmup", ""]))


def test_micromove_range_must_be_ordered():
    assert "minimum must be below" in problems_for(base_config(micromove_speed_mm_sec=[2, 0.2]))


def test_negative_mm_per_pixel_is_reported():
    assert "greater than zero" in problems_for(base_config(mm_per_pixel=-1))


def test_empty_file_is_reported(tmp_path):
    path = tmp_path / "tracking_config.yaml"
    path.write_text("")
    assert validate_config_file(str(path)) == ["The file is empty."]


def test_syntax_error_is_reported(tmp_path):
    path = tmp_path / "tracking_config.yaml"
    path.write_text("global:\n  tracking_type: [unclosed\n")
    assert "YAML syntax error" in " ".join(validate_config_file(str(path)))


def test_missing_file_is_reported(tmp_path):
    assert "File not found" in " ".join(validate_config_file(str(tmp_path / "nope.yaml")))


def test_a_valid_file_round_trips(tmp_path):
    path = tmp_path / "tracking_config.yaml"
    path.write_text(yaml.safe_dump(base_config()))
    assert validate_config_file(str(path)) == []


# --------------------------------------------------------------------------
# Legacy wrappers
# --------------------------------------------------------------------------

def test_special_function_wrappers_match_their_arena_targets():
    """A wrapper whose defaults drift from its target is a silent behaviour change."""
    import inspect

    from pytrackinganalysis import SpecialFunctions
    from pytrackinganalysis.Arena import Arena

    for name in ("analyze_rle_data", "analyze_rle_data_facet",
                 "analyze_distance_by_light", "analyze_distance_by_light_facet"):
        wrapper = inspect.signature(getattr(SpecialFunctions, name))
        target = inspect.signature(getattr(Arena, name))
        for param, spec in target.parameters.items():
            if param == "self" or spec.default is inspect.Parameter.empty:
                continue
            assert param in wrapper.parameters, f"{name}: wrapper is missing {param}"
            assert wrapper.parameters[param].default == spec.default, (
                f"{name}: default for {param} drifted "
                f"({wrapper.parameters[param].default!r} vs {spec.default!r})"
            )
