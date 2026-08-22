# Getting started

PyTrackingAnalysis analyses insect-tracking data from DTrack. You configure one experiment with a `tracking_config.yaml`, then run summaries, plots, stats, and reports from the desktop apps.

## What you need

1. A **Project directory** with a `project.yaml`, holding one subdirectory per experiment.
2. A **`tracking_config.yaml`** at the top of each experiment subdirectory (not inside `data/`).
3. A **`data/`** folder in each, with the DTrack export (`.xlsx` workbook + `*_Data_*.csv` files).

The pipeline creates `analysis/` and `qc/` on first run.

## First-time workflow

1. **Open the folder** in the Analysis Hub (**Project → Browse…**). Tiles across the top show live status; every tile opens its controls in a drop-down panel.
2. **Make it a Project** — Project tile → **Create config…** writes the `project.yaml` and opens the Project editor, where you set the shared design. (Pointing at a folder that is itself an experiment offers to create the Project on its parent instead.)
3. **Give each experiment a config** — **Experiment configs…** in the Analysis card creates them from the project design; edit one in `pytrack-config` to assign region treatments and the rig.
4. **Load an experiment** — **double-click its row** in the replicates table. That is the only way in, and it runs QC as it loads.
5. **Run analysis** — **Analyze → Run Analysis** (or open **Scripts** and run a saved recipe).
6. **Check quality** — the QC Viewer opens on load; `pytrack-qc` reopens it later.

## Apps

- **Analysis Hub** (`pytrack` / `pytrack-hub`) — day-to-day load, analyze, plots, scripts, batch.
- **Config Editor** (`pytrack-config`) — YAML forms + Script Editor.
- **QC Viewer** (`pytrack-qc`) — data-quality table and tracker plots.

Use the **?** buttons next to controls for topic-specific help. This Help window lists every topic in the sidebar.
