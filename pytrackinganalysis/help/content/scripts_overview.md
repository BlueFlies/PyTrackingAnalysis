# Scripts and Script Editor

Scripts are saved, re-runnable recipes: an ordered list of steps such as load, filter, analyze, plot, and report. They can operate at either the experiment level or the Project level.

## Two script levels

- **Experiment Scripts** use experiment actions. They live in a replicate's `tracking_config.yaml` under `scripts:`, or centrally in a Project's `project.yaml` under `experiment_scripts:`.
- **Project Scripts** use Project actions. They live in `project.yaml` under `scripts:` and can run all replicates, build combined analysis, render publication figures, create Project reports, and generate Project AI narratives.

The levels do not mix. The bridge is the Project action `run_in_experiments`, which runs a named Experiment Script in every replicate. Its optional `only:` parameter lists replicate directory names to include - blank means all replicates, and when editing a `project.yaml` the editor shows it as a checkable replicate list. A name matching no replicate is logged and counted in the failure summary while the run continues. The Hub also pre-checks a Project Script before running it: an unknown `only:` name, or a script name that resolves nowhere it is asked to run, aborts with a message before anything executes.

## Opening the editor

- For a replicate's Experiment Scripts, open its config in **Config Editor** and click the scripts icon in the top bar.
- For Project Scripts or centrally held Experiment Scripts, use the Hub Project panel's **Edit scripts...** button. The editor opens on `project.yaml` and shows a level switcher.

## Editor panes

- **Palette** - available actions, filtered by tracking type where needed. Double-click an action to append a step.
- **Canvas** - ordered step cards with move, delete, and validation markers.
- **Inspector** - parameter form for the selected step.
- **Preview + Save** - live YAML preview; Save writes the script section back to the same YAML while preserving the rest of the file.

## Running experiment scripts

The Hub's **Scripts** tile lists scripts from the loaded replicate's own `tracking_config.yaml` only - centrally held Experiment Scripts never appear there; they run through the `run_in_experiments` bridge. A script can begin with **Load experiment**, or it can reuse the experiment already loaded in the Hub. Scripts run by `run_in_experiments` receive each replicate pre-loaded, so they usually do not need their own load step.

## Running Project scripts

The Project panel's **Script** picker runs Project Scripts from `project.yaml`. Two built-ins are always available. **Standard pipeline**: validate design, run all analyses, build combined analysis, render publication figures, and create the Project report. **Report pipeline**: run all analyses, build combined analysis, render publication figures only when the Project has a `plot_specs.yaml`, and create the Project report - the **Create report** button plus curated figures, and the default designated script for Batch runs (see the **Batch runs** help topic).

## Legacy batch scripts

A script named `batch` comes from the retired batch-over-experiments mode and is unrelated to the Hub's **Batch** tile, which runs a designated Project Script across many Projects (see the **Batch runs** help topic). The old script is still useful for migration: create a Project around the old parent folder, then run a Project Script with `run_in_experiments` and `script: batch`. The action first looks in `project.yaml`'s `experiment_scripts:`, then falls back to each replicate's own `tracking_config.yaml`.
