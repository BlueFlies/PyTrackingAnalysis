"""Project: a marker-file parent of replicate Experiments (ADR-0005).

A directory with a ``project.yaml`` is a Project; its immediate subdirectories
containing a ``tracking_config.yaml`` are its Experiments — replicates of one
design, hard-validated to share the Experiment Type and the experimental
design factors and levels exactly. The Project owns the Combined Analysis
(stacked *filtered* per-replicate summaries with an ``Experiment`` column,
pooled + mixed-model statistics), the project-level publication figures
(``plot_specs.yaml`` / ``figures/``), and the Project Report
(``<project>/<name>_report.pdf``), with an opt-in AI narrative through the
same ``ai/`` stack the per-experiment report uses.
"""

from __future__ import annotations

import glob
import os

import pandas as pd
import yaml

from . import experiment_types, windowing
from .io_utils import atomic_write_text

PROJECT_FILENAME = "project.yaml"
#: The per-Experiment config. A Project never has one of its own: the shared
#: design lives in ``project.yaml`` and each replicate carries this file.
CONFIG_FILENAME = "tracking_config.yaml"

def is_project_dir(path) -> bool:
    return os.path.isfile(os.path.join(str(path), PROJECT_FILENAME))


def is_experiment_dir(path) -> bool:
    return os.path.isfile(os.path.join(str(path), CONFIG_FILENAME))


def has_experiment_data(path) -> bool:
    """True when *path* holds a recording: a ``data/`` subdirectory with at
    least one ``.xlsx`` workbook (the DTrack export that defines an
    experiment). This is the experiment-shape test for listing candidate
    replicates in the Project view; any other subdirectory is ignored."""
    data = os.path.join(str(path), "data")
    try:
        entries = os.listdir(data)
    except OSError:
        return False
    return any(entry.lower().endswith(".xlsx") for entry in entries)


def create_project_file(project_dir, name: str | None = None,
                        notes: str = "", design: dict | None = None) -> str:
    """Write (or update) ``project.yaml`` — upgrading e.g. an old batch
    parent. An existing file's unknown keys are preserved; name/notes are
    (re)written, and *design* (when given) replaces the ``design:`` section —
    the authoritative shared parameters every replicate must match.

    A file with no ``scripts:`` key at all is seeded with the default Project
    Script (ADR-0009 amendment) so every Project ships a visible, editable
    default run. An existing block is never touched — an empty list is a
    deliberate deletion, and re-seeding it would undo the user's edit.
    """
    from .script_editor.project_actions import default_project_script

    path = os.path.join(str(project_dir), PROJECT_FILENAME)
    payload: dict = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    payload["name"] = name or payload.get("name") \
        or os.path.basename(os.path.normpath(project_dir))
    if notes:
        payload["notes"] = notes
    elif "notes" in payload and not notes:
        payload.pop("notes")
    if design is not None:
        payload["design"] = design
    if "scripts" not in payload:
        payload["scripts"] = [default_project_script()]
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
    return path


