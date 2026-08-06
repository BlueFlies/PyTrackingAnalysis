import glob
import io
import logging
import os
import sys
import time
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import pandas as pd
import yaml
from . import Parameters
from . import Arena
from . import config_validation
from . import experiment_types
from . import io_utils

## The rig spellings the config accepts. config_validation owns this table so
## that the checker and the loader can never disagree about which rigs exist —
## Arena used to carry a third copy behind a dead code path.
_RIG_MAP = config_validation.RIG_ALIASES

## global: keys that are forwarded to Parameters.set() as explicit overrides.
_PARAMETER_KEYS = {
    'fps', 'mm_per_pixel', 'speed_window_seconds',
    'micromove_speed_mm_sec', 'walking_speed_mm_sec',
    'sleep_threshold_min', 'interaction_distances',
}

logger = logging.getLogger(__name__)

# Maps TrackingType to the plot methods (and kwargs) that are relevant for it
_TRACKING_TYPE_PLOTS = {
    Parameters.TrackingType.TRACKER: [
        ('plot_totaldistance_facet', {}),
    ],
    ## Both are plain tracking-class types whose trackers produce the standard
    ## Tracker summary, so they get the generic distance policy. Leaving them out
    ## of these tables made run_analysis emit a zero-byte Stats.txt and no plots
    ## while still printing "=== Done. ===" and recording 'ok' in batch mode.
    Parameters.TrackingType.DDROPTRACKER: [
        ('plot_totaldistance_facet', {}),
    ],
    Parameters.TrackingType.CENTROPHOBISMTRACKER: [
        ('plot_totaldistance_facet', {}),
    ],
    Parameters.TrackingType.TWOCHOICETRACKER: [
        ('plot_pi_facet', {}),
        ('plot_percentage_facet', {}),
        ('plot_transitions_facet', {}),
        ('plot_totaldistance_facet', {}),
    ],
    Parameters.TrackingType.TWOCHOICECOUNTER: [
        ('plot_pi_facet', {}),
        ('plot_percentage_facet', {}),
    ],
    Parameters.TrackingType.XCHOICETRACKER: [
        ('plot_adjusted_x_position_facet', {}),
        ('plot_totaldistance_facet', {}),
    ],
    Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER: [
        ('plot_interactions_facet', {}),
        ('plot_totaldistance_facet', {}),
    ],
    Parameters.TrackingType.PAIRWISEINTERACTIONCOUNTER: [
        ('plot_interactions_facet', {}),
    ],
}

# Maps TrackingType to the metrics used in run_pairwise_comparisons_facet
_TRACKING_TYPE_METRICS = {
    Parameters.TrackingType.TRACKER:                   ['TotalDistancePerMin'],
    Parameters.TrackingType.DDROPTRACKER:              ['TotalDistancePerMin'],
    Parameters.TrackingType.CENTROPHOBISMTRACKER:      ['TotalDistancePerMin'],
    Parameters.TrackingType.TWOCHOICETRACKER:          ['FinalPI', 'FinalPercentage', 'TotalDistancePerMin'],
    Parameters.TrackingType.TWOCHOICECOUNTER:          ['FinalPI', 'FinalPercentage'],
    Parameters.TrackingType.XCHOICETRACKER:            ['AvgAdjX_mm', 'TotalDistancePerMin'],
    Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER: None,   # built at runtime from interaction distances
    Parameters.TrackingType.PAIRWISEINTERACTIONCOUNTER: None,
    ## A plain COUNTER summary carries no outcome metric — only Treatment, Name,
    ## TrackingRegion and the observed-minutes bounds — so there is genuinely
    ## nothing to compare. Listed explicitly so it reads as a decision rather
    ## than an omission; stats() says so out loud instead of writing an empty file.
    Parameters.TrackingType.COUNTER:                   [],
}


