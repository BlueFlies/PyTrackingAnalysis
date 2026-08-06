"""The ``ExperimentType`` base class.

An Experiment Type (see ``CONTEXT.md``) is a named bundle that selects one
Tracking Type and constrains the rest of an experiment. Per ADR-0002 this is a
base class with one subclass per type, composed into ``Experiment`` as a
strategy: ``Experiment`` stays the orchestrator and asks its ``ExperimentType``
for type-specific decisions.

Per ADR-0001 the type *owns* its fixed fields — a typed ``tracking_config.yaml``
omits them and they are derived here, never written to disk. The base class is
the permissive default (this is what a Custom Experiment uses); concrete types
override the class attributes and, where needed, the methods.
"""

from __future__ import annotations

from .. import Parameters, config_validation


class ExperimentType:
    """Permissive base type. A Custom Experiment uses this behaviour directly."""

    #: Canonical key stored in the yaml (``experiment_type:``). Case-insensitive.
    name: str = "Custom"
    #: Human label for menus, the report cover, dialogs.
    display_name: str = "Custom"

    #: Fixed Tracking Type, or ``None`` to read it from the yaml (Custom).
    tracking_type: Parameters.TrackingType | None = None
    #: Allowed rig names (canonical), or ``None`` for no constraint.
    allowed_rigs: tuple[str, ...] | None = None
    #: Fixed facet cutoffs, or ``None`` to read from the yaml (Custom).
    facet_cutoffs: tuple[float, ...] | None = None
    #: Names for the phases; ``len`` should equal ``len(facet_cutoffs) + 1``.
    phase_labels: tuple[str, ...] = ()
    #: Ordered required counting-region group keys, or ``None`` for no constraint.
    required_counting_regions: tuple[str, ...] | None = None
    #: Whether the user may override fps / mm_per_pixel (False = rig preset only).
    allow_calibration_override: bool = True

    # ---- identity -----------------------------------------------------

    @property
    def is_custom(self) -> bool:
        return self.tracking_type is None and self.allowed_rigs is None

    # ---- derivation (ADR-0001: type owns these) -----------------------

    def resolve_tracking_type(self, global_cfg: dict) -> Parameters.TrackingType:
        """The Tracking Type to use: fixed by the type, else read from the yaml."""
        if self.tracking_type is not None:
            return self.tracking_type
        raw = str(global_cfg.get("tracking_type", "TRACKER")).upper()
        try:
            return Parameters.TrackingType[raw]
        except KeyError as err:
            raise ValueError(
                f"Unknown tracking_type '{raw}'. "
                f"Valid values: {[t.name for t in Parameters.TrackingType]}"
            ) from err

    def resolve_facet_cutoffs(self, global_cfg: dict):
        """The facet cutoffs to use: fixed by the type, else read from the yaml."""
        if self.facet_cutoffs is not None:
            return tuple(self.facet_cutoffs)
        raw = global_cfg.get("facet_cutoffs")
        return tuple(raw) if raw is not None else None

    def owned_keys(self) -> set[str]:
        """``global:`` keys the type owns — the user must not set them."""
        owned: set[str] = set()
        if self.tracking_type is not None:
            owned.add("tracking_type")
        if self.facet_cutoffs is not None:
            owned.add("facet_cutoffs")
        if not self.allow_calibration_override:
            owned |= {"fps", "mm_per_pixel"}
        return owned

    # ---- phases / report labelling ------------------------------------

    def phase_label(self, index: int, window) -> str:
        """Label for the phase at *index* (window is a ``(start, end)`` tuple)."""
        if 0 <= index < len(self.phase_labels):
            return self.phase_labels[index]
        # Fall back to a minute-range label like the generic report uses.
        start, end = window
        fmt = lambda v: f"{int(v)}" if float(v) == int(v) else f"{v:g}"  # noqa: E731
        return f"{fmt(start)}+" if end == float("inf") else f"{fmt(start)}–{fmt(end)}"

    # ---- report / outputs ---------------------------------------------

    def report_title(self) -> str:
        return "Tracking Analysis Report" if self.is_custom \
            else f"{self.display_name} Report"

    def report_intro(self) -> str | None:
        """Optional narrative paragraph for the top of the report."""
        return None

    def output_manifest(self) -> list[str]:
        """Filename suffixes (within ``analysis/``) this type is expected to
        produce. Declarative — used to verify a run produced what it should.
        Empty means 'no specific expectation' (Custom)."""
        return []

    # ---- validation (ADR-0001: fail hard for typed) -------------------

    def validate(self, config: dict) -> list[str]:
        """Type-specific problems, on top of the generic ``config_validation``.

        The base type adds nothing (a Custom Experiment is unconstrained).
        """
        return []

    # ---- new-project scaffold -----------------------------------------

    def scaffold_config(self) -> dict:
        """A minimal, intentionally-incomplete starter config for a new project
        of this type. Base type: a bare Custom config."""
        return {"global": {"tracking_type": "TRACKER", "tracking_rig": ""},
                "tracking_regions": {}}

    # ---- shared validation helpers (for subclasses) -------------------

    def _validate_rig(self, global_cfg: dict) -> list[str]:
        if self.allowed_rigs is None:
            return []
        rig = config_validation.normalize_rig(global_cfg.get("tracking_rig"))
        allowed = " or ".join(self.allowed_rigs)
        if not rig:
            return [f"{self.display_name}: choose a tracking_rig ({allowed})."]
        if rig not in self.allowed_rigs:
            return [f"{self.display_name}: tracking_rig must be {allowed}; "
                    f"got '{global_cfg.get('tracking_rig')}'."]
        return []

    def _validate_owned_fields(self, global_cfg: dict) -> list[str]:
        problems = []
        if self.tracking_type is not None:
            tt = global_cfg.get("tracking_type")
            if tt is not None and str(tt).upper() != self.tracking_type.name:
                problems.append(
                    f"{self.display_name}: tracking_type is fixed to "
                    f"{self.tracking_type.name}; remove the conflicting "
                    f"'tracking_type: {tt}'.")
        if self.facet_cutoffs is not None:
            fc = global_cfg.get("facet_cutoffs")
            if fc is not None and tuple(fc) != tuple(self.facet_cutoffs):
                problems.append(
                    f"{self.display_name}: facets are fixed to "
                    f"{list(self.facet_cutoffs)}; remove 'facet_cutoffs'.")
        if not self.allow_calibration_override:
            for key in ("fps", "mm_per_pixel"):
                if global_cfg.get(key) is not None:
                    problems.append(
                        f"{self.display_name}: '{key}' override is not allowed; "
                        f"calibration comes from the rig preset.")
        return problems

    def _validate_required_counting_regions(self, config: dict) -> list[str]:
        if self.required_counting_regions is None:
            return []
        required = list(self.required_counting_regions)
        regions = config.get("counting_regions")
        if not isinstance(regions, dict) or not regions:
            return [f"{self.display_name}: requires counting_regions "
                    f"{required} (in that order)."]
        keys = list(regions.keys())
        if keys != required:
            return [f"{self.display_name}: counting_regions must be exactly "
                    f"{required} in that order; got {keys}."]
        problems = []
        for key in required:
            group = regions.get(key)
            aliases = [] if not isinstance(group, dict) else \
                [a.strip() for a in str(group.get("alias", "")).split(",") if a.strip()]
            if not aliases:
                problems.append(
                    f"{self.display_name}: counting_regions.{key} needs at least "
                    f"one alias (the raw DTrack label).")
        return problems
