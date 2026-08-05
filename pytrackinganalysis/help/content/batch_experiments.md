# Batch experiments

In **Batch experiments** mode the chosen project directory is treated as a **parent folder**: every immediate subdirectory is run as its own independent experiment. Click **Run batch script** (the Load button changes its label in batch mode) to start.

## Each subfolder needs

- a `tracking_config.yaml` (any capitalisation) with the usual experiment configuration, and
- inside that YAML, a `scripts:` entry containing a script named **`batch`** (case-insensitive).

## What runs

For each subfolder, only its script named `batch` is executed, with that subfolder as the project directory. A `load_experiment` step with `path: "."` loads the subfolder’s own data. Scripts are authored in the Script Editor (Config Editor → Script Editor) and saved into each subfolder’s YAML.

## Skips and failures

- No `tracking_config.yaml` → subfolder is skipped with a warning in the Output tab.
- YAML has no script named `batch` → skipped with a warning.
- A script error in one subfolder is logged; the remaining subfolders still run.

When finished, a summary line reports how many subfolders ran, were skipped, or failed. Figures the scripts produce open as plot tabs.

**Batch tools** (Tools card) helps prepare parent folders: convert to `data/` layout, rename subdirs, copy YAML, combine summary CSVs.
