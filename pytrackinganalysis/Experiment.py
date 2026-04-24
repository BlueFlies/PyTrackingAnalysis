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

        if cutoffs is None:
            print("Skipping statistics (facet_cutoffs not set in config or as argument).")
            return ''

        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            for metric in self._stats_metrics():
                remove_partners = 'Interacting' in metric
                try:
                    self.arena.run_pairwise_comparisons_facet(
                        metric=metric,
                        cutoffs=cutoffs,
                        remove_partners=remove_partners,
                    )
                except Exception as e:
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

    def create_report(self, cutoffs=None, qc_cutoff: float = 0.9) -> str:
        """Generate a PDF report of the experiment to analysis_path.

        The report contains:
          1. Experiment summary text
          2. Data quality table
          3. Per-tracker QC position grids (tracking types only)
          4. All analysis plots appropriate for the tracking type

        Parameters
        ----------
        cutoffs :
            Facet cutoffs to use for faceted plots. Defaults to ``self.facet_cutoffs``.
        qc_cutoff :
            High-quality threshold used to flag trackers in the QC table.

        Returns
        -------
        str
            Path to the saved PDF file.
        """
        from matplotlib.backends.backend_pdf import PdfPages

        cutoffs = self._resolve_cutoffs(cutoffs)
        exp_name = self.arena.experiment_name
        pdf_path = os.path.join(self.analysis_path, f"{exp_name}_report.pdf")

        with PdfPages(pdf_path) as pdf:

            # ── Page 1: Experiment summary text ───────────────────────────
            summary_text = self.experiment_summary(save=False)
            lines = summary_text.splitlines()
            lines_per_page = 90
            for chunk_start in range(0, max(len(lines), 1), lines_per_page):
                chunk = '\n'.join(lines[chunk_start:chunk_start + lines_per_page])
                fig = plt.figure(figsize=(8.5, 11))
                fig.text(0.04, 0.97, chunk,
                         fontsize=6.5, verticalalignment='top',
                         fontfamily='monospace', transform=fig.transFigure)
                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)

            # ── Page 2: Data quality table ─────────────────────────────────
            dq = self.arena.get_data_quality()
            col_labels = ['Tracker', 'HighQuality', 'NotFound',
                          'Indiscernible', 'Start (min)', 'End (min)']
            table_rows = []
            row_colors = []
            for _, row in dq.iterrows():
                ok = row['HighQuality'] >= qc_cutoff
                table_rows.append([
                    row['Tracker'],
                    f"{row['HighQuality']:.1%}",
                    f"{row['NotFound']:.1%}",
                    f"{row['Indiscernible']:.1%}",
                    f"{row['StartMinutes']:.1f}",
                    f"{row['EndMinutes']:.1f}",
                ])
                row_colors.append(['#d4edda' if ok else '#f8d7da'] * len(col_labels))

            fig, ax = plt.subplots(figsize=(11, max(3, 0.35 * len(table_rows) + 1.5)))
            ax.axis('off')
            tbl = ax.table(
                cellText=table_rows,
                colLabels=col_labels,
                cellColours=row_colors,
                loc='center',
                cellLoc='center',
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(8)
            tbl.scale(1, 1.4)
            n_good = int((dq['HighQuality'] >= qc_cutoff).sum())
            ax.set_title(
                f"Data Quality — {exp_name}   "
                f"({n_good}/{len(dq)} trackers ≥ {qc_cutoff:.0%} high-quality)   "
                f"green = pass, red = fail",
                fontsize=10, pad=16,
            )
            pdf.savefig(fig, bbox_inches='tight')
            plt.close(fig)

            # ── Pages 3+: Per-tracker QC grid plots (tracking class only) ─
            if self.parameters.get_tracking_class() == Parameters.TrackingClass.TRACKING:
                tracker_items = list(self.arena.trackers.items())
                n = len(tracker_items)
                if n > 0:
                    ncols = min(4, n)
                    nrows = -(-n // ncols)

                    def _trt(tracker):
                        if tracker.tracking_region_design is not None:
                            return str(tracker.tracking_region_design['Treatment'].iat[0])
                        return ''

                    def _xm(tracker):
                        if tracker.tracking_region_design is not None:
                            return int(tracker.tracking_region_design['XLocationMultiplier'].iloc[0])
                        return 1

                    def _ym(tracker):
                        if tracker.tracking_region_design is not None:
                            return int(tracker.tracking_region_design['YLocationMultiplier'].iloc[0])
                        return 1

                    for plot_type, sup_x, sup_y, title_sfx in [
                        ('x',    'Minutes', 'X Position (mm)', '— X Position'),
                        ('y',    'Minutes', 'Y Position (mm)', '— Y Position'),
                        ('dist', 'Minutes', 'Cumulative Distance (mm)', '— Total Distance'),
                    ]:
                        fig, axes = plt.subplots(
                            nrows, ncols,
                            figsize=(ncols * 4, nrows * 3),
                            squeeze=False,
                        )
                        for idx, (key, tracker) in enumerate(tracker_items):
                            ax = axes[idx // ncols][idx % ncols]
                            try:
                                data = tracker.get_data_subset((0, 0))
                                if plot_type == 'x':
                                    xlims, _ = tracker.get_plot_limits()
                                    ax.plot(data['Minutes'],
                                            data['Xpos_mm'] * _xm(tracker),
                                            linewidth=0.8)
                                    ax.set_ylim(xlims)
                                elif plot_type == 'y':
                                    _, ylims = tracker.get_plot_limits()
                                    ax.plot(data['Minutes'],
                                            data['Ypos_mm'] * _ym(tracker),
                                            linewidth=0.8)
                                    ax.set_ylim(ylims)
                                else:
                                    ax.plot(data['Minutes'],
                                            data['Dist_mm'].cumsum(),
                                            linewidth=0.8)
                                ax.set_title(f"{key}\n{_trt(tracker)}", fontsize=7)
                                ax.tick_params(labelsize=6)
                            except Exception:
                                ax.set_title(f"{key}\n(error)", fontsize=7)
                        for idx in range(n, nrows * ncols):
                            axes[idx // ncols][idx % ncols].set_visible(False)
                        fig.supxlabel(sup_x, fontsize=9)
                        fig.supylabel(sup_y, fontsize=9)
                        fig.suptitle(f"{exp_name} {title_sfx}", fontsize=11)
                        fig.tight_layout()
                        pdf.savefig(fig, bbox_inches='tight')
                        plt.close(fig)

                    # XY scatter grid — rasterized to keep PDF size manageable
                    fig, axes = plt.subplots(
                        nrows, ncols,
                        figsize=(ncols * 3.5, nrows * 3.5),
                        squeeze=False,
                    )
                    for idx, (key, tracker) in enumerate(tracker_items):
                        ax = axes[idx // ncols][idx % ncols]
                        try:
                            data = tracker.get_data_subset((0, 0))
                            # Downsample to at most 5000 points per tracker to keep PDF renderable
                            if len(data) > 5000:
                                data = data.iloc[::len(data) // 5000]
                            xlims, ylims = tracker.get_plot_limits()
                            ax.scatter(
                                data['Xpos_mm'] * _xm(tracker),
                                data['Ypos_mm'] * _ym(tracker),
                                c=data['Minutes'], cmap='viridis',
                                vmin=data['Minutes'].min(),
                                vmax=data['Minutes'].max(),
                                s=2, alpha=0.5,
                                rasterized=True,
                            )
                            ax.set_xlim(xlims)
                            ax.set_ylim(ylims)
                            ax.set_aspect('equal', adjustable='box')
                            ax.set_title(f"{key}\n{_trt(tracker)}", fontsize=7)
                            ax.tick_params(labelsize=6)
                        except Exception:
                            ax.set_title(f"{key}\n(error)", fontsize=7)
                    for idx in range(n, nrows * ncols):
                        axes[idx // ncols][idx % ncols].set_visible(False)
                    fig.supxlabel('X Position (mm)', fontsize=9)
                    fig.supylabel('Y Position (mm)', fontsize=9)
                    fig.suptitle(f"{exp_name} — XY Position", fontsize=11)
                    fig.tight_layout()
                    pdf.savefig(fig, bbox_inches='tight', dpi=150)
                    plt.close(fig)

            # ── Final pages: analysis plots ────────────────────────────────
            # Close any stray figures left open by prior sections before
            # intercepting plt.show, so they don't pollute _add_to_pdf.
            plt.close('all')

            old_cutoffs = self.facet_cutoffs
            if cutoffs is not None:
                self.facet_cutoffs = cutoffs

            original_show = plt.show

            def _add_to_pdf():
                fig = plt.gcf()
                # Only save if the figure actually has axes (guards against
                # plt.gcf() auto-creating a blank figure).
                if fig.get_axes():
                    pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)

            plt.show = _add_to_pdf
            try:
                for method_name, kwargs in self._plot_methods():
                    try:
                        getattr(self.arena, method_name)(**kwargs)
                    except Exception as e:
                        print(f"Warning: could not generate '{method_name}': {e}")
            finally:
                plt.show = original_show
                self.facet_cutoffs = old_cutoffs
                plt.close('all')

        print(f"Report saved: {pdf_path}")
        return pdf_path

    def run_analysis(self, cutoffs=None, qc_cutoff: float = 0.9) -> None:
        """
        Run the complete analysis pipeline in one call.

        Order: experiment summary → QC report → summary CSVs → plots → statistics.

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

        print("\n--- Saving Plots ---")
        self.save_plots(cutoffs=cutoffs)

        print("\n--- Running Statistics ---")
        self.stats(cutoffs=cutoffs, save=True)

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
