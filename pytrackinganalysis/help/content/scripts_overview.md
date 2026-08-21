# Scripts and Script Editor

Scripts are saved, re-runnable analysis recipes: an ordered list of steps stored under `scripts:` in `tracking_config.yaml`.

## Concepts

- A **script** is `{name: "...", steps: [...]}`.
- A **step** is one action plus parameters, e.g. `{action: run_analysis, params: {facet: true}}`.
- Steps run **top to bottom**. `load_experiment` sets the current experiment; later steps use it. Filters change the in-memory experiment only (not files on disk).
- The name **`batch`** (any capitalisation) is reserved for Hub **Batch experiments** mode.

## Opening the editor

Config Editor → scripts icon in the top bar. Non-modal: keep Hub / Config open beside it. Plot actions offered depend on `global.tracking_type`.

## Panes

- **Palette** — double-click an action to append a step.
- **Canvas** — ordered step cards; move / delete; click to select.
- **Inspector** — parameters for the selected step.
- **Preview + Save** — live YAML; Save writes all scripts back into the config file.

## First script

1. New script (e.g. `full-run`).
2. **Load experiment** with project dir `.`.
3. Optional **Filter trackers by quality** (e.g. min high-quality 0.9).
4. **Run Full Analysis** (faceted if desired).
5. Optional **Create report** / plot steps.
6. Save, then run from the Hub **Scripts** card.

## Running from the Hub

**Scripts** card lists recipes from the active YAML. **Run Script** / **Run All** streams logs to Output and figures to plot tabs. In batch mode, only the script named `batch` runs per subfolder.


## Project scripts

A Project's `project.yaml` holds **Project Scripts** (`scripts:`, project-level actions: run in experiments, combined analysis, publication figures, project report, AI narrative) and centrally-held **Experiment Scripts** (`experiment_scripts:`) that `run_in_experiments` executes in every replicate (each replicate's own scripts are the fallback). The level switcher in this editor's top bar picks which list you are editing. The Hub's Project card runs them — including the built-in **Standard pipeline**.
