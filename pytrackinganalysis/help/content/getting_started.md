# Getting started

PyTrackingAnalysis analyses insect-tracking data from DTrack. You configure one experiment with a `tracking_config.yaml`, then run summaries, plots, stats, and reports from the desktop apps.

## What you need

1. A **project directory** for the experiment.
2. A **`tracking_config.yaml`** at the top of that directory (not inside `data/`).
3. A **`data/`** folder with the DTrack export (`.xlsx` workbook + `*_Data_*.csv` files).

The pipeline creates `analysis/` and `qc/` on first run.

## First-time workflow

1. **Create / open the project folder** in the Analysis Hub (**Project → Browse…**).
2. **Edit the config** — Project card → **Edit config…**, or run `pytrack-config`. Set tracking type, rig, design factors, and regions.
3. **Load the experiment** — Hub **Load** card → **Single project** → **Load experiment**.
4. **Run analysis** — **Analyze → Run Analysis** (or open **Scripts** and run a saved recipe).
5. **Check quality** — **QC viewer…** or `pytrack-qc` for per-tracker quality and trajectories.

## Apps

- **Analysis Hub** (`pytrack` / `pytrack-hub`) — day-to-day load, analyze, plots, scripts, batch.
- **Config Editor** (`pytrack-config`) — YAML forms + Script Editor.
- **QC Viewer** (`pytrack-qc`) — data-quality table and tracker plots.

Use the **?** buttons next to controls for topic-specific help. This Help window lists every topic in the sidebar.
