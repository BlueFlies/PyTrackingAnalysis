# Getting started

PyTrackingAnalysis analyzes insect-tracking data exported from DTrack. The Hub is now Project-first: a **Project** is a parent directory with a `project.yaml`, and each replicate is an **Experiment Directory** underneath it.

## What you need

1. A **Project directory** with `project.yaml`. This file holds the shared design: experiment type, factors and levels, facets, quality criteria, and counting-region names.
2. One **Experiment Directory** per replicate. Each one has a top-level `tracking_config.yaml` with the rig, tracking-region treatment assignments, counting-region aliases, and optional experiment scripts.
3. A `data/` folder inside each Experiment Directory, containing the DTrack workbook (`.xlsx`) and its `*_Data_*.csv` files.

The pipeline creates `analysis/` and `qc/` folders when it writes results.

## First-time workflow

1. Open the **Analysis Hub** (`pytrack`) and choose the parent folder from **Project -> Browse...**.
2. Make or edit the Project: **Project -> Create/Load -> Create config...** writes `project.yaml` and opens the Project editor. If you point at a folder that is already an Experiment Directory, the Hub offers to create the Project on the parent so that experiment becomes a replicate.
3. Add or adopt replicates from the Project panel's **Analysis** card. Use **Add experiment...** for a new replicate directory, or **Experiment configs...** to create missing `tracking_config.yaml` files from the project design.
4. Finish each replicate config in the Config Editor: choose the rig, assign every tracking region to the design factors, and check counting-region aliases.
5. Load a replicate by **double-clicking its row** in the Project table. This is the Hub's only experiment-loading path, and it runs QC as the experiment loads.
6. Run a single replicate from **Analyze -> Run Analysis**, or run the whole study from the Project panel with **Run all experiments** followed by **Build combined analysis** and **Project report**.

## Apps

- **Analysis Hub** (`pytrack` / `pytrack-hub`) - day-to-day Project workflow: load replicates, run analyses, view plots, build combined results, run Project scripts.
- **Config Editor** (`pytrack-config`) - structured editor for each replicate's `tracking_config.yaml`, plus the Script Editor for experiment scripts.
- **QC Viewer** (`pytrack-qc`) - per-tracker data-quality table and diagnostic plots for one Experiment Directory.

Use the **?** buttons next to controls for topic-specific help. The top-bar **Help** button opens the full help browser.
