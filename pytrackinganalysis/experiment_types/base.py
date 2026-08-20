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
    #: Facet cutoffs the type suggests. By default this is only a *default*
    #: (the user may change it); set ``facets_fixed = True`` to make it immovable.
    #: ``None`` means "read entirely from the yaml" (Custom).
    facet_cutoffs: tuple[float, ...] | None = None
    #: When True the type owns ``facet_cutoffs`` (immovable). When False (default)
    #: ``facet_cutoffs`` above is only a starting default the user can override.
    facets_fixed: bool = False
    #: Names for the phases of the *default* facet structure; ``len`` should equal
    #: ``len(facet_cutoffs) + 1``. Applied only when the actual cutoffs match the
    #: default (see :meth:`phase_labels_for`).
    phase_labels: tuple[str, ...] = ()
    #: Ordered required counting-region group keys, or ``None`` for no constraint.
    required_counting_regions: tuple[str, ...] | None = None
    #: Whether the user may override fps / mm_per_pixel (False = rig preset only).
    allow_calibration_override: bool = True
    #: For a type whose plate is fixed by the rig, the number of tracking regions
    #: per canonical rig name, e.g. ``{"arena_max": 36}``. Empty = no constraint.
    region_counts: dict = {}
    #: Default for the Low-Transition Exclusion (see CONTEXT.md / ADR-0003):
    #: a fly is kept only if its Transitions count during the Primary Phase is
    #: at least ``min_transitions`` (yaml-overridable; 0 = off). ``None`` means
    #: the type has no exclusion criterion at all (Custom and most types).
    default_min_transitions: int | None = None

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
        """The facet cutoffs to use.

        Fixed by the type when ``facets_fixed``; otherwise the yaml value if
        present, falling back to the type's default (``facet_cutoffs``).
        """
        if self.facets_fixed and self.facet_cutoffs is not None:
            return tuple(self.facet_cutoffs)
        raw = global_cfg.get("facet_cutoffs")
        if raw is not None:
            return tuple(raw)
        return tuple(self.facet_cutoffs) if self.facet_cutoffs is not None else None

    def resolve_min_transitions(self, global_cfg: dict) -> int | None:
        """The effective Low-Transition Exclusion threshold, or ``None`` when
        the type has no such criterion. The yaml's ``min_transitions`` wins
        over the type default; 0 disables the exclusion."""
        if self.default_min_transitions is None:
            return None
        raw = (global_cfg or {}).get("min_transitions")
        if raw is None:
            return int(self.default_min_transitions)
        return int(raw)

    def compute_exclusions(self, experiment):
        """Flies the type excludes from every result (ADR-0003), as a DataFrame
        of Name/TrackingRegion/Treatment/Transitions rows, or ``None`` when the
        type has no exclusion criterion. Base/Custom: none."""
        return None

    def regions_for_rig(self, rig) -> list[str] | None:
        """Expected tracking-region names for *rig*, or ``None`` when the type
        does not fix the plate. A rig with 36 regions yields ``T_0``..``T_35``."""
        n = self.region_counts.get(config_validation.normalize_rig(rig))
        if not n:
            return None
        return [f"T_{i}" for i in range(n)]

    def owned_keys(self) -> set[str]:
        """``global:`` keys the type owns — the user must not set them."""
        owned: set[str] = set()
        if self.tracking_type is not None:
            owned.add("tracking_type")
        if self.facets_fixed:
            owned.add("facet_cutoffs")
        if not self.allow_calibration_override:
            owned |= {"fps", "mm_per_pixel"}
        return owned

    # ---- phases / report labelling ------------------------------------

    def _minute_label(self, window) -> str:
        start, end = window
        fmt = lambda v: f"{int(v)}" if float(v) == int(v) else f"{v:g}"  # noqa: E731
        return f"{fmt(start)}+" if end == float("inf") else f"{fmt(start)}–{fmt(end)}"

    def resolve_facet_labels(self, global_cfg: dict) -> tuple[str, ...] | None:
        """User-chosen phase names from the yaml (``facet_labels``), or ``None``."""
        raw = (global_cfg or {}).get("facet_labels")
        if not raw or not isinstance(raw, (list, tuple)):
            return None
        return tuple(str(label) for label in raw)

    def phase_labels_for(self, windows, global_cfg: dict | None = None) -> list[str]:
        """Labels for each facet window (a list of ``(start, end)`` tuples).

        Precedence: the yaml's ``facet_labels`` (when it names every window),
        then the type's named phases (e.g. Acclimation/Experiment/Cooldown) —
        used only when the actual windows match the type's *default* facet
        structure — then honest minute-range labels, so mismatched or missing
        names never mislabel a phase.
        """
        windows = list(windows)
        user_labels = self.resolve_facet_labels(global_cfg or {})
        if user_labels and len(user_labels) == len(windows):
            return list(user_labels)
        if self.phase_labels and self.facet_cutoffs is not None \
                and len(windows) == len(self.phase_labels):
            from .. import windowing
            if windows == list(windowing.facet_windows(self.facet_cutoffs)):
                return list(self.phase_labels)
        return [self._minute_label(w) for w in windows]

    # ---- report / outputs ---------------------------------------------

    def report_title(self) -> str:
        return "Tracking Analysis Report" if self.is_custom \
            else f"{self.display_name} Report"

    def report_intro(self) -> str | None:
        """Optional narrative paragraph for the top of the report."""
        return None

    def report_sections(self, experiment) -> list:
        """Type-specific report blocks, inserted after the report intro and
        before the generic figures (ADR-0002: the type decides what its report
        leads with). Base/Custom: none — the generic report stands alone."""
        return []

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

    @staticmethod
    def _clean_cutoffs(cutoffs):
        """Render cutoffs as whole minutes where possible (10.0 -> 10)."""
        return [int(c) if float(c) == int(c) else c for c in cutoffs]

    def build_config(self, *, tracking_type=None, rig=None, facet_cutoffs=None,
                     facet_labels=None, factors=None) -> dict:
        """Build a full ``tracking_config.yaml`` dict from create-wizard inputs.

        Base (Custom) build: writes ``tracking_type`` (from the wizard), the rig,
        optional facets and factors, and an empty tracking_regions table for the
        user to fill. Concrete types override to lay out their plate and regions.
        """
        g: dict = {}
        if not self.is_custom:
            g["experiment_type"] = self.name
        if self.tracking_type is None and tracking_type:
            g["tracking_type"] = tracking_type
        if rig:
            g["tracking_rig"] = rig
        if facet_cutoffs:
            g["facet_cutoffs"] = self._clean_cutoffs(facet_cutoffs)
            labels = self._default_facet_labels(facet_cutoffs, facet_labels)
            if labels:
                g["facet_labels"] = labels
        if factors:
            g["experimental_design_factors"] = dict(factors)
        return {"global": g, "tracking_regions": {}}

    def _default_facet_labels(self, cutoffs, facet_labels) -> list[str] | None:
        """Phase names to write for a new config: the wizard's, else the type's
        defaults — but only when they name every window of *cutoffs*."""
        for candidate in (facet_labels, self.phase_labels):
            if candidate and len(candidate) == len(cutoffs) + 1:
                return [str(label) for label in candidate]
        return None

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
        if self.facets_fixed and self.facet_cutoffs is not None:
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

    def _validate_required_tracking_regions(self, config: dict) -> list[str]:
        """When the rig fixes the plate, the tracking regions must be exactly the
        expected ``T_0``..``T_{n-1}`` set. Skipped when the rig is unset (the
        'choose a rig' problem fires instead) or the type does not fix regions."""
        global_cfg = config.get("global") or {}
        expected = self.regions_for_rig(global_cfg.get("tracking_rig"))
        if expected is None:
            return []
        have = list((config.get("tracking_regions") or {}).keys())
        if have != expected:
            return [f"{self.display_name}: this rig requires exactly "
                    f"{len(expected)} tracking regions ({expected[0]}..{expected[-1]}); "
                    f"got {len(have)}."]
        return []

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
