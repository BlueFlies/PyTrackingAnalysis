import glob
import io
import logging
import os
import sys
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import pandas as pd
import yaml
from . import Parameters
from . import Arena

_RIG_MAP = Arena._RIG_MAP
_PARAMETER_KEYS = Arena._PARAMETER_KEYS

logger = logging.getLogger(__name__)

# Maps TrackingType to the plot methods (and kwargs) that are relevant for it
_TRACKING_TYPE_PLOTS = {
    Parameters.TrackingType.TRACKER: [
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
    Parameters.TrackingType.TWOCHOICETRACKER:          ['FinalPI', 'FinalPercentage', 'TotalDistancePerMin'],
    Parameters.TrackingType.TWOCHOICECOUNTER:          ['FinalPI', 'FinalPercentage'],
    Parameters.TrackingType.XCHOICETRACKER:            ['AvgAdjX_mm', 'TotalDistancePerMin'],
    Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER: None,   # built at runtime from interaction distances
    Parameters.TrackingType.PAIRWISEINTERACTIONCOUNTER: None,
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

    def __init__(self, project_directory: str, force_preprocessing: bool = False):
        """
        Parameters
        ----------
        project_directory :
            Root directory for the experiment. Must contain ``tracking_config.yaml``
            and a ``data/`` subdirectory with the experiment xlsx and csv files.
        force_preprocessing :
            Passed through to Arena; forces re-computation of nearest-neighbour
            pre-processing when True.
        """
        self.project_directory = os.path.abspath(project_directory)
        self.data_path     = self._find_subdir('data') + '/'
        self.analysis_path = os.path.join(self.project_directory, 'analysis') + '/'
        self.qc_path       = os.path.join(self.project_directory, 'qc') + '/'
        self.config_path   = os.path.join(self.project_directory, 'tracking_config.yaml')

        # Create output directories (data/ must already exist with files in it)
        os.makedirs(self.analysis_path, exist_ok=True)
        os.makedirs(self.qc_path, exist_ok=True)

        self.config = self._load_config()
        self.parameters = self._build_parameters()

        xlsx_files = glob.glob(os.path.join(self.data_path, '*.xlsx'))
        if not xlsx_files:
            raise FileNotFoundError(f"No .xlsx file found in {self.data_path}")
        exp_name = os.path.splitext(os.path.basename(xlsx_files[0]))[0]

        self.arena = Arena.Arena(
            exp_name, self.data_path, self.parameters,
            config_path=self.config_path,
            force_preprocessing=force_preprocessing,
        )

        # facet_cutoffs is optional in the global: section, e.g. facet_cutoffs: [10, 70]
        global_cfg = self.config.get('global', {})
        raw_cutoffs = global_cfg.get('facet_cutoffs')
        self.facet_cutoffs: tuple | None = tuple(raw_cutoffs) if raw_cutoffs is not None else None

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
            raise FileNotFoundError(
                f"tracking_config.yaml not found in {self.project_directory}"
            )
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _build_parameters(self) -> Parameters.Parameters:
        """Create a Parameters object from the global: section of the yaml."""
        global_cfg = self.config.get('global', {})

        # Resolve tracking type
        tracking_type_str = global_cfg.get('tracking_type', 'TRACKER').upper()
        try:
            tracking_type = Parameters.TrackingType[tracking_type_str]
        except KeyError:
            raise ValueError(
                f"Unknown tracking_type '{tracking_type_str}' in tracking_config.yaml. "
                f"Valid values: {[t.name for t in Parameters.TrackingType]}"
            )

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
            fps = global_cfg.get('fps', 30)
            mm_per_pixel = global_cfg.get('mm_per_pixel', 0.1)
            p.set_movie_values(tracking_type, fps, mm_per_pixel)
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
        dq         = self.arena.get_data_quality()
        n_total    = len(dq)
        n_good     = int((dq['HighQuality'] >= 0.9).sum())
        t_min      = dq['StartMinutes'].min()
        t_max      = dq['EndMinutes'].max()
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
            f"── Data Overview {'─' * (W - 17)}",
            f"  Total trackers        : {n_total}",
            f"  Passing ≥90% quality  : {n_good} / {n_total}",
            f"  Recording range       : {t_min:.1f} – {t_max:.1f} min",
            f"  Total data points     : {total_frames:,}",
            "",
            f"── Per-Tracker Summary {'─' * (W - 23)}",
        ]

        # Table header
        h = (f"  {'Tracker':<12}  {'Treatment':<22}  {'OK':<2}"
             f"  {'HighQuality':>11}  {'NotFound':>8}  {'Indiscernible':>13}"
             f"  {'Start':>6}  {'End':>6}")
        lines.append(h)
        lines.append(f"  {'-'*12}  {'-'*22}  {'-'*2}  {'-'*11}  {'-'*8}  {'-'*13}  {'-'*6}  {'-'*6}")

        for _, row in dq.iterrows():
            key     = row['Tracker']
            tracker = self.arena.trackers.get(key)
            treatment = ''
            if tracker is not None and tracker.tracking_region_design is not None:
                treatment = str(tracker.tracking_region_design['Treatment'].iat[0])
            ok = '✓' if row['HighQuality'] >= 0.9 else '✗'
            lines.append(
                f"  {key:<12}  {treatment:<22}  {ok:<2}"
                f"  {row['HighQuality']:>10.1%}  {row['NotFound']:>8.1%}"
                f"  {row['Indiscernible']:>13.1%}"
                f"  {row['StartMinutes']:>6.1f}  {row['EndMinutes']:>6.1f}"
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

        Parameters
        ----------
        cutoff :
            Fraction of high-quality frames below which a tracker triggers a warning.
        save :
            If True, writes ``{experiment_name}_data_quality.csv`` to qc_path.
        """
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
        first = next(iter(self.arena.trackers.values()), None)
        if first is not None and hasattr(first, 'get_data_quality'):
            self.qc(cutoff=qc_cutoff, save=True)
        else:
            print("Skipping data-quality table (not supported for this tracking type).")

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
            if cutoffs is None:
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

        plot_methods = self._plot_methods()
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

    # Letter-size page dimensions in inches.
    _LETTER_PORTRAIT = (8.5, 11.0)
    _LETTER_LANDSCAPE = (11.0, 8.5)
    # Inset that keeps content off the edge of the printable area.
    _MARGIN_LEFT = 0.06
    _MARGIN_RIGHT = 0.94
    _MARGIN_TOP = 0.94
    _MARGIN_BOTTOM = 0.06

    def create_report(self, cutoffs=None, qc_cutoff: float = 0.9) -> str:
        """Assemble a letter-size PDF report from the artifacts already in
        ``analysis/`` and ``qc/``.

        Run this after :meth:`run_analysis` and :meth:`run_qc`. The PDF is
        written to ``<analysis_path>/<exp>_report.pdf``. The report layout:

          * Cover page
          * Section divider — "Analysis"
          * Every ``.txt`` in ``analysis/`` (paginated monospaced text)
          * Every ``.csv`` in ``analysis/`` (rendered as a table)
          * Every ``.png`` in ``analysis/`` (one image per page, fit to letter)
          * Section divider — "Quality Control"
          * Every ``.txt`` / ``.csv`` / ``.png`` in ``qc/``

        Parameters are accepted for back-compat but ``cutoffs`` is unused
        (the report reads pre-rendered artifacts). ``qc_cutoff`` only drives
        the colored summary line on the cover page.
        """
        from matplotlib.backends.backend_pdf import PdfPages
        from pathlib import Path as _Path

        del cutoffs  # unused; report sources already-rendered artifacts.

        exp_name = self.arena.experiment_name
        analysis_dir = _Path(self.analysis_path)
        qc_dir = _Path(self.qc_path)
        pdf_path = os.path.join(self.analysis_path, f"{exp_name}_report.pdf")
        # Don't try to embed the report into itself.
        exclude = {os.path.abspath(pdf_path)}

        plt.close("all")
        with PdfPages(pdf_path) as pdf:
            self._report_cover_page(pdf, exp_name, qc_cutoff)

            self._report_section_divider(pdf, "Analysis")
            self._report_section_files(pdf, analysis_dir, exclude=exclude)

            self._report_section_divider(pdf, "Quality Control")
            self._report_section_files(pdf, qc_dir, exclude=exclude)

        plt.close("all")
        print(f"Saved: {pdf_path}")
        return pdf_path

    # ---------- Section walker -----------------------------------------

    def _report_section_files(
        self,
        pdf,
        directory,
        exclude: set | None = None,
    ) -> None:
        from pathlib import Path as _Path

        directory = _Path(directory)
        if not directory.exists():
            return
        exclude = {os.path.abspath(p) for p in (exclude or set())}

        def _filter(paths):
            return [p for p in paths if os.path.abspath(p) not in exclude]

        # Order text → tables → images so the narrative reads top-down.
        for path in sorted(_filter(directory.glob("*.txt"))):
            self._report_text_file(pdf, path)
        for path in sorted(_filter(directory.glob("*.csv"))):
            self._report_csv_table(pdf, path)
        for path in sorted(_filter(directory.glob("*.png"))):
            self._report_image(pdf, path)

    # ---------- Cover + section divider --------------------------------

    def _report_cover_page(self, pdf, exp_name: str, qc_cutoff: float) -> None:
        from datetime import datetime as _dt

        fig = plt.figure(figsize=self._LETTER_PORTRAIT)
        fig.patch.set_facecolor("white")

        # Title block — centered, top third.
        fig.text(0.5, 0.78, exp_name, ha="center", va="center",
                 fontsize=26, fontweight="bold", color="#0f172a")
        fig.text(0.5, 0.72, "Tracking Analysis Report",
                 ha="center", va="center", fontsize=14, color="#475569")
        # Hairline separator under the title block.
        ax_line = fig.add_axes([0.18, 0.685, 0.64, 0.001])
        ax_line.axis("off")
        ax_line.axhline(0, color="#94a3b8", linewidth=0.8)

        # Metadata block.
        global_cfg = self.config.get("global", {}) if isinstance(self.config, dict) else {}
        info = [
            ("Tracking type", self.parameters.get_tracking_type().name),
            ("Tracking rig", str(global_cfg.get("tracking_rig", "—"))),
            ("Project", os.path.abspath(self.project_directory)),
            ("Generated", _dt.now().strftime("%Y-%m-%d %H:%M")),
        ]
        y = 0.6
        for label, value in info:
            fig.text(0.18, y, f"{label}:", fontsize=10, color="#64748b",
                     fontweight="bold")
            fig.text(0.36, y, value, fontsize=10, family="monospace",
                     color="#0f172a")
            y -= 0.03

        # QC summary line — green if everything passes, red otherwise.
        try:
            dq = self.arena.get_data_quality()
            n = len(dq)
            n_good = int((dq["HighQuality"] >= qc_cutoff).sum())
            color = "#16a34a" if n_good == n else "#dc2626"
            fig.text(
                0.5, 0.36,
                f"Data quality: {n_good}/{n} trackers ≥ {qc_cutoff:.0%} high-quality",
                ha="center", fontsize=12, color=color, fontweight="bold",
            )
        except Exception:  # noqa: BLE001
            pass

        # Footer.
        fig.text(0.5, 0.05, "PyTrackingAnalysis", ha="center", va="center",
                 fontsize=9, color="#94a3b8")

        pdf.savefig(fig)
        plt.close(fig)

    def _report_section_divider(self, pdf, title: str) -> None:
        fig = plt.figure(figsize=self._LETTER_PORTRAIT)
        fig.patch.set_facecolor("white")
        fig.text(0.5, 0.5, title, ha="center", va="center",
                 fontsize=42, fontweight="bold", color="#1f2937")
        # Decorative bars above and below.
        ax = fig.add_axes([0.25, 0.555, 0.5, 0.001]); ax.axis("off")
        ax.axhline(0, color="#94a3b8", linewidth=1.2)
        ax = fig.add_axes([0.25, 0.445, 0.5, 0.001]); ax.axis("off")
        ax.axhline(0, color="#94a3b8", linewidth=1.2)
        pdf.savefig(fig)
        plt.close(fig)

    # ---------- Body content renderers ---------------------------------

    def _report_page_header(self, fig, title: str, subtitle: str | None = None) -> None:
        fig.text(self._MARGIN_LEFT, self._MARGIN_TOP + 0.03, title,
                 fontsize=12, fontweight="bold", color="#0f172a")
        if subtitle:
            fig.text(self._MARGIN_RIGHT, self._MARGIN_TOP + 0.03, subtitle,
                     fontsize=9, color="#64748b", ha="right")
        # Underline.
        ax = fig.add_axes(
            [self._MARGIN_LEFT, self._MARGIN_TOP + 0.018,
             self._MARGIN_RIGHT - self._MARGIN_LEFT, 0.0008],
        )
        ax.axis("off")
        ax.axhline(0, color="#cbd5e1", linewidth=0.6)

    def _report_text_file(self, pdf, path) -> None:
        title = path.stem
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as err:  # noqa: BLE001
            text = f"(could not read {path.name}: {err})"
        lines = text.splitlines() or [""]

        LINES_PER_PAGE = 60
        total_pages = max(1, -(-len(lines) // LINES_PER_PAGE))
        for page_idx in range(total_pages):
            start = page_idx * LINES_PER_PAGE
            chunk = "\n".join(lines[start:start + LINES_PER_PAGE])
            fig = plt.figure(figsize=self._LETTER_PORTRAIT)
            fig.patch.set_facecolor("white")
            subtitle = (
                f"page {page_idx + 1}/{total_pages}"
                if total_pages > 1 else None
            )
            self._report_page_header(fig, title, subtitle)
            fig.text(
                self._MARGIN_LEFT,
                self._MARGIN_TOP - 0.01,
                chunk,
                fontsize=8.5, family="monospace",
                verticalalignment="top",
                color="#0f172a",
            )
            pdf.savefig(fig)
            plt.close(fig)

    def _report_csv_table(self, pdf, path) -> None:
        title = path.stem
        try:
            df = pd.read_csv(path)
        except Exception as err:  # noqa: BLE001
            self._report_text_file_string(pdf, title, f"(could not read {path}: {err})")
            return
        if df.empty:
            self._report_text_file_string(pdf, title, "(empty)")
            return

        # Wide tables go landscape.
        landscape = len(df.columns) > 6
        figsize = self._LETTER_LANDSCAPE if landscape else self._LETTER_PORTRAIT

        # Format float columns for compactness; keep ints / strings as-is.
        display = df.copy()
        for col in display.columns:
            if pd.api.types.is_float_dtype(display[col]):
                display[col] = display[col].map(
                    lambda v: ("" if pd.isna(v) else f"{v:.3f}")
                )
            else:
                display[col] = display[col].astype(str)

        rows_per_page = 30 if landscape else 36
        n_rows = len(display)
        total_pages = max(1, -(-n_rows // rows_per_page))

        for page_idx in range(total_pages):
            start = page_idx * rows_per_page
            chunk = display.iloc[start:start + rows_per_page]
            fig = plt.figure(figsize=figsize)
            fig.patch.set_facecolor("white")
            subtitle = (
                f"page {page_idx + 1}/{total_pages}  ·  rows {start + 1}–"
                f"{start + len(chunk)} of {n_rows}"
            )
            self._report_page_header(fig, title, subtitle)

            ax = fig.add_axes([
                self._MARGIN_LEFT,
                self._MARGIN_BOTTOM,
                self._MARGIN_RIGHT - self._MARGIN_LEFT,
                self._MARGIN_TOP - self._MARGIN_BOTTOM - 0.04,
            ])
            ax.axis("off")
            tbl = ax.table(
                cellText=chunk.values.tolist(),
                colLabels=list(chunk.columns),
                cellLoc="center",
                loc="upper center",
            )
            tbl.auto_set_font_size(False)
            font_size = 7.5 if len(chunk.columns) > 8 else 8.5
            tbl.set_fontsize(font_size)
            tbl.scale(1, 1.35)

            # Header row styling.
            for j in range(len(chunk.columns)):
                cell = tbl[(0, j)]
                cell.set_facecolor("#1f2937")
                cell.set_text_props(color="white", weight="bold")
                cell.set_height(cell.get_height() * 1.1)
            # Alternating row tints, plus green/red for HighQuality if present.
            hq_idx = (
                list(chunk.columns).index("HighQuality")
                if "HighQuality" in chunk.columns else -1
            )
            for i, (_, row) in enumerate(chunk.iterrows()):
                base = "#f8fafc" if i % 2 == 0 else "#ffffff"
                for j in range(len(chunk.columns)):
                    tbl[(i + 1, j)].set_facecolor(base)
                if hq_idx >= 0:
                    try:
                        hq_val = float(str(row.iloc[hq_idx]).rstrip("%"))
                        if hq_val < 1.0:  # already a fraction
                            pass
                        else:
                            hq_val = hq_val / 100.0
                    except (TypeError, ValueError):
                        hq_val = None
                    if hq_val is not None:
                        if hq_val >= 0.90:
                            tint = "#dcfce7"
                        elif hq_val >= 0.80:
                            tint = "#fef9c3"
                        else:
                            tint = "#fee2e2"
                        for j in range(len(chunk.columns)):
                            tbl[(i + 1, j)].set_facecolor(tint)

            pdf.savefig(fig)
            plt.close(fig)

    def _report_text_file_string(self, pdf, title: str, body: str) -> None:
        """Helper for the rare case we need to surface a string, not a real file."""
        fig = plt.figure(figsize=self._LETTER_PORTRAIT)
        fig.patch.set_facecolor("white")
        self._report_page_header(fig, title)
        fig.text(self._MARGIN_LEFT, self._MARGIN_TOP - 0.01, body,
                 fontsize=9, family="monospace", verticalalignment="top",
                 color="#0f172a")
        pdf.savefig(fig)
        plt.close(fig)

    def _report_image(self, pdf, path) -> None:
        import matplotlib.image as mpimg

        title = path.stem
        try:
            img = mpimg.imread(str(path))
        except Exception as err:  # noqa: BLE001
            self._report_text_file_string(pdf, title, f"(could not read image: {err})")
            return

        # Pick orientation that wastes less paper for the source aspect ratio.
        h = img.shape[0]
        w = img.shape[1]
        landscape = w > h
        figsize = self._LETTER_LANDSCAPE if landscape else self._LETTER_PORTRAIT

        fig = plt.figure(figsize=figsize)
        fig.patch.set_facecolor("white")
        self._report_page_header(fig, title)

        ax = fig.add_axes([
            self._MARGIN_LEFT,
            self._MARGIN_BOTTOM,
            self._MARGIN_RIGHT - self._MARGIN_LEFT,
            self._MARGIN_TOP - self._MARGIN_BOTTOM - 0.04,
        ])
        ax.imshow(img)
        ax.axis("off")
        # Preserve aspect ratio inside the page area.
        ax.set_aspect("equal")
        pdf.savefig(fig, dpi=150)
        plt.close(fig)

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

        print("--- Experiment Summary ---")
        self.experiment_summary(save=True)

        print("\n--- Quality Control ---")
        self.qc(cutoff=qc_cutoff, save=True)

        print("\n--- Saving Summaries ---")
        self.save_summary(cutoffs=cutoffs)

        print("\n--- Running Statistics ---")
        self.stats(cutoffs=cutoffs, save=True)

        print("\n--- Saving Plots ---")
        self.save_plots(cutoffs=cutoffs)

        print(f"\n=== Done. Outputs written to: {self.analysis_path} ===")

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
            f"  Tracking type     : {global_cfg.get('tracking_type', 'Unknown')}",
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
