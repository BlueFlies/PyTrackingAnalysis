# Outputs

PyTrackingAnalysis writes outputs at two levels: per-experiment outputs inside each replicate, and Project outputs at the Project root.

## Experiment outputs

For one loaded replicate, results are written relative to that Experiment Directory.

### `analysis/`

- `*_experiment_summary.txt` - rig, design, quality overview, and per-tracker table.
- `*_Summary.csv` - per-tracker summary statistics after any exclusions.
- `*_Summary_Facet.csv` - the same summaries split by `facet_cutoffs`.
- `*_Excluded.csv` - for Valence, flies removed by the low-transition exclusion.
- `*_Stats.txt` - faceted pairwise comparisons across treatments.
- `*_Stats_flat.txt` - flat pairwise comparisons when run without faceting.
- `*_plot_*.png` - saved experiment-level figures.
- `*_Notes.txt` - optional run notes entered from the Hub.
- `*_AI_Summary.txt` - optional experiment AI Summary; deleted by the next `run_analysis()`.

The experiment PDF report, `<experiment>_report.pdf`, is written to the Experiment Directory root beside `tracking_config.yaml`.

### `qc/`

- `*_data_quality.csv` - per-tracker fraction of high-quality, not-found, and indiscernible frames.

The QC Viewer also shows per-tracker diagnostic plots when you select a row.

## Project outputs

Project-level outputs are written at the Project root.

- `analysis/<project>_Summary.csv` - Combined Analysis: filtered replicate summaries stacked with an `Experiment` column.
- `analysis/<project>_Summary_Facet.csv` - combined faceted summaries, when available.
- `analysis/<project>_Excluded.csv` - excluded flies across replicates.
- `analysis/<project>_Stats.txt` - pooled per-fly tests plus mixed-model p-values that account for replicate-to-replicate variation.
- `analysis/<project>_AI_Summary.txt` - optional Project AI narrative; deleted by the next Combined Analysis build and then recreated by **AI narrative...** when requested.
- `plot_specs.yaml` - Plot Editor specs and styles.
- `figures/*.svg` and `figures/*.pdf` - pooled publication figures.
- `<project>_report.pdf` - Project Report with pooled figures, statistics, replicate summary, and any saved AI narrative. In the Hub, **Create report** / **Update report** refreshes all replicate analyses, rebuilds Combined Analysis, and then writes this PDF.

The Hub **Tools** panel opens `analysis/` and `qc/` for the currently selected directory. If a replicate is loaded, those buttons open the replicate folders; at a Project root, they open Project-level folders when they exist.
