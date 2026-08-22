# QC Viewer

Use the QC Viewer to inspect per-tracker data quality before trusting summaries, plots, and reports.

## Opening it

- The Hub opens QC automatically after a replicate loads successfully.
- Run `pytrack-qc /path/to/ExperimentDirectory` to reopen it later.

QC is experiment-level. Point it at the directory that contains `tracking_config.yaml` and `data/`.

## Trackers table

Typical columns include `Tracker`, `HighQuality`, `NotFound`, `Indiscernible`, `StartMinutes`, and `EndMinutes`.

Rows are tinted against the experiment's QC cutoff:

- **Green** - passes the cutoff.
- **Yellow** - within the warning band below the cutoff.
- **Red** - fails the cutoff.

The exact thresholds are shown under the table. The filter box narrows rows by tracker name.

## Diagnostic plots

Select a tracker to update the plot tabs:

- **XY trajectory** - position colored by time.
- **Total distance over time** - cumulative distance through the recording.
- **X / Y vs time** - position timelines.
- **Data quality timeline** - frame-by-frame quality categories.

## Export

**Export data_quality.csv** writes the current table for external review. Running QC from the Hub also writes `qc/<experiment>_data_quality.csv`.