def _normalize(value):
    """Comparison form for design values: numbers as floats, sequences as
    lists of normalized items, everything else as-is."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


class _NameShim:
    """Duck-typed ``arena`` so the AI payload builder (which reads
    ``experiment.arena.experiment_name``) works on a Project unchanged."""

    def __init__(self, name: str):
        self.experiment_name = name


class Project:
    """The loaded Project: replicate discovery, design-match validation, the
    Combined Analysis, and the Project Report."""

    def __init__(self, project_dir: str):
        self.project_directory = os.path.abspath(str(project_dir))
        marker = os.path.join(self.project_directory, PROJECT_FILENAME)
        if not os.path.isfile(marker):
            raise FileNotFoundError(
                f"Not a Project: no {PROJECT_FILENAME} in "
                f"{self.project_directory}")
        with open(marker, encoding="utf-8") as handle:
            meta = yaml.safe_load(handle) or {}
        self.name = str(meta.get("name") or os.path.basename(
            self.project_directory))
        self.notes = str(meta.get("notes") or "")
        #: The authoritative shared design (ADR-0005 amendment): keys under
        #: ``design.global`` are enforced on every replicate's resolved
        #: config; ``design.counting_regions`` fixes the counting-region
        #: NAMES (aliases stay per-experiment). Absent -> legacy
        #: agreement-based validation.
        self.design: dict = dict(meta.get("design") or {})

        self.analysis_path = os.path.join(self.project_directory, "analysis") + os.sep
        self.arena = _NameShim(self.name)  # AI-payload compatibility

        # ---- discover replicates -------------------------------------
        self.experiment_names: list[str] = []
        self.configs: dict[str, dict] = {}
        for entry in sorted(os.listdir(self.project_directory)):
            sub = os.path.join(self.project_directory, entry)
            if os.path.isdir(sub) and is_experiment_dir(sub):
                self.experiment_names.append(entry)
                with open(os.path.join(sub, CONFIG_FILENAME),
                          encoding="utf-8") as handle:
                    self.configs[entry] = yaml.safe_load(handle) or {}
        if not self.experiment_names and not self.design:
            ## With a design in project.yaml an empty Project is legal — it
            ## was just created; replicates get scaffolded from the design.
            raise ValueError(
                f"Project '{self.name}' has no experiments: no subdirectory "
                f"of {self.project_directory} contains a {CONFIG_FILENAME}")

        #: Project Scripts and centrally-held Experiment Scripts (ADR-0006).
        ## Lenient here: a malformed block must not block loading the Project
        ## (the Script Editor and runner surface the specifics).
        def _script_list(key):
            raw = meta.get(key) or []
            return [dict(item) for item in raw
                    if isinstance(item, dict) and item.get("name")]
        self.scripts: list[dict] = _script_list("scripts")
        self.experiment_scripts: list[dict] = _script_list("experiment_scripts")

        self.warnings: list[str] = []
        self._validate_design_match()

    def find_script(self, name: str) -> dict | None:
        for script in self.scripts:
            if script.get("name") == name:
                return script
        return None

    def find_experiment_script(self, name: str) -> dict | None:
        """The centrally-held Experiment Script *name*, or None (the
        run_in_experiments bridge then falls back to each replicate's own)."""
        for script in self.experiment_scripts:
            if script.get("name") == name:
                return script
        return None

    # ------------------------------------------------------------------
    # Design-match validation (ADR-0005: hard-fail on factors/levels)
    # ------------------------------------------------------------------

    def _global(self, name: str) -> dict:
        return (self.configs[name].get("global") or {})

    def _validate_design_match(self) -> None:
        """Two modes (ADR-0005 + amendment): with a ``design:`` section the
        project.yaml is the AUTHORITY — every replicate's resolved values must
        match it (and counting-region names must match in order; aliases stay
        free). Without one (legacy), replicates must agree with each other on
        type, tracking type, and factors/levels."""
        design_global = dict(self.design.get("global") or {})

        def type_of(name):
            return experiment_types.get_experiment_type(
                self._global(name).get("experiment_type"))

        if self.design:
            self.experiment_type = experiment_types.get_experiment_type(
                design_global.get("experiment_type"))
            ref_factors = dict(design_global.get(
                "experimental_design_factors") or {})
        else:
            first = self.experiment_names[0]
            self.experiment_type = type_of(first)
            ref_factors = dict(self._global(first).get(
                "experimental_design_factors") or {})
        self.design_factors = {str(k): [str(l) for l in (v or [])]
                               for k, v in ref_factors.items()}
        self.tracking_type_name = self.experiment_type.resolve_tracking_type(
            design_global if self.design
            else (self._global(self.experiment_names[0])
                  if self.experiment_names else {})).name

        problems: list[str] = []
        if self.design:
            problems += self._validate_against_design(design_global)
        else:
            problems += self._validate_agreement(ref_factors)
        if problems:
            raise ValueError(
                f"Project '{self.name}': replicates do not match the "
                f"project design ({len(problems)} problem(s)):\n  - "
                + "\n  - ".join(problems))

        # Non-fatal differences worth surfacing (keys the design leaves free).
        def spread(getter, label):
            values = {}
            for name in self.experiment_names:
                values.setdefault(repr(getter(name)), []).append(name)
            if len(values) > 1:
                detail = "; ".join(f"{v}: {', '.join(ns)}"
                                   for v, ns in values.items())
                self.warnings.append(f"{label} differs across replicates "
                                     f"({detail})")

        t = self.experiment_type
        if self.experiment_names:
            for key, getter in (
                ("facet_cutoffs",
                 lambda n: t.resolve_facet_cutoffs(self._global(n))),
                ("min_transitions",
                 lambda n: t.resolve_min_transitions(self._global(n))),
                ("min_movement",
                 lambda n: t.resolve_min_movement(self._global(n))),
            ):
                if key not in design_global:
                    spread(getter, key)
            spread(lambda n: self._global(n).get("tracking_rig"),
                   "tracking_rig")

    #: How a replicate's value for an enforced design key is resolved before
    #: comparison — type-aware, so a config that *omits* a key the type
    #: defaults (e.g. min_transitions) still matches a design stating the
    #: default.
    _RESOLVERS = {
        "experiment_type": lambda t, g: t.name,
        "tracking_type": lambda t, g: t.resolve_tracking_type(g).name,
        "facet_cutoffs": lambda t, g: list(t.resolve_facet_cutoffs(g) or []),
        "min_transitions": lambda t, g: t.resolve_min_transitions(g),
        "min_movement": lambda t, g: t.resolve_min_movement(g),
        "facet_labels": lambda t, g: list(g.get("facet_labels")
                                          or t.phase_labels or []),
    }

    def _validate_against_design(self, design_global: dict) -> list[str]:
        problems: list[str] = []
        expected_type = self.experiment_type
        counting_names = [str(n) for n in
                          (self.design.get("counting_regions") or [])]
        for name in self.experiment_names:
            g = self._global(name)
            t = experiment_types.get_experiment_type(g.get("experiment_type"))
            for key, expected in design_global.items():
                resolver = self._RESOLVERS.get(key)
                if key == "experiment_type":
                    actual = t.name
                    expected_cmp = expected_type.name
                elif key == "experimental_design_factors":
                    factors = g.get("experimental_design_factors") or {}
                    for factor, levels in (expected or {}).items():
                        theirs = sorted(str(l) for l in
                                        (factors.get(factor) or []))
                        ours = sorted(str(l) for l in (levels or []))
                        if theirs != ours:
                            problems.append(
                                f"{name}: factor '{factor}' has levels "
                                f"{theirs} but the project design requires "
                                f"{ours}")
                    extra = set(factors) - set(expected or {})
                    if extra:
                        problems.append(
                            f"{name}: factors {sorted(extra)} are not in the "
                            f"project design")
                    continue
                elif resolver is not None:
                    actual = resolver(t, g)
                    expected_cmp = expected
                else:
                    actual = g.get(key)
                    expected_cmp = expected
                if _normalize(actual) != _normalize(expected_cmp):
                    problems.append(
                        f"{name}: {key} is {actual!r} but the project design "
                        f"requires {expected_cmp!r}")
            if counting_names:
                have = [str(k) for k in
                        (self.configs[name].get("counting_regions") or {})]
                if have != counting_names:
                    problems.append(
                        f"{name}: counting_regions are {have} but the project "
                        f"design requires {counting_names} (in that order; "
                        f"aliases are experiment-specific)")
        return problems

    def _validate_agreement(self, ref_factors: dict) -> list[str]:
        """Legacy mode (no design section): replicates must agree with the
        first replicate."""
        problems: list[str] = []
        ref_tt = self.tracking_type_name
        for name in self.experiment_names[1:]:
            t = experiment_types.get_experiment_type(
                self._global(name).get("experiment_type"))
            if t.name != self.experiment_type.name:
                problems.append(
                    f"{name}: experiment_type is '{t.name}' but the project "
                    f"uses '{self.experiment_type.name}'")
                continue
            tt = t.resolve_tracking_type(self._global(name)).name
            if tt != ref_tt:
                problems.append(
                    f"{name}: tracking_type is '{tt}' but the project uses "
                    f"'{ref_tt}'")
            factors = self._global(name).get(
                "experimental_design_factors") or {}
            if set(factors) != set(ref_factors):
                problems.append(
                    f"{name}: design factors {sorted(factors)} do not match "
                    f"the project's {sorted(ref_factors)}")
                continue
            for factor, levels in ref_factors.items():
                theirs = [str(l) for l in (factors.get(factor) or [])]
                ours = [str(l) for l in (levels or [])]
                if sorted(theirs) != sorted(ours):
                    problems.append(
                        f"{name}: factor '{factor}' has levels {theirs} but "
                        f"the project uses {ours}")
        return problems

    def scaffold_replicate_config(self) -> dict:
        """A tracking_config.yaml for a new replicate: a copy of the first
        replicate's config when one exists (design-conformant by validation),
        else built from the project design (rig and region assignments left
        for the user)."""
        import copy

        if self.experiment_names:
            return copy.deepcopy(self.configs[self.experiment_names[0]])
        g = dict(self.design.get("global") or {})
        cfg = self.experiment_type.build_config(
            facet_cutoffs=g.get("facet_cutoffs"),
            facet_labels=g.get("facet_labels"),
            factors=g.get("experimental_design_factors"),
            min_transitions=g.get("min_transitions"),
            min_movement=g.get("min_movement"),
        )
        counting_names = [str(n) for n in
                          (self.design.get("counting_regions") or [])]
        if counting_names:
            existing = cfg.get("counting_regions") or {}
            cfg["counting_regions"] = {
                n: dict(existing.get(n) or {"alias": ""})
                for n in counting_names}
        return cfg

    def unconfigured_dirs(self) -> list[str]:
        """Immediate subdirectories that hold a recording but are not
        Experiments yet — experiment-shaped folders (a ``data/`` directory
        with at least one ``.xlsx``, see :func:`has_experiment_data`) with no
        ``tracking_config.yaml``.

        Membership is by config file, so such a directory is invisible to
        :attr:`experiment_names` until it has one; these are the candidates
        :meth:`scaffold_replicate` gives a config to. Every other
        subdirectory (project outputs, caches, unrelated folders) is ignored
        — the data criterion is the whole test, no denylist.
        """
        pending: list[str] = []
        for entry in sorted(os.listdir(self.project_directory)):
            sub = os.path.join(self.project_directory, entry)
            if not os.path.isdir(sub) or is_experiment_dir(sub):
                continue
            if has_experiment_data(sub):
                pending.append(entry)
        return pending

    def scaffold_replicate(self, name: str) -> str:
        """Give replicate *name* a design-conformant ``tracking_config.yaml``
        and return its path.

        Creates the directory and its ``data/`` folder when missing, so this
        serves both "add a new replicate" and "adopt a folder that was already
        sitting in the Project". Never overwrites an existing config — a
        replicate's region assignments are hand-made.
        """
        directory = self.experiment_dir(name)
        config_path = os.path.join(directory, CONFIG_FILENAME)
        if os.path.isfile(config_path):
            raise FileExistsError(f"'{name}' already has a {CONFIG_FILENAME}")
        os.makedirs(os.path.join(directory, "data"), exist_ok=True)
        config = self.scaffold_replicate_config()
        atomic_write_text(
            config_path,
            lambda handle: yaml.safe_dump(config, handle, sort_keys=False,
                                          allow_unicode=True))
        return config_path

    # ------------------------------------------------------------------
    # Replicate access / status
    # ------------------------------------------------------------------

    def experiment_dir(self, name: str) -> str:
        return os.path.join(self.project_directory, name)

    def load_experiment(self, name: str):
        from .Experiment import Experiment
        return Experiment(self.experiment_dir(name))

    def _summary_csv(self, name: str, suffix: str = "_Summary.csv") -> str | None:
        """Path of a replicate's saved summary artifact, or None. The
        recording name (xlsx basename) need not match the directory name, so
        the file is found by suffix."""
        pattern = os.path.join(self.experiment_dir(name), "analysis",
                               f"*{suffix}")
        matches = glob.glob(pattern)
        if suffix == "_Summary.csv":
            matches = [p for p in matches
                       if not p.endswith("_Summary_Facet.csv")]
        return sorted(matches)[0] if matches else None

    def experiment_status(self, name: str) -> dict:
        """Cheap per-replicate status from saved artifacts (no data load)."""
        status = {"analyzed": False, "report": False, "flies": None,
                  "excluded": None, "flagged": None,
                  "has_data": has_experiment_data(self.experiment_dir(name))}
        path = self._summary_csv(name)
        if path:
            status["analyzed"] = True
            try:
                df = pd.read_csv(path)
                status["flies"] = len(df)
                if "LowMovementFlag" in df.columns:
                    status["flagged"] = int(
                        df["LowMovementFlag"].fillna(False).astype(bool).sum())
            except Exception:  # noqa: BLE001
                pass
        excl = self._summary_csv(name, "_Excluded.csv")
        if excl:
            try:
                status["excluded"] = len(pd.read_csv(excl))
            except Exception:  # noqa: BLE001
                pass
        report = os.path.join(self.experiment_dir(name),
                              f"{name}_report.pdf")
        status["report"] = os.path.isfile(report)
        return status

    def run_all(self, qc_cutoff: float = 0.9, make_reports: bool = True,
                skip_analyzed: bool = False, log=print) -> list[str]:
        """Run each replicate's full analysis (and report); returns failures."""
        failures: list[str] = []
        for name in self.experiment_names:
            if skip_analyzed and self.experiment_status(name)["analyzed"]:
                log(f"[{name}] already analyzed — skipped")
                continue
            log(f"[{name}] running analysis…")
            try:
                exp = self.load_experiment(name)
                exp.run_analysis(qc_cutoff=qc_cutoff)
                if make_reports:
                    exp.create_report(qc_cutoff=qc_cutoff)
            except Exception as err:  # noqa: BLE001
                failures.append(f"{name}: {err}")
                log(f"[{name}] FAILED: {err}")
        return failures

    # ------------------------------------------------------------------
    # Combined Analysis
    # ------------------------------------------------------------------

    def combined_frames(self):
        """The stacked, filtered replicate summaries.

        Returns ``(summary, facet, excluded, missing)`` — each frame carries an
        ``Experiment`` first column; ``missing`` lists replicates without a
        saved summary (they are omitted, never silently analyzed).
        """
        summaries, facets, excludeds, missing = [], [], [], []
        for name in self.experiment_names:
            path = self._summary_csv(name)
            if path is None:
                missing.append(name)
                continue
            df = pd.read_csv(path)
            df.insert(0, "Experiment", name)
            summaries.append(df)
            fpath = self._summary_csv(name, "_Summary_Facet.csv")
            if fpath:
                fdf = pd.read_csv(fpath)
                fdf.insert(0, "Experiment", name)
                facets.append(fdf)
            epath = self._summary_csv(name, "_Excluded.csv")
            if epath:
                try:
                    edf = pd.read_csv(epath)
                    if len(edf):
                        edf.insert(0, "Experiment", name)
                        excludeds.append(edf)
                except Exception:  # noqa: BLE001
                    pass
        summary = pd.concat(summaries, ignore_index=True) if summaries else None
        facet = pd.concat(facets, ignore_index=True) if facets else None
        excluded = (pd.concat(excludeds, ignore_index=True) if excludeds
                    else pd.DataFrame())
        return summary, facet, excluded, missing

    def build_combined_analysis(self) -> dict:
        """Write the Combined Analysis into ``<project>/analysis/`` and return
        ``{written: [...], missing: [...]}``. Raises when nothing is built."""
        summary, facet, excluded, missing = self.combined_frames()
        if summary is None:
            raise ValueError(
                f"No replicate has a saved analysis yet "
                f"(missing: {', '.join(missing)}). Run the experiments first.")
        os.makedirs(self.analysis_path, exist_ok=True)
        written = []
        path = os.path.join(self.analysis_path, f"{self.name}_Summary.csv")
        summary.to_csv(path, index=False, na_rep="NA")
        written.append(path)
        if facet is not None:
            path = os.path.join(self.analysis_path,
                                f"{self.name}_Summary_Facet.csv")
            facet.to_csv(path, index=False, na_rep="NA")
            written.append(path)
        path = os.path.join(self.analysis_path, f"{self.name}_Excluded.csv")
        excluded.to_csv(path, index=False, na_rep="NA")
        written.append(path)
        stats_text = self.stats_text(summary, facet)
        path = os.path.join(self.analysis_path, f"{self.name}_Stats.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(stats_text)
        written.append(path)
        ## The AI narrative is a derivative of one Combined Analysis; a stale
        ## one must not sit beside fresh numbers (mirrors run_analysis).
        self.delete_ai_summary()
        return {"written": written, "missing": missing}

    # ------------------------------------------------------------------
    # Phases / windows shared across replicates
    # ------------------------------------------------------------------

    def shared_windows(self):
        """``(windows, labels)`` when every replicate resolves the same facet
        cutoffs, else ``(None, None)``."""
        cutoffs = {tuple(self.experiment_type.resolve_facet_cutoffs(
            self._global(n)) or ()) for n in self.experiment_names}
        if len(cutoffs) != 1:
            return None, None
        only = next(iter(cutoffs))
        if not only:
            return None, None
        windows = list(windowing.facet_windows(only))
        labels = self.experiment_type.phase_labels_for(
            windows, self._global(self.experiment_names[0]))
        return windows, labels

    @staticmethod
    def parse_window(value) -> tuple:
        """A FacetRange CSV cell ("(10, 70)" / "(70, inf)") back to a tuple."""
        if isinstance(value, tuple):
            return value
        inner = str(value).strip().strip("()")
        lo, _, hi = inner.partition(",")
        return (float(lo), float(hi))

    def window_labels(self, facet: pd.DataFrame) -> tuple[list, dict]:
        """Ordered windows present in *facet* and their display labels."""
        windows: list[tuple] = []
        for raw in facet["FacetRange"]:
            w = self.parse_window(raw)
            if w not in windows:
                windows.append(w)
        shared, labels = self.shared_windows()
        if shared is not None and [tuple(w) for w in shared] == windows:
            label_of = dict(zip(windows, labels))
        else:
            label_of = {w: self.experiment_type._minute_label(w)
                        for w in windows}
        return windows, label_of

    # ------------------------------------------------------------------
    # Statistics: pooled per-fly tests + mixed-model companion
    # ------------------------------------------------------------------

    def _metrics(self) -> list[str]:
        from .Experiment import _TRACKING_TYPE_METRICS
        from . import Parameters
        tt = Parameters.TrackingType[self.tracking_type_name]
        return list(_TRACKING_TYPE_METRICS.get(tt) or []) or ["FinalPI"]

    def comparison_rows(self, summary: pd.DataFrame,
                        facet: pd.DataFrame | None) -> list[dict]:
        """One row per metric × phase × treatment pair: pooled Welch/Tukey p
        beside the mixed-model (experiment random intercept) p."""
        import itertools

        import numpy as np
        from scipy import stats as sstats

        frames: list[tuple[str, pd.DataFrame]] = []
        if facet is not None and "FacetRange" in facet.columns:
            windows, label_of = self.window_labels(facet)
            for w in windows:
                mask = facet["FacetRange"].map(self.parse_window) == w
                frames.append((label_of[w], facet[mask]))
        else:
            frames.append(("Whole recording", summary))

        n_experiments = summary["Experiment"].nunique() \
            if "Experiment" in summary.columns else 1
        rows: list[dict] = []
        for metric in self._metrics():
            for label, frame in frames:
                if metric not in frame.columns:
                    continue
                value = pd.to_numeric(frame[metric], errors="coerce")
                data = pd.DataFrame({
                    "Treatment": frame["Treatment"].astype(str).str.strip(),
                    "Experiment": frame.get("Experiment", "one"),
                    "Value": value,
                }).dropna(subset=["Value"])
                data = data[data["Treatment"] != ""]
                groups = {t: g["Value"].values
                          for t, g in data.groupby("Treatment", sort=False)
                          if len(g) >= 2}
                if len(groups) < 2:
                    continue
                try:
                    if len(groups) == 2:
                        (na, va), (nb, vb) = groups.items()
                        _s, p = sstats.ttest_ind(va, vb, equal_var=False)
                        pairs = [(na, nb, float(np.mean(vb) - np.mean(va)),
                                  float(p))]
                    else:
                        from statsmodels.stats.multicomp import pairwise_tukeyhsd
                        endog = np.concatenate(list(groups.values()))
                        glabels = np.concatenate(
                            [[t] * len(v) for t, v in groups.items()])
                        res = pairwise_tukeyhsd(endog=endog, groups=glabels,
                                                alpha=0.05)
                        pairs = [(str(a), str(b), float(d), float(p))
                                 for (a, b), d, p in zip(
                                     itertools.combinations(res.groupsunique, 2),
                                     res.meandiffs, res.pvalues)]
                except Exception:  # noqa: BLE001
                    continue
                for a, b, diff, p_pooled in pairs:
                    p_mixed = self._mixed_p(data, a, b) \
                        if n_experiments > 1 else None
                    rows.append({
                        "metric": metric, "phase": label,
                        "a": a, "n_a": len(groups[a]),
                        "b": b, "n_b": len(groups[b]),
                        "diff": diff, "p_pooled": p_pooled,
                        "significant": bool(p_pooled < 0.05),
                        "p_mixed": p_mixed,
                    })
        return rows

    @staticmethod
    def _mixed_p(data: pd.DataFrame, a: str, b: str) -> float | None:
        """Treatment p-value from a linear mixed model on the (a, b) subset:
        Value ~ Treatment with a per-Experiment random intercept."""
        try:
            import warnings

            import statsmodels.formula.api as smf
            sub = data[data["Treatment"].isin([a, b])].copy()
            if sub["Experiment"].nunique() < 2:
                return None
            sub["is_b"] = (sub["Treatment"] == b).astype(float)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = smf.mixedlm("Value ~ is_b", sub,
                                    groups=sub["Experiment"])
                fit = model.fit(reml=True, method="lbfgs")
            return float(fit.pvalues["is_b"])
        except Exception:  # noqa: BLE001
            return None

    def stats_text(self, summary: pd.DataFrame,
                   facet: pd.DataFrame | None) -> str:
        rows = self.comparison_rows(summary, facet)
        bar = "=" * 72
        lines = [bar, f"Project statistics — {self.name}",
                 f"Experiment type : {self.experiment_type.display_name}",
                 f"Replicates      : {len(self.experiment_names)} "
                 f"({', '.join(self.experiment_names)})",
                 f"Flies (pooled)  : {len(summary)}",
                 "",
                 "Pooled p: Welch's t-test (two levels) / Tukey HSD (more) on",
                 "all flies pooled across replicates — matches the plots.",
                 "Mixed p: linear mixed model per pair (treatment fixed,",
                 "experiment random intercept) — accounts for between-",
                 "replicate variation. Disagreement between the two indicates",
                 "a batch effect; consult the per-replicate panels.",
                 bar, ""]
        for warning in self.warnings:
            lines.append(f"Note: {warning}")
        if self.warnings:
            lines.append("")
        header = (f"{'Metric':<20} {'Phase':<14} {'A':<18} {'B':<18} "
                  f"{'diff':>8} {'pooled p':>10} {'mixed p':>10}")
        lines += [header, "-" * len(header)]
        for r in rows:
            mixed = f"{r['p_mixed']:.4g}" if r["p_mixed"] is not None else "—"
            a = f"{r['a']} (n={r['n_a']})"
            b = f"{r['b']} (n={r['n_b']})"
            lines.append(
                f"{r['metric']:<20} {r['phase']:<14} {a:<18} {b:<18} "
                f"{r['diff']:>+8.3f} {r['p_pooled']:>10.4g} {mixed:>10}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # AI narrative (same contract as the per-experiment AI Summary)
    # ------------------------------------------------------------------

    _AI_SUMMARY_MARKER = "[AI Summary] "

    def _ai_summary_path(self) -> str:
        return os.path.join(self.analysis_path, f"{self.name}_AI_Summary.txt")

    def read_ai_summary(self):
        try:
            with open(self._ai_summary_path(), encoding="utf-8") as handle:
                text = handle.read().strip()
        except OSError:
            return None
        if not text:
            return None
        first, _, rest = text.partition("\n")
        if first.startswith(self._AI_SUMMARY_MARKER):
            return first[len(self._AI_SUMMARY_MARKER):].strip(), rest.strip()
        return None, text

    def write_ai_summary(self, text: str, provider: str, model: str) -> str:
        from datetime import datetime as _dt
        stamp = _dt.now().strftime("%Y-%m-%d %H:%M")
        path = self._ai_summary_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"{self._AI_SUMMARY_MARKER}{provider} {model}, "
                         f"{stamp}\n\n{text.strip()}\n")
        return path

    def delete_ai_summary(self) -> None:
        try:
            os.remove(self._ai_summary_path())
        except FileNotFoundError:
            pass

    def ai_prompt(self) -> str:
        return self.experiment_type.ai_summary_prompt() + (
            "\n\nProject context: this is a PROJECT-level report combining "
            f"{len(self.experiment_names)} replicate experiments of the same "
            "design; flies are pooled by treatment across replicates. The "
            "statistics table shows both pooled per-fly tests and a linear "
            "mixed model whose p-values account for between-replicate "
            "variation — comment on their agreement or disagreement, and on "
            "consistency across the replicates table.")

    def generate_ai_summary(self, provider: str, model: str | None = None) -> str:
        from .ai import build_payload, get_summarizer
        summarizer = get_summarizer(provider, model=model)
        payload = build_payload(self)
        text = summarizer.summarize(payload, self.ai_prompt())
        self.write_ai_summary(text, summarizer.display_name, summarizer.model)
        return text

    def render_figures(self, formats=("svg",)) -> list[str]:
        """Write the pooled publication figures to ``figures/`` straight from
        ``plot_specs.yaml`` — the headless equivalent of the Plot Editor's
        save buttons. Returns the written paths."""
        from . import pubfigures as pf

        _summary, facet, _excluded, missing = self.combined_frames()
        if facet is None:
            raise ValueError(
                "No replicate has a saved analysis yet — run the experiments "
                f"first (missing: {', '.join(missing)}).")
        windows, label_of = self.window_labels(facet)
        specs = pf.load_project_specs(self.project_directory)
        region1 = next(iter((self.design.get("counting_regions") or [])), None) \
            or (next(iter(self.configs[self.experiment_names[0]]
                          .get("counting_regions") or {}), "region 1")
                if self.experiment_names else "region 1")
        out_dir = os.path.join(self.project_directory, pf.FIGURES_DIRNAME)
        written: list[str] = []
        for plot_id, info in pf.PLOT_TYPES.items():
            if info["metric"] not in facet.columns:
                continue
            spec = specs.plots.get(plot_id) or pf.default_spec(plot_id, region1)
            style = specs.style_for(spec)
            df = pf.faceted_data_from_combined(
                facet, info["metric"], [label_of[w] for w in windows],
                lambda v: label_of[self.parse_window(v)])
            g = pf.build_ggplot(df, spec, style)
            for fmt in formats:
                path = os.path.join(out_dir, f"{plot_id}.{fmt}")
                pf.save_ggplot(g, path, style)
                written.append(path)
        return written

    # ------------------------------------------------------------------
    # Project Report
    # ------------------------------------------------------------------

    def _pub_figure_blocks(self, facet: pd.DataFrame | None, _m) -> list:
        """The pooled publication figures as report blocks, rendered by the
        same Spec/Style system the Plot Editor saves (ADR-0005)."""
        import io

        from PIL import Image

        from . import pubfigures as pf

        if facet is None:
            return []
        windows, label_of = self.window_labels(facet)
        specs = pf.load_project_specs(self.project_directory)
        region1 = next(iter(self.configs[self.experiment_names[0]]
                            .get("counting_regions") or {}), "region 1")
        blocks = []
        for plot_id, info in pf.PLOT_TYPES.items():
            if info["metric"] not in facet.columns:
                continue
            spec = specs.plots.get(plot_id) or pf.default_spec(plot_id, region1)
            style = specs.style_for(spec)
            try:
                df = pf.faceted_data_from_combined(
                    facet, info["metric"],
                    [label_of[w] for w in windows],
                    lambda v: label_of[self.parse_window(v)])
                g = pf.build_ggplot(df, spec, style)
                png = pf.render_png_bytes(g, style, dpi=200)
                w, h = Image.open(io.BytesIO(png)).size
                blocks.append(_m.Figure(
                    data=png, fmt="png", width_in=w / 200, height_in=h / 200,
                    title=info["display"],
                    caption=f"All flies pooled across "
                            f"{len(self.experiment_names)} replicates; "
                            "styled by the project's plot_specs.yaml."))
            except Exception:  # noqa: BLE001
                continue
        return blocks

    def build_report_model(self, qc_cutoff: float = 0.9,
                           include_ai_summary: bool = True):
        from .report import Report
        from .report import model as _m

        summary, facet, excluded, missing = self.combined_frames()
        if summary is None:
            raise ValueError(
                "No replicate has a saved analysis yet — run the experiments "
                f"first (missing: {', '.join(missing)}).")

        report = Report(self.name)
        factors = ";  ".join(f"{k}: {', '.join(v)}"
                             for k, v in self.design_factors.items()) or "—"
        metadata = [
            ("Experiment type", self.experiment_type.display_name),
            ("Design factors", factors),
            ("Replicates", f"{summary['Experiment'].nunique()} "
                           f"({', '.join(sorted(summary['Experiment'].unique()))})"),
            ("Flies (pooled)", str(len(summary))),
            ("Project", self.project_directory),
        ]
        status: list = []
        if missing:
            status.append(_m.StatusLine(
                f"{len(missing)} replicate(s) not analyzed: "
                f"{', '.join(missing)}", _m.Level.ERROR))
        if "LowMovementFlag" in summary.columns:
            per_exp = summary.groupby("Experiment")["LowMovementFlag"].agg(
                ["sum", "count"])
            bad = [str(n) for n, row in per_exp.iterrows()
                   if row["count"] and row["sum"] / row["count"] > 0.5]
            if bad:
                status.append(_m.StatusLine(
                    f"Potential issue: >50% low-movement flies in "
                    f"{', '.join(bad)}", _m.Level.ERROR))
            else:
                status.append(_m.StatusLine(
                    f"Low movement: {int(per_exp['sum'].sum())}/"
                    f"{int(per_exp['count'].sum())} pooled flies flagged",
                    _m.Level.WARN if per_exp["sum"].sum() else _m.Level.OK))
        report.add(_m.Cover(self.name, "Project Report", metadata=metadata,
                            status=status or None))

        if self.notes:
            report.add(_m.Heading("Notes", level=2))
            report.add(_m.Paragraph(self.notes))

        if include_ai_summary:
            saved = self.read_ai_summary()
            if saved:
                provenance, body = saved
                report.add(_m.SectionDivider("AI Narrative"))
                if provenance:
                    report.add(_m.Paragraph(f"Generated by {provenance}. The "
                                            "narrative summarizes the "
                                            "pipeline's numbers; it performs "
                                            "no analysis of its own."))
                for para in body.split("\n\n"):
                    if para.strip():
                        report.add(_m.Paragraph(para.strip()))

        report.add(_m.SectionDivider("Combined Analysis"))
        intro = self.experiment_type.report_intro()
        if intro:
            report.add(_m.Paragraph(intro))
        report.add(_m.Paragraph(
            f"Flies from {summary['Experiment'].nunique()} replicate "
            "experiments are pooled by treatment. Every replicate shares the "
            "design factors exactly (validated at load); each replicate's "
            "exclusions and flags were applied before pooling."))
        for warning in self.warnings:
            report.add(_m.Paragraph(f"Note: {warning}"))

        for block in self._pub_figure_blocks(facet, _m):
            report.add(block)

        rows, levels = [], []
        for r in self.comparison_rows(summary, facet):
            mixed = f"{r['p_mixed']:.4g}" if r["p_mixed"] is not None else "—"
            rows.append([r["metric"], r["phase"],
                         f"{r['a']} (n={r['n_a']})",
                         f"{r['b']} (n={r['n_b']})",
                         f"{r['diff']:+.3f}", f"{r['p_pooled']:.4g}", mixed])
            levels.append(_m.Level.OK if r["significant"] else None)
        if rows:
            report.add(_m.Table(
                columns=["Metric", "Phase", "Group A", "Group B",
                         "Mean diff (B − A)", "Pooled p", "Mixed p"],
                rows=rows, row_levels=levels,
                title="Statistical comparisons (pooled + mixed model)",
                caption="Pooled p: Welch/Tukey on all flies (matches the "
                        "figures). Mixed p: linear mixed model per pair with "
                        "a per-experiment random intercept. α = 0.05 on the "
                        "pooled test; no multiplicity correction. Full text "
                        "in the _Stats.txt output."))

        report.add(_m.SectionDivider("Replicates"))
        rep_rows, rep_levels = [], []
        windows, label_of = (self.window_labels(facet) if facet is not None
                             else ([], {}))
        primary = windows[1] if len(windows) >= 2 else \
            (windows[0] if windows else None)
        for name in self.experiment_names:
            st = self.experiment_status(name)
            headline = ""
            if facet is not None and primary is not None \
                    and "FinalPI" in facet.columns:
                sub = facet[(facet["Experiment"] == name)
                            & (facet["FacetRange"].map(self.parse_window)
                               == primary)]
                parts = []
                for treat, g in sub.groupby(
                        sub["Treatment"].astype(str).str.strip(), sort=False):
                    vals = pd.to_numeric(g["FinalPI"], errors="coerce").dropna()
                    if len(vals):
                        parts.append(f"{treat} {vals.mean():+.2f}")
                headline = ";  ".join(parts)
            flagged = st["flagged"]
            flies = st["flies"] or 0
            rep_rows.append([
                name,
                str(flies) if st["analyzed"] else "not analyzed",
                str(st["excluded"]) if st["excluded"] is not None else "0",
                str(flagged) if flagged is not None else "—",
                headline or "—",
                "yes" if st["report"] else "no",
            ])
            level = None
            if not st["analyzed"]:
                level = _m.Level.ERROR
            elif flagged is not None and flies and flagged / flies > 0.5:
                level = _m.Level.WARN
            rep_levels.append(level)
        report.add(_m.Table(
            columns=["Experiment", "Flies", "Excluded", "Low-movement",
                     f"PI ({label_of.get(primary, 'primary')})" if primary
                     else "PI", "Report"],
            rows=rep_rows, row_levels=rep_levels,
            title="Per-replicate summary",
            caption="Flies counted after each replicate's own exclusion; "
                    "amber rows have >50% low-movement flies; each replicate "
                    "has its own full report in its directory."))
        return report

    def create_report(self, backend: str = "reportlab",
                      qc_cutoff: float = 0.9) -> str:
        from .report import render as _render
        model = self.build_report_model(qc_cutoff=qc_cutoff)
        ext = {"reportlab": "pdf"}.get(backend, "pdf")
        out_path = os.path.join(self.project_directory,
                                f"{self.name}_report.{ext}")
        _render(model, out_path, backend=backend)
        print(f"Saved: {out_path}")
        return out_path
