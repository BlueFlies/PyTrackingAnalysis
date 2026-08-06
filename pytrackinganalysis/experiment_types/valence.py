"""The Valence Experiment Type — the first concrete type.

A two-choice light-preference assay: a two-choice tracker with Light vs NoLight
counting regions on a Max or Colosseum arena, with a fixed three-phase structure
(acclimation / experiment / cooldown from cutoffs [10, 70]). See ``CONTEXT.md``
and ADR-0001.
"""

from __future__ import annotations

from .. import Parameters
from .base import ExperimentType


class ValenceExperimentType(ExperimentType):
    name = "Valence"
    display_name = "Valence Experiment"

    tracking_type = Parameters.TrackingType.TWOCHOICETRACKER
    allowed_rigs = ("arena_max", "colosseum")
    facet_cutoffs = (10, 70)
    phase_labels = ("Acclimation", "Experiment", "Cooldown")
    required_counting_regions = ("Light", "NoLight")
    allow_calibration_override = False

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
                "Light": {"alias": "Light, LL, L"},
                "NoLight": {"alias": "NoLight, NL, N"},
            },
            "tracking_regions": {},
        }
