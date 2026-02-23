import io
import logging
import os
import sys
import matplotlib.pyplot as plt
import yaml
import Parameters
import Arena

logger = logging.getLogger(__name__)

# Maps tracking_rig values from tracking_config.yaml to normalized names
_RIG_MAP = {
    'small_arena':  'small_arena',
    'smallarena':   'small_arena',
    'arena_max':    'arena_max',
    'arenamax':     'arena_max',
    'colosseum':    'colosseum',
    'colloseum':    'colosseum',
    'obscura':      'obscura',
    'movie':        'movie',
}

# Parameter keys that can be overridden directly in the global: section of the yaml
_PARAMETER_KEYS = {
    'fps', 'mm_per_pixel', 'speed_window_seconds',
    'micromove_speed_mm_sec', 'walking_speed_mm_sec',
    'sleep_threshold_min', 'interaction_distances',
}

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
        exp.info()
        exp.qc()
        exp.run_analysis()          # QC + summaries + plots + stats in one call

    All Arena methods are accessible directly on the Experiment object via
    attribute delegation, so ``exp.summarize()`` is the same as
    ``exp.arena.summarize()``.

    YAML global section keys recognised
    ------------------------------------
    tracking_type   : TrackingType enum name (e.g. ``TWOCHOICETRACKER``)
    tracking_rig    : Rig preset name (small_arena, arena_max, colosseum, obscura, movie)
    facet_cutoffs   : List of minute boundaries for faceted analysis (default [10, 70])
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
        self.data_path     = os.path.join(self.project_directory, 'data') + '/'
        self.analysis_path = os.path.join(self.project_directory, 'analysis') + '/'
        self.qc_path       = os.path.join(self.project_directory, 'qc') + '/'
        self.config_path   = os.path.join(self.project_directory, 'tracking_config.yaml')

        # Create output directories (data/ must already exist with files in it)
        os.makedirs(self.analysis_path, exist_ok=True)
        os.makedirs(self.qc_path, exist_ok=True)

        self.config     = self._load_config()
        self.parameters = self._build_parameters()

        # facet_cutoffs can be set in global: as a list, e.g. facet_cutoffs: [10, 70]
        global_cfg = self.config.get('global', {})
        raw_cutoffs = global_cfg.get('facet_cutoffs', [10, 70])
        self.facet_cutoffs: tuple = tuple(raw_cutoffs) if isinstance(raw_cutoffs, list) else raw_cutoffs

        self.arena = Arena.Arena(
            self.parameters,
            data_path=self.data_path,
            force_preprocessing=force_preprocessing,
            config_path=self.config_path,
        )
        self.experimental_design = self.arena.experimental_design

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    def _plot_methods(self) -> list:
        """Return (method_name, kwargs) pairs for all relevant plots, with facet_cutoffs injected."""
        tt = self.parameters.get_tracking_type()
        base = _TRACKING_TYPE_PLOTS.get(tt, [])
        # Inject current facet_cutoffs into any method that accepts `cutoffs`
        result = []
        for name, kwargs in base:
            merged = dict(kwargs)
            if 'cutoffs' not in merged:
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

    def info(self) -> None:
        """Print a structured status overview of the experiment."""
        tt = self.parameters.get_tracking_type().name
        dq = self.arena.get_data_quality()
        n_total = len(self.arena.trackers)
        n_good  = int((dq['HighQuality'] >= 0.9).sum())
        t_min   = dq['StartMinutes'].min()
        t_max   = dq['EndMinutes'].max()
        global_cfg = self.config.get('global', {})

        print(f"Experiment   : {self.arena.experiment_name}")
        print(f"  Tracking type  : {tt}")
        print(f"  Tracking rig   : {global_cfg.get('tracking_rig', 'Unknown')}")
        print(f"  Trackers       : {n_good}/{n_total} with ≥90% data quality")
        print(f"  Data range     : {t_min:.1f} – {t_max:.1f} min")
        print(f"  Facet cutoffs  : {self.facet_cutoffs}")
        print(f"  Design loaded  : {self.experimental_design is not None}")
        print(f"  Analysis path  : {self.analysis_path}")
        print(f"  QC path        : {self.qc_path}")

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
        self.arena.print_short_data_quality_report(cutoff=cutoff)
        if save:
            dq   = self.arena.get_data_quality()
            path = os.path.join(self.qc_path, f"{self.arena.experiment_name}_data_quality.csv")
            dq.to_csv(path, index=False, na_rep='NA')
            print(f"Saved: {path}")

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
        if cutoffs is None:
            cutoffs = self.facet_cutoffs

        summary = self.arena.summarize()
        path = os.path.join(self.analysis_path, f"{self.arena.experiment_name}_Summary.csv")
        summary.to_csv(path, index=False, na_rep='NA')
        print(f"Saved: {path}")

        summary_facet = self.arena.summarize_facet(cutoffs=cutoffs)
        path_facet = os.path.join(self.analysis_path, f"{self.arena.experiment_name}_Summary_Facet.csv")
        summary_facet.to_csv(path_facet, index=False, na_rep='NA')
        print(f"Saved: {path_facet}")

        if copy_to_clipboard:
            summary_facet.to_clipboard(index=False, na_rep='NA')

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
        if cutoffs is None:
            cutoffs = self.facet_cutoffs

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
        if cutoffs is not None:
            # Temporarily override facet_cutoffs for _plot_methods()
            old_cutoffs = self.facet_cutoffs
            self.facet_cutoffs = tuple(cutoffs) if not isinstance(cutoffs, tuple) else cutoffs
        else:
            old_cutoffs = None

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
            if old_cutoffs is not None:
                self.facet_cutoffs = old_cutoffs

    def run_analysis(self, cutoffs=None, qc_cutoff: float = 0.9) -> None:
        """
        Run the complete analysis pipeline in one call.

        Order: QC report → summary CSVs → plots → statistics.

        Parameters
        ----------
        cutoffs :
            Facet cutoffs to use throughout. Defaults to ``self.facet_cutoffs``.
        qc_cutoff :
            Fraction threshold passed to :meth:`qc`.
        """
        if cutoffs is None:
            cutoffs = self.facet_cutoffs

        name = self.arena.experiment_name
        print(f"=== Running analysis for: {name} ===\n")

        print("--- Quality Control ---")
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
            f"  Facet cutoffs     : {self.facet_cutoffs}",
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


if __name__ == "__main__":
    project_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    exp = Experiment(project_dir)
    print(exp)