class Experiment:
    """
    Primary organizer for a tracking experiment.

    Reads ``tracking_config.yaml`` from the project directory to configure
    Parameters, then loads data from the ``data/`` subdirectory via Arena.
    Analysis outputs go to ``analysis/`` and QC outputs to ``qc/``.

    Directory layout expected::

        project_directory/
            tracking_config.yaml    ← experiment configuration
            data/                   ← input xlsx + csv files  (must already exist)
            analysis/               ← created automatically on load
            qc/                     ← created automatically on load

    Typical usage::

        exp = Experiment('/path/to/project')
        exp.experiment_summary()
        exp.qc()
        exp.run_analysis()          # QC + summaries + plots + stats in one call

    All Arena methods are accessible directly on the Experiment object via
    attribute delegation, so ``exp.summarize()`` is the same as
    ``exp.arena.summarize()``.

    YAML global section keys recognised
    ------------------------------------
    tracking_type   : TrackingType enum name (e.g. ``TWOCHOICETRACKER``)
    tracking_rig    : Rig preset name (small_arena, arena_max, colosseum, obscura, movie)
    facet_cutoffs   : Optional list of minute boundaries for faceted analysis, e.g. [10, 70]
    fps             : Override fps after rig preset is applied
    mm_per_pixel    : Override mm_per_pixel after rig preset is applied
    speed_window_seconds, micromove_speed_mm_sec, walking_speed_mm_sec,
    sleep_threshold_min, interaction_distances : other parameter overrides
    """

    def __init__(self, project_directory: str, force_preprocessing: bool = False,
                 config_path: str | None = None):
        """
        Parameters
        ----------
        project_directory :
            Root directory for the experiment. Must contain ``tracking_config.yaml``
            and a ``data/`` subdirectory with the experiment xlsx and csv files.
        force_preprocessing :
            Passed through to Arena; forces re-computation of nearest-neighbour
            pre-processing when True.
        config_path :
            Alternative config file to load instead of
            ``<project_directory>/tracking_config.yaml``. A relative path is
            resolved against *project_directory*. The Hub offers a config
            selector, and without this parameter the filename was joined on
            unconditionally, so choosing a second config silently loaded the
            *other* file's tracking type, rig calibration and cutoffs.
        """
        self.project_directory = os.path.abspath(project_directory)
        self.data_path     = self._find_subdir('data') + '/'
        self.analysis_path = os.path.join(self.project_directory, 'analysis') + '/'
        self.qc_path       = os.path.join(self.project_directory, 'qc') + '/'
        if config_path is None:
            self.config_path = os.path.join(self.project_directory, 'tracking_config.yaml')
        else:
            self.config_path = config_path if os.path.isabs(config_path) \
                else os.path.join(self.project_directory, config_path)

        # Create output directories (data/ must already exist with files in it)
        os.makedirs(self.analysis_path, exist_ok=True)
        os.makedirs(self.qc_path, exist_ok=True)

        self.config = self._load_config()
        ## The Experiment Type (absent -> Custom) owns the fixed fields and its
        ## own constraints. Resolve it before anything reads tracking_type or
        ## facets, so those come from the type for a typed experiment (ADR-0001).
        self.experiment_type = experiment_types.get_experiment_type(
            (self.config.get('global') or {}).get('experiment_type'))
        self._validate_config()
        self.parameters = self._build_parameters()

        ## Excel writes a '~$Name.xlsx' lock file next to any workbook that is
        ## currently open. Globbing unsorted and unfiltered picked it up, and the
        ## experiment died with "Excel file format cannot be determined" — for
        ## the entirely ordinary reason that the user had the sheet open.
        ## Sorting also makes the choice deterministic when several are present.
        xlsx_files = sorted(
            f for f in glob.glob(os.path.join(self.data_path, '*.xlsx'))
            if not os.path.basename(f).startswith(('~$', '.'))
        )
        if not xlsx_files:
            raise FileNotFoundError(f"No .xlsx file found in {self.data_path}")
        if len(xlsx_files) > 1:
            logger.warning(
                "Multiple .xlsx files in %s; using '%s'. Others: %s",
                self.data_path, os.path.basename(xlsx_files[0]),
                ", ".join(os.path.basename(f) for f in xlsx_files[1:]),
            )
        exp_name = os.path.splitext(os.path.basename(xlsx_files[0]))[0]

        self.arena = Arena.Arena(
            exp_name, self.data_path, self.parameters,
            config_path=self.config_path,
            force_preprocessing=force_preprocessing,
        )

        # Facet cutoffs: fixed by the Experiment Type for a typed experiment,
        # otherwise read from the global: section (Custom). e.g. [10, 70].
        self.facet_cutoffs: tuple | None = self.experiment_type.resolve_facet_cutoffs(
            self.config.get('global', {}))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_subdir(self, name: str) -> str:
        """Return the path of a subdirectory matching *name* (case-insensitive).

        Falls back to the lowercase name if no match exists (letting later code
        raise a clear error about missing files).
        """
        try:
            entries = os.listdir(self.project_directory)
        except OSError:
            return os.path.join(self.project_directory, name)
        for entry in entries:
            if entry.lower() == name.lower() and os.path.isdir(
                os.path.join(self.project_directory, entry)
            ):
                return os.path.join(self.project_directory, entry)
        return os.path.join(self.project_directory, name)

    def _load_config(self) -> dict:
        if not os.path.isfile(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _validate_config(self) -> None:
        """Validate the config through its Experiment Type.

        ``config_validation`` catches unknown rigs, missing movie calibration,
        bad multipliers, mis-ordered cutoffs, and (for a typed experiment) the
        type's own constraints. For a **typed** experiment we fail hard (ADR-0001)
        — a Valence config that names the wrong rig or omits Light/NoLight should
        stop at load, not crash mid-analysis or silently produce wrong numbers.
        A **Custom** experiment stays lenient (its previous behaviour): a config
        can be imperfect and still analysable, and refusing to load it would be a
        breaking change for existing projects.
        """
        problems = config_validation.validate_config(self.config)
        if not problems:
            return
        if not self.experiment_type.is_custom:
            raise ValueError(
                f"{self.experiment_type.display_name} configuration has "
                f"{len(problems)} problem(s) in {self.config_path}:\n  - "
                + "\n  - ".join(problems)
            )
        logger.warning("Problems in %s:", self.config_path)
        print(f"Warning: {len(problems)} problem(s) in {self.config_path}:")
        for problem in problems:
            logger.warning("  %s", problem)
            print(f"  - {problem}")

    def _build_parameters(self) -> Parameters.Parameters:
        """Create a Parameters object from the global: section of the yaml."""
        global_cfg = self.config.get('global', {})

        ## Tracking type comes from the Experiment Type: fixed for a typed
        ## experiment (the yaml does not carry it), read from the yaml for Custom.
        tracking_type = self.experiment_type.resolve_tracking_type(global_cfg)

        # Resolve rig and apply preset
        rig_raw = global_cfg.get('tracking_rig', '').lower().replace(' ', '_').replace('-', '_')
        rig = _RIG_MAP.get(rig_raw, rig_raw)

        p = Parameters.Parameters()
        if rig == 'small_arena':
            p.set_small_arena_values(tracking_type)
        elif rig == 'arena_max':
            p.set_arena_max_values(tracking_type)
        elif rig in ('colosseum', 'colloseum'):
            p.set_colloseum_values(tracking_type)
        elif rig == 'obscura':
            p.set_obscura_values(tracking_type)
        elif rig == 'movie':
            ## A movie has no rig preset to fall back on. Guessing 30 fps / 0.1 mm
            ## per pixel would silently rescale every time and distance in the
            ## experiment, so require the real calibration instead.
            missing = [k for k in ('fps', 'mm_per_pixel') if global_cfg.get(k) is None]
            if missing:
                raise ValueError(
                    "tracking_rig 'movie' requires explicit calibration in the global: "
                    f"section of tracking_config.yaml. Missing: {', '.join(missing)}."
                )
            p.set_movie_values(tracking_type, global_cfg['fps'], global_cfg['mm_per_pixel'])
        else:
            p.set_tracking_type(tracking_type)

        # Apply any explicit parameter overrides present in global:
        overrides = {k: v for k, v in global_cfg.items() if k in _PARAMETER_KEYS}
        if overrides:
            p.set(**overrides)

        return p

    def _stats_metrics(self) -> list:
        """Return the metrics appropriate for pairwise comparison for this tracking type."""
        tt = self.parameters.get_tracking_type()
        if tt in (Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER,
                  Parameters.TrackingType.PAIRWISEINTERACTIONCOUNTER):
            return [f"PercentInteracting_{d}" for d in self.parameters.interaction_distance_mm]
        return _TRACKING_TYPE_METRICS.get(tt, [])

    def _resolve_cutoffs(self, cutoffs):
        """Return cutoffs to use, preferring the explicit argument over ``self.facet_cutoffs``.

        Returns None when neither is set; callers skip faceted operations gracefully.
        """
        return cutoffs if cutoffs is not None else self.facet_cutoffs

    def _plot_methods(self) -> list:
        """Return (method_name, kwargs) pairs for all relevant plots.

        Injects ``self.facet_cutoffs`` into plot kwargs only when it is set.
        """
        tt = self.parameters.get_tracking_type()
        base = _TRACKING_TYPE_PLOTS.get(tt, [])
        result = []
        for name, kwargs in base:
            merged = dict(kwargs)
            if name.endswith('_facet') and 'cutoffs' not in merged and self.facet_cutoffs is not None:
                merged['cutoffs'] = self.facet_cutoffs
            result.append((name, merged))
        return result

    # ------------------------------------------------------------------
    # Delegation to Arena
    # ------------------------------------------------------------------

    def __getattr__(self, name: str):
        """Delegate attribute lookups to the underlying Arena object."""
        if name == 'arena':
            raise AttributeError(name)
        return getattr(self.arena, name)

    # ------------------------------------------------------------------
    # User-facing methods
    # ------------------------------------------------------------------

    def experiment_summary(self, save: bool = True) -> str:
        """Print a detailed overview of the experiment and optionally save it to analysis_path.

        Parameters
        ----------
        save :
            If True, writes ``{experiment_name}_experiment_summary.txt`` to analysis_path.

        Returns
        -------
        str
            The full info text.
        """
        ## Counter-class experiments have no per-frame DataQuality; the overview
        ## still reports timing and tracker counts for them.
        supports_dq = self.arena.supports_data_quality()
        dq         = self.arena.get_data_quality() if supports_dq else None
        if supports_dq:
            n_total = len(dq)
            n_good  = int((dq['HighQuality'] >= 0.9).sum())
            t_min   = dq['StartMinutes'].min()
            t_max   = dq['EndMinutes'].max()
        else:
            n_total = len(self.arena.trackers)
            n_good  = None
            minutes = [t.rawdata['Minutes'] for t in self.arena.trackers.values()
                       if 'Minutes' in t.rawdata.columns and len(t.rawdata)]
            t_min   = min((m.min() for m in minutes), default=float('nan'))
            t_max   = max((m.max() for m in minutes), default=float('nan'))
        global_cfg = self.config.get('global', {})
        p          = self.parameters
        cutoffs_str = str(self.facet_cutoffs) if self.facet_cutoffs is not None else 'Not set'
        total_frames = sum(len(t.rawdata) for t in self.arena.trackers.values())

        W = 54  # separator width
        sep = '─' * W

        lines = [
            f"=== Experiment: {self.arena.experiment_name} ===",
            "",
            f"── Paths {'─' * (W - 8)}",
            f"  Project   : {self.project_directory}",
            f"  Data      : {self.data_path}",
            f"  Analysis  : {self.analysis_path}",
            f"  QC        : {self.qc_path}",
            "",
            f"── Configuration {'─' * (W - 17)}",
            f"  Tracking type  : {global_cfg.get('tracking_type', 'Unknown')}",
            f"  Tracking rig   : {global_cfg.get('tracking_rig', 'Unknown')}",
            f"  Facet cutoffs  : {cutoffs_str}",
            f"  Design loaded  : {'Yes' if self.experimental_design is not None else 'No'}",
            "",
            f"── Parameters {'─' * (W - 14)}",
            f"  FPS                   : {p.fps}",
            f"  mm / pixel            : {p.mm_per_pixel}",
            f"  Speed window          : {p.speed_window_seconds} s",
            f"  Micro-move speed      : {p.micro_move_speed_mm_sec[0]} – {p.micro_move_speed_mm_sec[1]} mm/s",
            f"  Walking speed         : ≥ {p.walking_speed_mm_sec} mm/s",
            f"  Sleep threshold       : {p.sleep_threshold_min} min",
            f"  Interaction distances : {p.interaction_distance_mm} mm",
            "",
            *self._design_summary_lines(W),
            f"── Data Overview {'─' * (W - 17)}",
            f"  Total trackers        : {n_total}",
            (f"  Passing ≥90% quality  : {n_good} / {n_total}" if supports_dq
             else "  Passing ≥90% quality  : n/a (no per-frame quality for this tracking type)"),
            f"  Recording range       : {t_min:.1f} – {t_max:.1f} min",
            f"  Total data points     : {total_frames:,}",
            "",
            f"── Per-Tracker Summary {'─' * (W - 23)}",
        ]

        def _treatment_of(key):
            tracker = self.arena.trackers.get(key)
            if tracker is not None and tracker.tracking_region_design is not None:
                return str(tracker.tracking_region_design['Treatment'].iat[0])
            return ''

        if supports_dq:
            # Table header
            h = (f"  {'Tracker':<12}  {'Treatment':<22}  {'OK':<2}"
                 f"  {'HighQuality':>11}  {'NotFound':>8}  {'Indiscernible':>13}"
                 f"  {'Start':>6}  {'End':>6}")
            lines.append(h)
            lines.append(f"  {'-'*12}  {'-'*22}  {'-'*2}  {'-'*11}  {'-'*8}  {'-'*13}  {'-'*6}  {'-'*6}")

            for _, row in dq.iterrows():
                key = row['Tracker']
                ok = '✓' if row['HighQuality'] >= 0.9 else '✗'
                lines.append(
                    f"  {key:<12}  {_treatment_of(key):<22}  {ok:<2}"
                    f"  {row['HighQuality']:>10.1%}  {row['NotFound']:>8.1%}"
                    f"  {row['Indiscernible']:>13.1%}"
                    f"  {row['StartMinutes']:>6.1f}  {row['EndMinutes']:>6.1f}"
                )
        else:
            lines.append(f"  {'Region':<12}  {'Treatment':<22}  {'Rows':>10}  {'Start':>6}  {'End':>6}")
            lines.append(f"  {'-'*12}  {'-'*22}  {'-'*10}  {'-'*6}  {'-'*6}")
            for key, tracker in self.arena.trackers.items():
                minutes = tracker.rawdata['Minutes'] if 'Minutes' in tracker.rawdata.columns else None
                start = minutes.min() if minutes is not None and len(minutes) else float('nan')
                end = minutes.max() if minutes is not None and len(minutes) else float('nan')
                lines.append(
                    f"  {key:<12}  {_treatment_of(key):<22}  {len(tracker.rawdata):>10,}"
                    f"  {start:>6.1f}  {end:>6.1f}"
                )

        text = '\n'.join(lines)
        print(text)

        if save:
            path = os.path.join(self.analysis_path,
                                f"{self.arena.experiment_name}_experiment_summary.txt")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"\nSaved: {path}")

        return text

    def _design_summary_lines(self, W: int) -> list:
        """Formatted description of the tracking_config.yaml design for the
        experiment summary: factors and their levels, factor assignments to
        tracking regions, non-unit location multipliers, counting regions with
        their aliases, and facet cutoffs."""
        import textwrap

        def _wrap(prefix: str, items: list) -> list:
            """One entry as ``prefix item, item, …`` wrapped to the summary width,
            continuation lines aligned under the first item."""
            return textwrap.wrap(
                prefix + ', '.join(str(i) for i in items),
                width=78,
                subsequent_indent=' ' * len(prefix),
            )

        lines = [f"── Experimental Design {'─' * (W - 23)}"]

        factors = self.config.get('global', {}).get('experimental_design_factors') or {}
        if factors:
            lines.append("  Factors:")
            name_w = max(len(str(n)) for n in factors)
            for name, levels in factors.items():
                if isinstance(levels, (list, tuple)):
                    levels_str = ', '.join(str(v) for v in levels)
                else:
                    levels_str = str(levels)
                lines.append(f"    {str(name):<{name_w}} : {levels_str}")
        else:
            lines.append("  Factors : none defined in config")

        ed = self.experimental_design
        tr = ed.tracking_regions if ed is not None else None
        if tr is not None and not tr.empty:
            lines.append("  Factor assignments (tracking regions):")
            for treatment, grp in tr.groupby('Treatment', sort=False):
                label = str(treatment).strip() or '(unassigned)'
                names = list(grp['RegionName'])
                lines.extend(_wrap(f"    {label} ({len(names)}): ", names))

            flipped = tr[(tr['XLocationMultiplier'] != 1) | (tr['YLocationMultiplier'] != 1)]
            if flipped.empty:
                lines.append("  Location multipliers : all 1 (no flips)")
            else:
                lines.append("  Location multipliers ≠ 1:")
                for (xm, ym), grp in flipped.groupby(
                    ['XLocationMultiplier', 'YLocationMultiplier'], sort=False
                ):
                    names = list(grp['RegionName'])
                    lines.extend(_wrap(f"    x={xm:+d}, y={ym:+d} ({len(names)}): ", names))
        else:
            lines.append("  Tracking regions : none defined in config")

        counting = ed.counting_regions if ed is not None else None
        if counting:
            lines.append("  Counting regions:")
            name_w = max(len(str(n)) for n in counting)
            for name, aliases in counting.items():
                lines.append(f"    {str(name):<{name_w}} : aliases {', '.join(aliases)}")
        else:
            lines.append("  Counting regions : none defined in config")

        if self.facet_cutoffs is not None:
            cutoffs_str = ', '.join(str(c) for c in self.facet_cutoffs) + ' min'
        else:
            cutoffs_str = 'not set'
        lines.append(f"  Facet cutoffs : {cutoffs_str}")
        lines.append("")
        return lines

    def _col_distribution(self, col: str) -> 'pd.DataFrame | None':
        """Return fraction-of-frames per unique value of *col*, one row per tracker.

        Returns None if the column is absent from any tracker's rawdata.
        """
        rows = []
        for key, tracker in self.arena.trackers.items():
            if col not in tracker.rawdata.columns:
                return None
            vc = tracker.rawdata[col].value_counts(normalize=True).sort_index()
            rows.append({'Tracker': key, **{str(k): v for k, v in vc.items()}})
        df = pd.DataFrame(rows).fillna(0).set_index('Tracker')
        return df

    def qc(self, cutoff: float = 0.9, save: bool = True) -> None:
        """
        Print the data quality report and optionally save it to qc_path.

        Counter-class experiments have no per-frame tracking quality to report,
        so this prints a note and returns instead of raising.

        Parameters
        ----------
        cutoff :
            Fraction of high-quality frames below which a tracker triggers a warning.
        save :
            If True, writes ``{experiment_name}_data_quality.csv`` to qc_path.
        """
        if not self.arena.supports_data_quality():
            print("Skipping data-quality table (not supported for this tracking type).")
            return

        dq = self.arena.get_data_quality()
        n_total = len(dq)
        n_good  = int((dq['HighQuality'] >= cutoff).sum())

        print(f"=== Data Quality: {self.arena.experiment_name} ===\n")
        print(f"Trackers passing ≥{cutoff:.0%} high-quality threshold: {n_good}/{n_total}\n")

        # Per-tracker table with all three quality types
        fmt = dq[['Tracker', 'HighQuality', 'NotFound', 'Indiscernible',
                   'StartMinutes', 'EndMinutes']].copy()
        for col in ('HighQuality', 'NotFound', 'Indiscernible'):
            fmt[col] = fmt[col].map('{:.1%}'.format)
        for col in ('StartMinutes', 'EndMinutes'):
            fmt[col] = fmt[col].map('{:.1f}'.format)
        print(fmt.to_string(index=False))

        # Summary stats per quality type
        print("\n--- Summary ---")
        for col in ('HighQuality', 'NotFound', 'Indiscernible'):
            print(f"  {col:15s}  mean={dq[col].mean():.1%}"
                  f"  min={dq[col].min():.1%}  max={dq[col].max():.1%}")

        # NObjects distribution
        nobj_df = self._col_distribution('NObjects')
        if nobj_df is not None:
            print("\n--- NObjects Distribution (% of frames) ---")
            print(nobj_df.apply(lambda c: c.map('{:.1%}'.format)).to_string())

        # BlobType distribution
        blob_df = self._col_distribution('BlobType')
        if blob_df is not None:
            print("\n--- BlobType Distribution (% of frames) ---")
            print(blob_df.apply(lambda c: c.map('{:.1%}'.format)).to_string())

        # Warnings
        below = dq[dq['HighQuality'] < cutoff]
        print()
        if len(below) > 0:
            print("****************************************************")
            print(f"Warning: {len(below)} tracker(s) below {cutoff:.0%} high-quality threshold:")
            for _, row in below.iterrows():
                print(f"  {row['Tracker']}: HighQuality={row['HighQuality']:.1%}"
                      f"  NotFound={row['NotFound']:.1%}"
                      f"  Indiscernible={row['Indiscernible']:.1%}")
            print("****************************************************")
        else:
            print("****************************************************")
            print(f"All trackers meet the {cutoff:.0%} high-quality threshold.")
            print("****************************************************")

        if save:
            path = os.path.join(self.qc_path, f"{self.arena.experiment_name}_data_quality.csv")
            dq.to_csv(path, index=False, na_rep='NA')
            print(f"\nSaved: {path}")

    def run_qc(self, cutoffs=None, qc_cutoff: float = 0.9) -> None:
        """Run the full QC suite. All outputs are written to ``self.qc_path``.

        Always:
          * Per-tracker data-quality table — same as :meth:`qc` (when supported).
          * Per-tracker XY plot grid (``<exp>_qc_trackers_xy.png``).

        Tracker-class types (TRACKER, TWOCHOICETRACKER, XCHOICETRACKER,
        PAIRWISEINTERACTIONTRACKER, CENTROPHOBISMTRACKER, DDROPTRACKER):
          * Faceted dot plot of TotalDistancePerMin
            (``<exp>_qc_TotalDistancePerMin_facet.png``).

        TWOCHOICETRACKER only:
          * Faceted dot plot of TransitionsPerMin
            (``<exp>_qc_TransitionsPerMin_facet.png``).

        Parameters
        ----------
        cutoffs :
            Facet cutoffs in minutes. Defaults to ``self.facet_cutoffs``.
        qc_cutoff :
            Fraction threshold passed through to :meth:`qc`.
        """
        cutoffs = self._resolve_cutoffs(cutoffs)
        name = self.arena.experiment_name
        print(f"=== Running QC for: {name} ===\n")

        # 1. Data-quality table (Tracker subclasses only — Counter has no get_data_quality).
        self.qc(cutoff=qc_cutoff, save=True)

        # 2. Per-tracker XY plot grid.
        self._save_qc_xy_grid()

        # 3. Conditional facet plots.
        tt = self.parameters.get_tracking_type()
        facet_tracker_types = (
            Parameters.TrackingType.TRACKER,
            Parameters.TrackingType.TWOCHOICETRACKER,
            Parameters.TrackingType.XCHOICETRACKER,
            Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER,
            Parameters.TrackingType.CENTROPHOBISMTRACKER,
            Parameters.TrackingType.DDROPTRACKER,
        )
        if tt in facet_tracker_types:
            self._save_qc_facet_plot('TotalDistancePerMin', cutoffs)

        if tt == Parameters.TrackingType.TWOCHOICETRACKER:
            self._save_qc_facet_plot('TransitionsPerMin', cutoffs)

        print(f"\n=== QC outputs in: {self.qc_path} ===")

    def _save_qc_xy_grid(self, range_minutes=(0, 0), ncols: int = 4) -> None:
        """Save a multi-panel XY scatter, one subplot per tracker, to qc_path."""
        tracker_items = list(self.arena.trackers.items())
        n = len(tracker_items)
        if n == 0:
            print("No trackers to plot.")
            return
        ncols = min(ncols, n)
        nrows = -(-n // ncols)
        exp_name = self.arena.experiment_name

        def _treatment(tr):
            d = getattr(tr, 'tracking_region_design', None)
            return str(d['Treatment'].iat[0]) if d is not None and not d.empty else ''

        def _x_mult(tr):
            d = getattr(tr, 'tracking_region_design', None)
            return int(d['XLocationMultiplier'].iloc[0]) if d is not None and not d.empty else 1

        def _y_mult(tr):
            d = getattr(tr, 'tracking_region_design', None)
            return int(d['YLocationMultiplier'].iloc[0]) if d is not None and not d.empty else 1

        fig, axes = plt.subplots(
            nrows, ncols, figsize=(ncols * 3.5, nrows * 3.5), squeeze=False,
        )
        for idx, (key, tracker) in enumerate(tracker_items):
            ax = axes[idx // ncols][idx % ncols]
            try:
                data = tracker.get_data_subset(range_minutes)
                xlims, ylims = tracker.get_plot_limits()
                ax.scatter(
                    data['Xpos_mm'] * _x_mult(tracker),
                    data['Ypos_mm'] * _y_mult(tracker),
                    c=data['Minutes'], cmap='viridis',
                    vmin=data['Minutes'].min(), vmax=data['Minutes'].max(),
                    s=1, alpha=0.5,
                )
                ax.set_xlim(xlims)
                ax.set_ylim(ylims)
                ax.set_aspect('equal', adjustable='box')
                ax.set_title(f"{key}\n{_treatment(tracker)}", fontsize=7)
                ax.tick_params(labelsize=6)
                roi = getattr(tracker, 'tracking_region_roi', None)
                if roi is not None and not roi.empty and roi['Shape'].values[0] == 'Ellipse':
                    w = roi['Width'].values[0] * tracker.parameters.mm_per_pixel
                    h = roi['Height'].values[0] * tracker.parameters.mm_per_pixel
                    ax.add_patch(patches.Ellipse(
                        (0, 0), width=w, height=h,
                        edgecolor='gray', facecolor='none', linewidth=0.8,
                    ))
            except Exception as err:  # noqa: BLE001
                ax.set_title(f"{key}\n(error: {err})", fontsize=7)
        for idx in range(n, nrows * ncols):
            axes[idx // ncols][idx % ncols].set_visible(False)
        fig.supxlabel('X Position (mm)', fontsize=9)
        fig.supylabel('Y Position (mm)', fontsize=9)
        fig.suptitle(f"{exp_name} — QC: XY positions", fontsize=11)
        fig.tight_layout()
        path = os.path.join(self.qc_path, f"{exp_name}_qc_trackers_xy.png")
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"Saved: {path}")

    def _save_qc_facet_plot(self, metric: str, cutoffs) -> None:
        """Save a facet dot plot of *metric* (mm/min or transitions/min) to qc_path."""
        if cutoffs is None:
            print(f"Skipping QC facet plot for {metric} (facet_cutoffs not set).")
            return

        method_name = {
            'TotalDistancePerMin': 'plot_totaldistance_facet_generaltracker',
            'TransitionsPerMin':   'plot_transitions_facet_twochoicetracker',
        }.get(metric)
        if method_name is None:
            print(f"Unknown QC facet metric: {metric}")
            return
        method = getattr(self.arena, method_name, None)
        if method is None:
            print(f"Arena does not implement {method_name}; skipping.")
            return

        exp_name = self.arena.experiment_name
        filename = os.path.join(self.qc_path, f"{exp_name}_qc_{metric}_facet.png")

        original_show = plt.show

        def _save_and_close():
            fig = plt.gcf()
            fig.savefig(filename, dpi=150, bbox_inches='tight')
            plt.close(fig)
            print(f"Saved: {filename}")

        plt.show = _save_and_close
        try:
            method(cutoffs=cutoffs)
        finally:
            plt.show = original_show

    def save_summary(self, cutoffs=None, copy_to_clipboard: bool = False):
        """
        Compute and save the flat and faceted summaries to analysis_path.

        Parameters
        ----------
        cutoffs :
            Facet cutoffs to use. Defaults to ``self.facet_cutoffs``.
        copy_to_clipboard :
            If True, copies the faceted summary to the clipboard.

        Returns
        -------
        tuple
            ``(summary_df, summary_facet_df)``
        """
        cutoffs = self._resolve_cutoffs(cutoffs)

        summary = self.arena.summarize()
        path = os.path.join(self.analysis_path, f"{self.arena.experiment_name}_Summary.csv")
        summary.to_csv(path, index=False, na_rep='NA')
        print(f"Saved: {path}")

        summary_facet = None
        if cutoffs is not None:
            summary_facet = self.arena.summarize_facet(cutoffs=cutoffs)
            path_facet = os.path.join(self.analysis_path,
                                      f"{self.arena.experiment_name}_Summary_Facet.csv")
            summary_facet.to_csv(path_facet, index=False, na_rep='NA')
            print(f"Saved: {path_facet}")
            if copy_to_clipboard:
                summary_facet.to_clipboard(index=False, na_rep='NA')
        else:
            print("Skipping faceted summary (facet_cutoffs not set in config or as argument).")

        return summary, summary_facet

    def stats(self, cutoffs=None, save: bool = True) -> str:
        """
        Run all relevant pairwise comparisons for this tracking type.

        Results are printed to the console and, when *save* is True, written to
        ``{experiment_name}_Stats.txt`` in analysis_path.

        When facet cutoffs are available the per-facet Tukey HSD comparisons are
        run; otherwise (or in addition) the flat full-recording comparisons are
        run, so :meth:`run_analysis` always produces a Stats file even on
        configs without ``facet_cutoffs``.

        Parameters
        ----------
        cutoffs :
            Facet cutoffs to use. Defaults to ``self.facet_cutoffs``.
        save :
            If True, writes the statistics text file to analysis_path.

        Returns
        -------
        str
            The full statistics output as a string.
        """
        cutoffs = self._resolve_cutoffs(cutoffs)

        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            metrics = self._stats_metrics()
            tracking_type = self.parameters.get_tracking_type()
            if not metrics:
                ## Never write a zero-byte Stats.txt: a reader cannot tell an
                ## empty file from a crashed run, and run_analysis reports
                ## success either way.
                if tracking_type in _TRACKING_TYPE_METRICS:
                    print(f"No statistical comparisons are defined for tracking type "
                          f"{tracking_type.name}: its summary carries no outcome metric.")
                else:
                    print(f"Warning: tracking type {tracking_type.name} has no statistics policy "
                          f"defined in this version. No comparisons were run.")
            elif cutoffs is None:
                print("(No facet_cutoffs configured — running flat pairwise comparisons.)\n")
                for metric in metrics:
                    try:
                        self.arena.run_pairwise_comparisons(metric=metric)
                    except Exception as e:  # noqa: BLE001
                        print(f"Warning: could not run comparison for '{metric}': {e}")
            else:
                for metric in metrics:
                    remove_partners = 'Interacting' in metric
                    try:
                        self.arena.run_pairwise_comparisons_facet(
                            metric=metric,
                            cutoffs=cutoffs,
                            remove_partners=remove_partners,
                        )
                    except Exception as e:  # noqa: BLE001
                        print(f"Warning: could not run comparison for '{metric}': {e}")
        finally:
            sys.stdout = old_stdout

        stats_text = buf.getvalue()
        print(stats_text)

        if save:
            path = os.path.join(self.analysis_path, f"{self.arena.experiment_name}_Stats.txt")
            with open(path, 'w') as f:
                f.write(stats_text)
            print(f"Saved: {path}")

        return stats_text

    def plot_totaldistance_facet(self, cutoffs=None, save: bool = True) -> None:
        """
        Plot total distance per minute across facet phases, with an option to save.

        Parameters
        ----------
        cutoffs :
            Facet cutoffs in minutes. Defaults to ``self.facet_cutoffs``.
        save :
            If True (default), saves the figure to analysis_path.
        """
        cutoffs = self._resolve_cutoffs(cutoffs)
        if cutoffs is None:
            print("Skipping plot_totaldistance_facet (facet_cutoffs not set in config or as argument).")
            return

        original_show = plt.show

        if save:
            filename = os.path.join(
                self.analysis_path,
                f"{self.arena.experiment_name}_plot_totaldistance_facet.png",
            )

            def _save_and_show():
                fig = plt.gcf()
                fig.savefig(filename, dpi=150, bbox_inches='tight')
                plt.close(fig)
                print(f"Saved: {filename}")

            plt.show = _save_and_show

        try:
            self.arena.plot_totaldistance_facet(cutoffs=cutoffs)
        finally:
            plt.show = original_show

    def save_tracker_grid_plots(self, range_minutes=(0, 0), output_dir=None, ncols=4) -> None:
        """
        Save one multi-panel figure per plot type, with every tracker as its own subplot.

        Produces four files:
            ``{name}_trackers_x.png``
            ``{name}_trackers_y.png``
            ``{name}_trackers_xy.png``
            ``{name}_trackers_totaldistance.png``

        Parameters
        ----------
        range_minutes :
            ``(start, end)`` in minutes. ``(0, 0)`` uses the full recording.
        output_dir :
            Destination directory. Defaults to ``self.analysis_path``.
        ncols :
            Number of columns in the subplot grid. Default 4.
        """
        if output_dir is None:
            output_dir = self.analysis_path
        os.makedirs(output_dir, exist_ok=True)

        tracker_items = list(self.arena.trackers.items())
        n = len(tracker_items)
        if n == 0:
            return

        ncols = min(ncols, n)
        nrows = -(-n // ncols)          # ceiling division
        exp_name = self.arena.experiment_name

        def _treatment(tracker):
            if tracker.tracking_region_design is not None:
                return str(tracker.tracking_region_design['Treatment'].iat[0])
            return ''

        def _x_mult(tracker):
            if tracker.tracking_region_design is not None:
                return int(tracker.tracking_region_design['XLocationMultiplier'].iloc[0])
            return 1

        def _y_mult(tracker):
            if tracker.tracking_region_design is not None:
                return int(tracker.tracking_region_design['YLocationMultiplier'].iloc[0])
            return 1

        # ── X position ──────────────────────────────────────────────────
        fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 4, nrows * 3), squeeze=False)
        for idx, (key, tracker) in enumerate(tracker_items):
            ax = axes[idx // ncols][idx % ncols]
            try:
                data = tracker.get_data_subset(range_minutes)
                xlims, _ = tracker.get_plot_limits()
                ax.plot(data['Minutes'], data['Xpos_mm'] * _x_mult(tracker), linewidth=0.8)
                ax.set_ylim(xlims)
                ax.set_title(f"{key}\n{_treatment(tracker)}", fontsize=7)
                ax.tick_params(labelsize=6)
            except Exception:
                ax.set_title(f"{key}\n(error)", fontsize=7)
        for idx in range(n, nrows * ncols):
            axes[idx // ncols][idx % ncols].set_visible(False)
        fig.supxlabel('Minutes', fontsize=9)
        fig.supylabel('X Position (mm)', fontsize=9)
        fig.suptitle(f"{exp_name} — X Position", fontsize=11)
        fig.tight_layout()
        path = os.path.join(output_dir, f"{exp_name}_trackers_x.png")
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"Saved: {path}")

        # ── Y position ──────────────────────────────────────────────────
        fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 4, nrows * 3), squeeze=False)
        for idx, (key, tracker) in enumerate(tracker_items):
            ax = axes[idx // ncols][idx % ncols]
            try:
                data = tracker.get_data_subset(range_minutes)
                _, ylims = tracker.get_plot_limits()
                ax.plot(data['Minutes'], data['Ypos_mm'] * _y_mult(tracker), linewidth=0.8)
                ax.set_ylim(ylims)
                ax.set_title(f"{key}\n{_treatment(tracker)}", fontsize=7)
                ax.tick_params(labelsize=6)
            except Exception:
                ax.set_title(f"{key}\n(error)", fontsize=7)
        for idx in range(n, nrows * ncols):
            axes[idx // ncols][idx % ncols].set_visible(False)
        fig.supxlabel('Minutes', fontsize=9)
        fig.supylabel('Y Position (mm)', fontsize=9)
        fig.suptitle(f"{exp_name} — Y Position", fontsize=11)
        fig.tight_layout()
        path = os.path.join(output_dir, f"{exp_name}_trackers_y.png")
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"Saved: {path}")

        # ── XY position ─────────────────────────────────────────────────
        fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.5, nrows * 3.5), squeeze=False)
        for idx, (key, tracker) in enumerate(tracker_items):
            ax = axes[idx // ncols][idx % ncols]
            try:
                data = tracker.get_data_subset(range_minutes)
                xlims, ylims = tracker.get_plot_limits()
                ax.scatter(
                    data['Xpos_mm'] * _x_mult(tracker),
                    data['Ypos_mm'] * _y_mult(tracker),
                    c=data['Minutes'], cmap='viridis',
                    vmin=data['Minutes'].min(), vmax=data['Minutes'].max(),
                    s=1, alpha=0.5,
                )
                ax.set_xlim(xlims)
                ax.set_ylim(ylims)
                ax.set_aspect('equal', adjustable='box')
                ax.set_title(f"{key}\n{_treatment(tracker)}", fontsize=7)
                ax.tick_params(labelsize=6)
                roi = getattr(tracker, 'tracking_region_roi', None)
                if roi is not None and roi['Shape'].values[0] == 'Ellipse':
                    w = roi['Width'].values[0] * tracker.parameters.mm_per_pixel
                    h = roi['Height'].values[0] * tracker.parameters.mm_per_pixel
                    ax.add_patch(patches.Ellipse(
                        (0, 0), width=w, height=h,
                        edgecolor='gray', facecolor='none', linewidth=0.8,
                    ))
            except Exception:
                ax.set_title(f"{key}\n(error)", fontsize=7)
        for idx in range(n, nrows * ncols):
            axes[idx // ncols][idx % ncols].set_visible(False)
        fig.supxlabel('X Position (mm)', fontsize=9)
        fig.supylabel('Y Position (mm)', fontsize=9)
        fig.suptitle(f"{exp_name} — XY Position", fontsize=11)
        fig.tight_layout()
        path = os.path.join(output_dir, f"{exp_name}_trackers_xy.png")
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"Saved: {path}")

        # ── Total distance ───────────────────────────────────────────────
        # Use Dist_mm.cumsum() rather than the raw DTrack TotalDistance column.
        # The DTrack column is in pixels, starts at a non-zero value at frame 1
        # (pre-accumulated from before the first saved frame), and has occasional
        # non-monotonic drops. Dist_mm is in mm, starts at 0, and is always >= 0.
        fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 4, nrows * 3), squeeze=False)
        for idx, (key, tracker) in enumerate(tracker_items):
            ax = axes[idx // ncols][idx % ncols]
            try:
                data = tracker.get_data_subset(range_minutes)
                cum_dist = data['Dist_mm'].cumsum()
                ax.plot(data['Minutes'], cum_dist, linewidth=0.8)
                ax.set_title(f"{key}\n{_treatment(tracker)}", fontsize=7)
                ax.tick_params(labelsize=6)
            except Exception:
                ax.set_title(f"{key}\n(error)", fontsize=7)
        for idx in range(n, nrows * ncols):
            axes[idx // ncols][idx % ncols].set_visible(False)
        fig.supxlabel('Minutes', fontsize=9)
        fig.supylabel('Total Distance (mm)', fontsize=9)
        fig.suptitle(f"{exp_name} — Total Distance", fontsize=11)
        fig.tight_layout()
        path = os.path.join(output_dir, f"{exp_name}_trackers_totaldistance.png")
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"Saved: {path}")

    def save_plots(self, cutoffs=None, output_dir: str = None) -> None:
        """
        Save all relevant plots for this tracking type as PNG files.

        Each Arena plot method is called with the current ``facet_cutoffs`` and
        its ``plt.show()`` call is intercepted so that figures are written to disk
        rather than displayed interactively.

        Parameters
        ----------
        cutoffs :
            Overrides ``self.facet_cutoffs`` for this call only.
        output_dir :
            Destination directory. Defaults to ``self.analysis_path``.
        """
        resolved = self._resolve_cutoffs(cutoffs)
        old_cutoffs = self.facet_cutoffs
        if resolved is not None:
            self.facet_cutoffs = resolved

        if output_dir is None:
            output_dir = self.analysis_path
        os.makedirs(output_dir, exist_ok=True)

        plot_methods = self._plot_methods()
        ## _plot_methods only injects `cutoffs` when facet_cutoffs is set. With
        ## no cutoffs configured the facet methods used to be called bare and
        ## fall through to a hardcoded (10, 70) default, so one PDF could carry
        ## whole-recording p-values beside plots split at 10 and 70 minutes with
        ## nothing marking the discrepancy. Skip them instead, and say so.
        if self.facet_cutoffs is None:
            skipped = [name for name, kwargs in plot_methods if name.endswith('_facet')]
            if skipped:
                print(f"(No facet_cutoffs configured — skipping {len(skipped)} faceted plot(s).)")
            plot_methods = [(name, kwargs) for name, kwargs in plot_methods
                            if not name.endswith('_facet')]

        method_counts: dict = {}
        current_method = ['unknown']
        original_show = plt.show

        def _save_and_close():
            name = current_method[0]
            method_counts[name] = method_counts.get(name, 0) + 1
            suffix = f"_{method_counts[name]}" if method_counts[name] > 1 else ""
            filename = os.path.join(
                output_dir,
                f"{self.arena.experiment_name}_{name}{suffix}.png",
            )
            fig = plt.gcf()
            fig.savefig(filename, dpi=150, bbox_inches='tight')
            plt.close(fig)
            print(f"Saved: {filename}")

        plt.show = _save_and_close
        try:
            for method_name, kwargs in plot_methods:
                current_method[0] = method_name
                try:
                    getattr(self.arena, method_name)(**kwargs)
                except Exception as e:
                    print(f"Warning: could not generate '{method_name}': {e}")
        finally:
            plt.show = original_show
            self.facet_cutoffs = old_cutoffs

        if self.parameters.get_tracking_type() == Parameters.TrackingType.TRACKER:
            self.save_tracker_grid_plots(output_dir=output_dir)

    # ------------------------------------------------------------------
    # PDF report generation
    # ------------------------------------------------------------------

    #: Name of the marker file :meth:`run_analysis` drops in ``analysis/``.
    _RUN_MANIFEST = ".pytracking_run.json"

    def _write_run_manifest(self) -> None:
        """Stamp the start of an analysis run so stale artifacts can be identified."""
        import json
        from datetime import datetime as _dt

        payload = {
            "started": time.time(),
            "started_iso": _dt.now().isoformat(timespec="seconds"),
            "facet_cutoffs": list(self.facet_cutoffs) if self.facet_cutoffs is not None else None,
            "tracking_type": self.parameters.get_tracking_type().name,
        }
        try:
            io_utils.atomic_write_text(
                os.path.join(self.analysis_path, self._RUN_MANIFEST),
                lambda handle: json.dump(payload, handle, indent=2),
            )
        except OSError as err:
            logger.warning("Could not write the run manifest: %s", err)

    def _run_started_at(self):
        """Timestamp of the last :meth:`run_analysis`, or None if never recorded."""
        import json

        path = os.path.join(self.analysis_path, self._RUN_MANIFEST)
        try:
            with open(path, encoding="utf-8") as handle:
                return float(json.load(handle)["started"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def create_report(self, cutoffs=None, qc_cutoff: float = 0.9,
                      backend: str = "reportlab") -> str:
        """Assemble a professional report for this experiment.

        Builds a backend-agnostic document model (see
        :mod:`pytrackinganalysis.report`) from the current analysis outputs and
        renders it with the named *backend* — reportlab today; the same model is
        designed to drive future Markdown/LaTeX backends without any change to
        the analysis core. Run after :meth:`run_analysis` and :meth:`run_qc`.

        Unlike the previous version, the report draws its plots natively as
        consolidated multi-panel figures rather than re-embedding the
        interactive ``save_plots`` PNGs, and reads the freshly written
        ``*_Stats.txt`` and ``*_Summary*.csv`` artifacts for its text and
        tables. ``cutoffs`` is accepted for back-compat and unused. Returns the
        path to the written report.
        """
        from .report import render as _render

        del cutoffs  # report sources the current analysis outputs, not a re-run.
        report = self.build_report_model(qc_cutoff=qc_cutoff)
        ext = {"reportlab": "pdf"}.get(backend, "pdf")
        out_path = os.path.join(
            self.analysis_path, f"{self.arena.experiment_name}_report.{ext}")
        _render(report, out_path, backend=backend)
        print(f"Saved: {out_path}")
        return out_path

    # ------------------------------------------------------------------
    # Report model assembly (analysis-side; imports the document model only,
    # never a rendering backend, so the core stays engine-independent).
    # ------------------------------------------------------------------

    def build_report_model(self, qc_cutoff: float = 0.9):
        """Build the backend-agnostic :class:`~...report.model.Report`.

        The single bridge between analysis data and the report: it emits the
        cover, section dividers, statistics text, summary tables and
        report-native figures as model blocks.
        """
        from datetime import datetime as _dt
        from pathlib import Path as _Path

        from . import report_figures
        from .report import model as _m

        exp_name = self.arena.experiment_name
        report = _m.Report(exp_name)

        # ---- Cover ----
        global_cfg = (self.config.get("global", {})
                      if isinstance(self.config, dict) else {})
        metadata = []
        if not self.experiment_type.is_custom:
            metadata.append(("Experiment type", self.experiment_type.display_name))
        metadata += [
            ("Tracking type", self.parameters.get_tracking_type().name),
            ("Tracking rig", str(global_cfg.get("tracking_rig", "—"))),
            ("Project", os.path.abspath(self.project_directory)),
            ("Generated", _dt.now().strftime("%Y-%m-%d %H:%M")),
        ]
        # Title/intro come from the Experiment Type (ADR-0001): a Valence report
        # says "Valence Experiment Report" and carries the assay's intro.
        report.add(_m.Cover(exp_name, self.experiment_type.report_title(),
                            metadata=metadata,
                            status=self._qc_status_line(qc_cutoff)))

        # ---- Analysis section ----
        # Whole-recording figures, then the per-phase (faceted) figures when
        # facet_cutoffs is configured, then the statistical-test text. The
        # numeric summary tables are NOT embedded — that data is written to the
        # CSVs in analysis/ by run_analysis; the report is a visual + stats
        # narrative, not a data dump.
        report.add(_m.SectionDivider("Analysis"))
        intro = self.experiment_type.report_intro()
        if intro:
            report.add(_m.Paragraph(intro))
        for fig in report_figures.build_analysis_figures(self):
            report.add(fig)
        for fig in report_figures.build_faceted_figures(self):
            report.add(fig)
        self._add_text_blocks(report, _Path(self.analysis_path), _m)

        # ---- Quality-control section ----
        report.add(_m.SectionDivider("Quality Control"))
        for fig in report_figures.build_qc_figures(self):
            report.add(fig)
        self._add_text_blocks(report, _Path(self.qc_path), _m)

        return report

    def _qc_status_line(self, qc_cutoff: float):
        """Cover-page QC one-liner as a semantic StatusLine, or None."""
        from .report import model as _m

        try:
            if not self.arena.supports_data_quality():
                return None
            dq = self.arena.get_data_quality()
            hq = pd.to_numeric(dq["HighQuality"], errors="coerce")
            n = len(hq)
            n_good = int((hq >= qc_cutoff).sum())
            level = _m.Level.OK if n_good == n else _m.Level.ERROR
            return _m.StatusLine(
                f"Data quality: {n_good}/{n} trackers ≥ {qc_cutoff:.0%} high-quality",
                level)
        except Exception:  # noqa: BLE001
            return None

    def _add_text_blocks(self, report, directory, _m) -> None:
        """Add each non-empty ``*.txt`` in *directory* as a Preformatted block."""
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.txt")):
            if path.name.startswith("."):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as err:
                text = f"(could not read {path.name}: {err})"
            if text.strip():
                report.add(_m.Preformatted(text, title=path.stem))



    def run_analysis(self, cutoffs=None, qc_cutoff: float = 0.9) -> None:
        """
        Run the complete analysis pipeline in one call.

        Order: experiment summary → QC report → summary CSVs → statistics → plots.

        Parameters
        ----------
        cutoffs :
            Facet cutoffs to use throughout. Defaults to ``self.facet_cutoffs``.
        qc_cutoff :
            Fraction threshold passed to :meth:`qc`.
        """
        cutoffs = self._resolve_cutoffs(cutoffs)

        name = self.arena.experiment_name
        print(f"=== Running analysis for: {name} ===\n")

        ## Record when this run began so create_report can tell the artifacts it
        ## produced from leftovers of an earlier configuration sitting in the
        ## same directory. Without it a stale *_Summary_Facet.csv is embedded in
        ## the PDF as a current result with no provenance marker at all.
        self._write_run_manifest()

        print("--- Experiment Summary ---")
        self.experiment_summary(save=True)

        print("\n--- Quality Control ---")
        ## The full QC suite, not just the table: it is guarded for counter-class
        ## experiments and writes the QC artifacts that create_report picks up.
        self.run_qc(cutoffs=cutoffs, qc_cutoff=qc_cutoff)

        print("\n--- Saving Summaries ---")
        self.save_summary(cutoffs=cutoffs)

        print("\n--- Running Statistics ---")
        self.stats(cutoffs=cutoffs, save=True)

        print("\n--- Saving Plots ---")
        self.save_plots(cutoffs=cutoffs)

        self._verify_output_manifest()

        print(f"\n=== Done. Outputs written to: {self.analysis_path} ===")

    def _verify_output_manifest(self) -> None:
        """Warn if the Experiment Type declared data outputs it did not produce.

        Each Experiment Type declares the files it is expected to write
        (``output_manifest``); this checks they exist after a run. Empty for a
        Custom Experiment, which declares nothing.
        """
        manifest = self.experiment_type.output_manifest()
        if not manifest:
            return
        name = self.arena.experiment_name
        missing = [suffix for suffix in manifest
                   if not os.path.exists(os.path.join(self.analysis_path, f"{name}{suffix}"))]
        if missing:
            print(f"Warning: {self.experiment_type.display_name} expected these "
                  f"outputs which were not produced: {', '.join(missing)}")

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        global_cfg = self.config.get('global', {})
        lines = [
            f"Experiment: {self.arena.experiment_name}",
            f"  Project directory : {self.project_directory}",
            f"  Data path         : {self.data_path}",
            f"  Analysis path     : {self.analysis_path}",
            f"  QC path           : {self.qc_path}",
            f"  Experiment type   : {self.experiment_type.display_name}",
            f"  Tracking type     : {self.parameters.get_tracking_type().name}",
            f"  Tracking rig      : {global_cfg.get('tracking_rig', 'Unknown')}",
            f"  Facet cutoffs     : {self.facet_cutoffs if self.facet_cutoffs is not None else 'Not set'}",
            f"  Parameters        :",
        ]
        for line in str(self.parameters).splitlines():
            lines.append(f"    {line}")
        if self.experimental_design is not None:
            lines.append(f"  Experimental design:")
            for line in str(self.experimental_design).splitlines():
                lines.append(f"    {line}")
        return '\n'.join(lines)

    def __repr__(self) -> str:
        return (
            f"Experiment(project_directory={self.project_directory!r}, "
            f"experiment={self.arena.experiment_name!r})"
        )


def _is_experiment_dir(path: str) -> bool:
    """Return True if *path* looks like a valid experiment directory.

    Requires:
      - tracking_config.yaml present (case-insensitive)
      - a subdirectory named 'data' (case-insensitive) that contains at least one .xlsx file
    """
    entries = {e.lower(): e for e in os.listdir(path)}

    if 'tracking_config.yaml' not in entries:
        return False

    data_name = entries.get('data')
    if data_name is None:
        return False

    data_dir = os.path.join(path, data_name)
    if not os.path.isdir(data_dir):
        return False

    return bool(glob.glob(os.path.join(data_dir, '*.xlsx')))


def batch_analyze(
    parent_directory: str,
    cutoffs=None,
    qc_cutoff: float = 0.9,
    force_preprocessing: bool = False,
) -> dict:
    """Run analysis and create a PDF report for every experiment in *parent_directory*.

    Scans all immediate subdirectories of *parent_directory* for valid experiment
    folders (those containing a ``tracking_config.yaml`` and a ``data/`` subdirectory
    with at least one ``.xlsx`` file). Runs :meth:`Experiment.run_analysis` and
    :meth:`Experiment.create_report` on each one.

    Parameters
    ----------
    parent_directory :
        Root directory to search. Only immediate subdirectories are checked
        (non-recursive).
    cutoffs :
        Facet cutoffs passed through to each experiment. ``None`` uses the
        value in each experiment's own ``tracking_config.yaml``.
    qc_cutoff :
        High-quality frame threshold used in the QC report (default 0.9).
    force_preprocessing :
        If True, forces re-computation of nearest-neighbour pre-processing.

    Returns
    -------
    dict
        ``{experiment_path: 'ok' | error_message}`` for every candidate directory.
    """
    parent_directory = os.path.abspath(parent_directory)
    results = {}

    candidates = sorted(
        entry for entry in (
            os.path.join(parent_directory, name)
            for name in os.listdir(parent_directory)
        )
        if os.path.isdir(entry)
    )

    if not candidates:
        print(f"No subdirectories found in {parent_directory}")
        return results

    valid = [p for p in candidates if _is_experiment_dir(p)]

    if not valid:
        print(f"No valid experiment directories found in {parent_directory}")
        return results

    print(f"Found {len(valid)} experiment(s) in {parent_directory}\n")

    for i, exp_dir in enumerate(valid, 1):
        print(f"[{i}/{len(valid)}] {exp_dir}")
        print("=" * 60)
        try:
            exp = Experiment(exp_dir, force_preprocessing=force_preprocessing)
            exp.run_analysis(cutoffs=cutoffs, qc_cutoff=qc_cutoff)
            exp.create_report(cutoffs=cutoffs, qc_cutoff=qc_cutoff)
            results[exp_dir] = 'ok'
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            print(f"  ERROR: {msg}")
            results[exp_dir] = msg
        print()

    ok = sum(1 for v in results.values() if v == 'ok')
    print(f"Batch complete: {ok}/{len(valid)} succeeded.")
    if ok < len(valid):
        print("Failed directories:")
        for path, msg in results.items():
            if msg != 'ok':
                print(f"  {path}: {msg}")

    return results


if __name__ == "__main__":
    project_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    exp = Experiment(project_dir)
    print(exp)
