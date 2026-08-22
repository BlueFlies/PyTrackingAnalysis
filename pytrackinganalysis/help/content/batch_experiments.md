# Legacy batch and migration

The old Hub **Batch experiments** mode has been retired. The Project workflow replaces it with a clearer model: a parent folder has `project.yaml`, each subdirectory is a replicate Experiment Directory, and Project actions run or combine the set.

## What to use now

- **Run all experiments** runs the full analysis and per-replicate report for every configured replicate.
- **Build combined analysis** pools the already-filtered replicate summaries into the Project `analysis/` folder and writes pooled plus mixed-model statistics.
- **Project report** builds the Project-level PDF.
- **Standard pipeline** in the Project Script picker runs the usual full Project sequence with one click.

## Migrating an old batch parent

1. Open the old parent folder in the Hub.
2. Use **Create project** or **Create config...** to write `project.yaml`.
3. Confirm the shared design in the Project editor. The dialog can infer it from the first existing replicate config.
4. Use **Experiment configs...** for any subfolder that has data but no `tracking_config.yaml`.
5. Use **Run all experiments** or the built-in **Standard pipeline**.

## Existing `batch` scripts

Old per-folder scripts named `batch` can still run. Create a Project Script containing `run_in_experiments` with `script: batch`. It resolves the script from the Project's central `experiment_scripts:` first, then falls back to each replicate's own `tracking_config.yaml`.

## Python batch helper

The Python API still includes `batch_analyze(parent_folder)`. It scans immediate subdirectories and runs the fixed experiment pipeline in each one. It does not need `project.yaml`, and it does not build Combined Analysis or a Project Report.
