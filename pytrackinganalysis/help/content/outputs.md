# Outputs

All outputs are written relative to the project directory. Open them from the Hub **Tools** panel (sidebar) (**Open analysis folder** / **Open qc folder**).

## `analysis/` — main results

- `*_experiment_summary.txt` — rig, design, quality overview, per-tracker table
- `*_Summary.csv` — per-tracker summary statistics
- `*_Summary_Facet.csv` — same, split by `facet_cutoffs` phases
- `*_Excluded.csv` — (Valence) flies removed by the low-transition exclusion (`min_transitions`, default 5, measured over the primary phase; 0 = off)
- Valence summary CSVs also carry a `LowMovementFlag` column: flies below `min_movement` (default 140 mm/min) in the first phase, flagged but kept; >50% flagged marks the experiment as potentially an issue
- `*_Stats.txt` — pairwise comparisons across treatments (Welch t-test or Tukey HSD)
- `*_plot_*.png` — saved figures named after each plot method
- `<project>_report.pdf` — the PDF report, written to the **project root** (beside the yaml): figures → stats table → experiment summary → QC
- `figures/` — publication figures saved by the Plot Editor (`pytrack-plots`): vector SVG (editable text in Illustrator) / PDF, regenerable from `plot_specs.yaml` in the project root

## `qc/` — data quality

- `*_data_quality.csv` — per-tracker fraction of valid frames; trackers below the QC cutoff are flagged

Faceted runs and scripts write into the same folders. Batch parent tools can **Combine summary CSVs** across subfolders into combined files at the parent root.
