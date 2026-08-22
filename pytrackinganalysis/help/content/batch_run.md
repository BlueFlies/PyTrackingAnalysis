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
- The **Script** picker holds the designated Project Script. **Each
  project's own script (default)** runs the script each Project carries in
  its own `project.yaml` — every Project is created with one, named **Report
  pipeline**: create / update the project report (the Create-report button in
  one step — analyze every replicate, pool, build the PDF) → render
  publication figures (skipped when the Project has no `plot_specs.yaml`).
  Because it
  lives in the file you can open it in the Script Editor, read exactly what
  a batch run will do, and change it per Project. **Report pipeline
  (built-in)**, **Standard pipeline (built-in)**, and any scripts in
  `batch.yaml`'s `project_scripts:` section are also listed as explicit
  choices; a saved designation naming a script the Projects define
  themselves stays listed too, shown as "(from each project)".
- **Run batch** runs the designated script in every checked Project — one
  at a time, in name order — continue-on-error with `[project]`-prefixed
  log lines and a summary at the end. It unloads the loaded experiment
  first — the run rewrites every replicate's analysis.
- **AI narrative of the batch** asks an AI provider, after the run, to
  synthesize the Projects' own narratives into `batch_ai_narrative.md` at the
  batch folder: results across the batch, Projects whose design looks
  compromised, and Projects that lost a lot of flies. Minor per-Project
  detail is left where it belongs, in each Project's own narrative. You pick
  the provider before the run starts (the same providers and models as the
  Project-level **AI narrative...**). Only Projects that succeeded are
  included, and the file's front matter names which ones they were.

  Note the interaction with the default script: `project_report` rebuilds
  each Project's Combined Analysis, and that **deletes** that Project's
  narrative. So a Project with no narrative left gets a fresh one generated
  first — one extra provider call per Project, each logged. A provider
  failure never fails the Batch Run itself; the run's own result stands.
- **Suppress new plot / output tabs** stops the output area opening a tab
  for every figure and every saved file. A Batch Run touches each replicate
  of each Project, so unchecked it can bury the Output tab under hundreds of
  them. The **Output** and **Errors** tabs keep updating as usual, and every
  figure and artifact is still written to disk — only the tabs are skipped.
  The switch applies to all runs while it is checked, not only Batch Runs.

## How the script resolves, per Project

1. `batch.yaml` `project_scripts:` — one recipe serving every Project,
   never copied into their `project.yaml`s.
2. The Project's own `scripts:` section.
3. The built-ins (Report pipeline, Standard pipeline).

With no designation (the default) a Project runs its own script — the one
named **`batch`**, or its first script if that one was renamed. A
Project whose `project.yaml` has no `scripts:` section **does not run**: it
is reported and skipped, and the run continues. There is no invisible
fallback — add a script in the Script Editor, or designate one above.

A name that resolves nowhere fails that Project; the run continues and the
summary says so. A Project that fails to load at all (say, a design
mismatch) is likewise recorded as that Project's failure, never the run's.
A Batch Run never creates or upgrades a `project.yaml`.

## batch.yaml

Optional, created only when needed: changing the Script picker away from the
default writes the designation (`script:`) there, and a `project_scripts:`
list can be added by hand. Leaving **Each project's own script** selected
never creates the file.

## Batch tools

The old **Batch tools** button now lives here, disabled — it predates the
Project structure and is being reworked.
