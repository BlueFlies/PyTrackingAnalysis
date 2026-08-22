# Scripts and Script Editor

Scripts are saved, re-runnable recipes: an ordered list of steps such as load, filter, analyze, plot, and report. They can operate at either the experiment level or the Project level.

## Two script levels

- **Experiment Scripts** use experiment actions. They live in a replicate's `tracking_config.yaml` under `scripts:`, or centrally in a Project's `project.yaml` under `experiment_scripts:`.
- **Project Scripts** use Project actions. They live in `project.yaml` under `scripts:` and can create the Project report (which analyzes every replicate and pools the results), render publication figures, validate the design, and generate Project AI narratives.

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

The Project panel's **Script** picker runs Project Scripts from `project.yaml`, listing that file's own scripts first. Every Project is created with one already written there, named **`batch`** - the name says what it is for: it is the script a Batch run executes in this Project. It runs: create / update the Project report, then render publication figures. The report step is the whole **Create report** button - it analyzes every replicate and pools the results before building the PDF - which is why it comes first and why nothing else needs to precede it. The figure step skips itself when the Project has no `plot_specs.yaml`, so an unattended run never invents figures nobody curated. Because it lives in the file, you can open it in the Script Editor to see exactly what the default run does, and edit it. This is also what a Batch run executes by default (see the **Batch runs** help topic).

Two built-ins are listed below your own scripts as explicit choices. **Standard pipeline**: validate design, create the Project report, render publication figures. **Report pipeline**: the same, minus the `validate_design` gate.

## Two different scripts named `batch`

The name appears at both levels, and the level tells them apart:

- A **Project Script** named `batch`, in `project.yaml` under `scripts:`, is the default every Project is created with - what a Batch run executes in that Project.
- An **Experiment Script** named `batch`, in a replicate's `tracking_config.yaml` under `scripts:` (or centrally under `experiment_scripts:`), is the legacy name from the retired batch-over-experiments mode.

They never collide: each level reads its own section, and the levels do not mix. The legacy script is still useful for migration - create a Project around the old parent folder, then run a Project Script with `run_in_experiments` and `script: batch`. That action first looks in `project.yaml`'s `experiment_scripts:`, then falls back to each replicate's own `tracking_config.yaml`.
