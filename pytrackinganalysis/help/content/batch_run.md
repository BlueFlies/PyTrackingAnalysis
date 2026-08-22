# Batch runs

A **Batch** is a folder whose immediate subdirectories are Projects. Nothing
marks it — choose such a folder with the Batch panel's own **Choose batch
folder…** button (or Project tile → **Load…**) and the **Batch** tile lights
up with every Project inside it auto-loaded into the table; select a single
Project and the Batch tile dims instead. A
Batch is a processing convenience: it runs many Projects unattended and
reports per-Project success or failure. It never pools results across
Projects — each Project keeps its own design and its own outputs.

## The Batch panel

- The **projects table** lists every Project in the folder (subdirectories
  without a `project.yaml` are skipped, with a log line during a run).
  Checked rows join the next run — all are checked by default, so re-running
  one failed Project is two clicks. **Double-click a row to select that
  Project**: the strip switches to it, exactly as if you had loaded its
  folder. There is no "up to batch" button — to return, load the Batch
  folder again.
- The **Script** picker holds the designated Project Script. **Report
  pipeline (built-in)** is the default: run all analyses → build combined
  analysis → render publication figures (only when the Project has a
  `plot_specs.yaml`) → project report — the Create-report button, as a
  script. **Standard pipeline (built-in)** and any scripts in `batch.yaml`'s
  `project_scripts:` section are also listed; a saved designation naming a
  script the Projects define in their own `project.yaml`s stays listed too,
  shown as "(from each project)".
- **Run batch** runs the designated script in every checked Project — one
  at a time, in name order — continue-on-error with `[project]`-prefixed
  log lines and a summary at the end. It unloads the loaded experiment
  first — the run rewrites every replicate's analysis.

## How the script resolves, per Project

1. `batch.yaml` `project_scripts:` — one recipe serving every Project,
   never copied into their `project.yaml`s.
2. The Project's own `scripts:` section.
3. The built-ins (Report pipeline, Standard pipeline).

A name that resolves nowhere fails that Project; the run continues and the
summary says so. A Project that fails to load at all (say, a design
mismatch) is likewise recorded as that Project's failure, never the run's.
A Batch Run never creates or upgrades a `project.yaml`.

## batch.yaml

Optional, created only when needed: changing the Script picker away from the
default writes the designation (`script:`) there, and a `project_scripts:`
list can be added by hand. Leaving the default (Report pipeline) selected
never creates the file.

## Batch tools

The old **Batch tools** button now lives here, disabled — it predates the
Project structure and is being reworked.
