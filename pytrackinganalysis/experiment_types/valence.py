"""The Valence Experiment Type — the first concrete type.

A two-choice light-preference assay: a two-choice tracker with Light vs NoLight
counting regions on a Max or Colosseum arena, with a fixed three-phase structure
(acclimation / experiment / cooldown from cutoffs [10, 70]). See ``CONTEXT.md``
and ADR-0001.
"""

from __future__ import annotations

from .. import Parameters, config_validation
from .base import ExperimentType

# Default counting-region aliases for a fresh Valence project (editable later).
_LIGHT_ALIAS = "Light, Left1, Left2, Left3, Right4, Right5, Right6"
_NOLIGHT_ALIAS = "NoLight, Right1, Right2, Right3, Left4, Left5, Left6"
# Arena Max: the first 18 wells face the opposite way, so their X axis is
# flipped (-1) to orient Light consistently; the rest are +1. Colosseum: all +1.
_MAX_XFLIP_COUNT = 18


class ValenceExperimentType(ExperimentType):
    name = "Valence"
    display_name = "Valence Experiment"

    tracking_type = Parameters.TrackingType.TWOCHOICETRACKER
    allowed_rigs = ("arena_max", "colosseum")
    facet_cutoffs = (10, 70)   # a default; the user may change it (facets_fixed=False)
    facets_fixed = False
    phase_labels = ("Acclimation", "Experiment", "Cooldown")
    required_counting_regions = ("Light", "NoLight")
    allow_calibration_override = False
    # The plate is fixed by the rig: Arena Max has 36 wells (T_0..T_35),
    # Colosseum has 24 (T_0..T_23).
    region_counts = {"arena_max": 36, "colosseum": 24}

    def report_intro(self) -> str:
        return ("A two-choice light-preference (valence) assay. Positive PI means "
                "the animals prefer Light over NoLight. The recording is split into "
                "three phases: Acclimation (0–10 min), Experiment (10–70 min, the "
                "phase the primary result is read from), and Cooldown (70+ min).")

    def output_manifest(self) -> list[str]:
        # The data outputs a Valence run is expected to produce in analysis/.
        return ["_Summary.csv", "_Summary_Facet.csv", "_Stats.txt"]

    def validate(self, config: dict) -> list[str]:
        global_cfg = config.get("global") or {}
        problems: list[str] = []
        problems += self._validate_owned_fields(global_cfg)
        problems += self._validate_rig(global_cfg)
        problems += self._validate_required_counting_regions(config)
        if not config.get("tracking_regions"):
            problems.append(
                f"{self.display_name}: no tracking_regions defined — assign each "
                f"region's treatment before running.")
        else:
            problems += self._validate_required_tracking_regions(config)
        return problems

    def scaffold_config(self) -> dict:
        # Rig is intentionally left blank: the user must choose Max or Colosseum,
        # so a freshly scaffolded project fails validation until they do.
        return {
            "global": {
                "experiment_type": self.name,
                "tracking_rig": "",
            },
            "counting_regions": {
                "Light": {"alias": _LIGHT_ALIAS},
                "NoLight": {"alias": _NOLIGHT_ALIAS},
            },
            "tracking_regions": {},
        }

    def build_config(self, *, rig=None, facet_cutoffs=None, factors=None, **_) -> dict:
        """Full Valence config for the create wizard.

        Lays out the rig's plate with the correct X multipliers (Arena Max flips
        the first 18 wells; Colosseum is all +1), the Light/NoLight counting
        regions, the chosen (or default) facets, and any design factors. Region
        treatments are left blank for the user to assign.
        """
        g: dict = {"experiment_type": self.name}
        if rig:
            g["tracking_rig"] = rig
        cutoffs = facet_cutoffs if facet_cutoffs else self.facet_cutoffs
        g["facet_cutoffs"] = self._clean_cutoffs(cutoffs)
        if factors:
            g["experimental_design_factors"] = dict(factors)

        names = self.regions_for_rig(rig) or []
        flip = _MAX_XFLIP_COUNT if config_validation.normalize_rig(rig) == "arena_max" else 0
        tracking_regions = {
            name: {
                "experimental_factors": "",
                "x_location_multiplier": -1 if i < flip else 1,
                "y_location_multiplier": 1,
            }
            for i, name in enumerate(names)
        }
        return {
            "global": g,
            "counting_regions": {
                "Light": {"alias": _LIGHT_ALIAS},
                "NoLight": {"alias": _NOLIGHT_ALIAS},
            },
            "tracking_regions": tracking_regions,
        }
