# Project actions

The Project panel's **Analysis** card runs work across the replicate set. Use it after the Project has a valid `project.yaml` and each replicate has a configured `tracking_config.yaml`.

## Replicate table

The table shows each configured replicate plus any data-looking folder that is still missing a config.

- **Config** is `yes` or `missing`.
- **Flies** is the analyzed fly count, `not analyzed`, or `no data`.
- **Excluded** and **Flagged** show Valence quality results when available.
- **Report** shows whether the per-replicate PDF exists.

Double-click a configured row to load that replicate and run QC. Double-click a missing-config row to create its config from the Project design.

## Setup actions

- **Experiment configs...** opens the config manager for all immediate subdirectories. Create missing configs, create all missing configs, or open an existing replicate in the Config Editor.
- **Add experiment...** creates a new replicate directory and scaffolds its config from `project.yaml`.

## Project pipeline

Recommended order:

1. **Run all experiments** - runs each replicate's analysis and per-replicate report. The Hub unloads any currently loaded replicate first so it cannot keep stale in-memory results.
2. **Build combined analysis** - stacks analyzed replicate summaries into Project-level CSVs and writes pooled plus mixed-model statistics under `<project>/analysis/`.
3. **Plot editor...** - opens the Project-level publication figure editor, using the combined faceted data.
4. **AI narrative...** - optional; writes a Project AI narrative from Combined Analysis.
5. **Project report** - builds `<project>/<project>_report.pdf`.

`Build combined analysis` does not silently run missing replicates. It reports missing analyses and builds from the summaries that exist. Rebuilding combined analysis deletes any saved Project AI narrative because the narrative describes one specific combined result.

## Project scripts

The Project **Script** picker runs Project Scripts from `project.yaml`. **Standard pipeline (built-in)** is always available and runs:

1. validate design
2. run all analyses
3. build combined analysis
4. render publication figures
5. create Project report

Use **Edit scripts...** to author custom Project Scripts or centrally held Experiment Scripts.
