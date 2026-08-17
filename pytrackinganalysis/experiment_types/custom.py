"""The Custom Experiment Type — today's freeform behaviour.

A config with no ``experiment_type`` key resolves to this. It fixes nothing,
constrains nothing, and defers entirely to the generic ``config_validation``,
so existing projects behave exactly as before (ADR-0001).
"""

from __future__ import annotations

from .base import ExperimentType


class CustomExperimentType(ExperimentType):
    name = "Custom"
    display_name = "Custom"
    # All the constraint attributes stay at their permissive base defaults:
    # tracking_type=None (from yaml), allowed_rigs=None, facet_cutoffs=None,
    # required_counting_regions=None, allow_calibration_override=True.
