# Legacy batch migration

The old Hub **Batch experiments** mode - the batch-over-experiments mode - has been retired. The Project workflow replaces it with a clearer model: a parent folder has `project.yaml`, each subdirectory is a replicate Experiment Directory, and Project actions run or combine the set.

This page is about that retired mode only. The Hub's **Batch** tile is something else entirely: it runs many Projects at once. See the **Batch runs** help topic.

## What to use now

- **Create report** / **Update report** runs every replicate, rebuilds Combined Analysis, and writes the Project-level PDF.
- **Plot editor...** uses the Combined Analysis created by the report refresh to curate publication figures.
- **Standard pipeline** in the Project Script picker runs the usual full Project sequence with one click.

## Migrating an old batch-over-experiments parent

1. Open the old parent folder in the Hub.
2. Use **Create project** or **Create config...** to write `project.yaml`.
3. Confirm the shared design in the Project editor. The dialog can infer it from the first existing replicate config.
4. Use **Experiment configs...** for any subfolder that has data but no `tracking_config.yaml`.
5. Use **Create report** or the built-in **Standard pipeline** for a full Project refresh.

## Existing `batch` scripts

Old per-folder scripts named `batch` can still run. Create a Project Script containing `run_in_experiments` with `script: batch`. It resolves the script from the Project's central `experiment_scripts:` first, then falls back to each replicate's own `tracking_config.yaml`. The optional `only:` parameter limits the run to the listed replicate directory names; leave it blank to run all replicates. The Hub pre-checks the script before starting, so a mistyped replicate name or a script name that resolves nowhere aborts before anything runs.

## Python batch helper

The Python API still includes the legacy `batch_analyze(parent_directory)` helper. It scans immediate subdirectories and runs the fixed experiment pipeline in each one. It does not need `project.yaml`, and it does not build Combined Analysis or a Project Report. It is unrelated to the Hub's Batch runs, which run a designated Project Script across many Projects.
