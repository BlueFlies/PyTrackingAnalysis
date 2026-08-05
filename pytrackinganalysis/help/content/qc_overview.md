# QC Viewer

Use the QC Viewer to inspect tracking quality before trusting summaries and plots.

## How to open

- Hub **Project → QC viewer…**, or
- `pytrack-qc /path/to/MyExperiment`

## Trackers table

Columns typically include `Tracker`, `HighQuality`, `NotFound`, `Indiscernible`, `StartMinutes`, `EndMinutes`.

Rows tint by %HighQuality against the project’s QC cutoff:

- **Green** — passes the cutoff
- **Yellow** — within one band below the cutoff
- **Red** — fails

Filter the table by tracker name. Exact thresholds appear under the table.

## Plots

Select a tracker to fill the plot dock:

- **XY trajectory** — position coloured by time
- **Total distance over time** — cumulative distance
- **X / Y vs time** — position timelines
- **Data quality timeline** — per-frame quality categories

## Export

**Export data_quality.csv** writes the full table for external review (also produced under `qc/` when you run QC from the Hub).
