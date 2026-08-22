# Scripts and Script Editor

Scripts are saved, re-runnable recipes: an ordered list of steps such as load, filter, analyze, plot, and report. They can operate at either the experiment level or the Project level.

## Two script levels

- **Experiment Scripts** use experiment actions. They live in a replicate's `tracking_config.yaml` under `scripts:`, or centrally in a Project's `project.yaml` under `experiment_scripts:`.
- **Project Scripts** use Project actions. They live in `project.yaml` under `scripts:` and can run all replicates, build combined analysis, render publication figures, create Project reports, and generate Project AI narratives.

The levels do not mix. The bridge is the Project action `run_in_experiments`, which runs a named Experiment Script in every replicate.

## Opening the editor

- For a replicate's Experiment Scripts, open its config in **Config Editor** and click the scripts icon in the top bar.
- For Project Scripts or centrally held Experiment Scripts, use the Hub Project panel's **Edit scripts...** button. The editor opens on `project.yaml` and shows a level switcher.

## Editor panes

- **Palette** - available actions, filtered by tracking type where needed. Double-click an action to append a step.
- **Canvas** - ordered step cards with move, delete, and validation markers.
- **Inspector** - parameter form for the selected step.
- **Preview + Save** - live YAML preview; Save writes the script section back to the same YAML while preserving the rest of the file.

## Running experiment scripts

The Hub's **Scripts** tile lists scripts from the loaded replicate's `tracking_config.yaml`. A script can begin with **Load experiment**, or it can reuse the experiment already loaded in the Hub. Scripts run by `run_in_experiments` receive each replicate pre-loaded, so they usually do not need their own load step.

## Running Project scripts

The Project panel's **Script** picker runs Project Scripts from `project.yaml`. The built-in **Standard pipeline** is always available: validate design, run all analyses, build combined analysis, render publication figures, and create the Project report.

## Legacy batch scripts

A script named `batch` is no longer a special Hub mode. It is still useful for migration: create a Project around the old parent folder, then run a Project Script with `run_in_experiments` and `script: batch`. The action first looks in `project.yaml`'s `experiment_scripts:`, then falls back to each replicate's own `tracking_config.yaml`.
