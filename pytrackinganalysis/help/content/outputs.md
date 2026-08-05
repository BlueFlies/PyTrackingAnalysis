# Outputs

All outputs are written relative to the project directory. Open them from the Hub **Tools** card (**Open analysis folder** / **Open qc folder**).

## `analysis/` — main results

- `*_experiment_summary.txt` — rig, design, quality overview, per-tracker table
- `*_Summary.csv` — per-tracker summary statistics
- `*_Summary_Facet.csv` — same, split by `facet_cutoffs` phases
- `*_Stats.txt` — pairwise comparisons across treatments (Welch t-test or Tukey HSD)
- `*_plot_*.png` — saved figures named after each plot method
- `*_report.pdf` — multi-page PDF: summary → QC → tracker grids → plots

## `qc/` — data quality

- `*_data_quality.csv` — per-tracker fraction of valid frames; trackers below the QC cutoff are flagged

Faceted runs and scripts write into the same folders. Batch parent tools can **Combine summary CSVs** across subfolders into combined files at the parent root.
