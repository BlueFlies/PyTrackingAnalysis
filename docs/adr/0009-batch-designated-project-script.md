# Batch mode is a designated Project Script over a structural Batch

## Context

Projects (ADR-0005) replaced the old batch-over-experiments mode, and
ADR-0006 absorbed its legacy `batch`-script convention into
`run_in_experiments`. But labs accumulate many sibling Projects and want them
analyzed unattended — a batch *of Projects*, one level above everything
scripting currently reaches. The Hub is Project-first (ADR-0008) with a
five-tile strip whose selection invariantly names a Project.

## Decision

- **A Batch is structural, and a processing convenience only.** A directory
  whose immediate subdirectories hold a `project.yaml` is a Batch — the
  Project↔Experiment rule one level up. Only existing Projects qualify: a
  Batch Run never creates or upgrades a `project.yaml`, and non-Project
  children are skipped with a log line. No marker file is required to run
  one: `project.yaml` exists because a design authority must be declared, and
  a Batch has no authority to declare. A `batch.yaml` appears lazily, only
  once batch-level scripting is authored. A Batch never pools results across
  Projects (each has its own design); its only output is a per-Project run
  summary. A required marker ("Create batch…" first) and a manifest of
  arbitrary Project paths were both rejected.
- **There is no third script level.** Batch mode runs one **designated
  Project Script** in every Project — continue-on-error, per-Project log
  prefixes, failures summarized at the end (the `run_in_experiments`
  semantics one level up). The default designation is a new built-in, the
  **Report Pipeline**: run all analyses → build combined analysis → render
  publication figures *only when the Project has a `plot_specs.yaml`* →
  project report. That is the Hub's Create report button plus curated
  figures, so zero authoring makes a batch run mean "press Create report on
  every Project". The Standard Pipeline was rejected as the default (it
  stays available in the picker): its `validate_design` gate would fail
  Projects mid-migration, and its unconditional figure step renders
  default-spec figures nobody curated — wrong for an unattended run over
  many Projects. A batch-action registry was rejected: its roster today would be exactly one action
  (`run_in_projects`), so every batch script would be one step long —
  machinery with no second use case. If a genuine second batch-level action
  ever appears, ADR-0006's one-language/segregated-registry pattern extends
  naturally.
- **`batch.yaml` holds the designation and central Project Scripts.**
  `script:` names the designated Project Script; `project_scripts:` centrally
  holds Project Scripts that serve every Project without being copied into
  their `project.yaml`s — the `experiment_scripts:` idea one level up.
  Resolution order for the designation: the Batch's central
  `project_scripts:`, then each Project's own `scripts:`, then built-ins
  (Report Pipeline, Standard Pipeline). A Project where the name resolves nowhere fails that
  Project; the run continues and the summary says so.
- **The selection now names a Batch or a Project — still exactly one job.**
  The strip regains a sixth tile, leftmost: **Batch · Project · Analyze ·
  Plots · Scripts · AI**, reading left-to-right down the containment
  hierarchy. Selecting a Batch lights the Batch tile (projects table, script
  picker, Run batch) and dims the Project-and-below tiles ("select a
  project"); selecting a Project dims the Batch tile. Double-clicking a row
  in the projects table is an *ordinary selection change* down to that
  Project — not ADR-0008's drill-in disease, because the selection still does
  one job (name the working container) and no second context is created;
  there is consequently no "up to batch" button, exactly as there is no "up
  to project" one. A batch-run dialog (no state change) and a
  parent-sniffing Batch tile on a Project selection were rejected.
- **A batch run unloads first and runs Projects sequentially, in name
  order.** It rewrites every replicate's analysis in every Project, so the
  loaded experiment is unloaded for ADR-0008's staleness reason. Sequential
  execution matches `run_in_experiments` and keeps the log readable. The
  Batch panel's projects table is checkable (all rows on by default), so
  re-running one failed Project is two clicks, not a directory reshuffle.

## Amendment (2026-08-22): every project.yaml ships a default Project Script

The built-in default was invisible. A user reading their `project.yaml` saw no
`scripts:` block and had no way to learn what a Batch Run would do to their
Project, let alone adjust it — the Report Pipeline existed only in code.

- **`create_project_file` seeds `scripts:` with the default Project Script**
  (the Report Pipeline's steps, named **`batch`** — it is the script a Batch
  Run executes here, and naming it after the built-in hid that — carrying a `notes:`
  line saying where it came from). It is written into the file, so it is
  visible in the Script Editor, editable, and renameable. A `project.yaml`
  whose block is absent is seeded on the next write; an authored block is
  left untouched.
- **No designation now means "each Project's own script", and there is no
  implicit fallback.** `resolve_designated_script(None, …)` takes the
  Project's script named `batch`, else its first authored script.
  A Project whose `scripts:` is empty **does not run**: it fails that Project
  with a message naming the Script Editor, and the Batch Run continues. The
  built-ins remain resolvable *by name* — an explicit designation is a user
  choice, not a silent substitution — and stay in both Hub pickers.
- **The conditional figure step moves into the action.**
  `render_publication_figures` now skips itself (with a log line) when the
  Project has no `plot_specs.yaml`, so the materialized default script is as
  safe for an unattended run as the code-defined built-in was.
  `report_pipeline_for` still pre-drops the step for the built-in path, which
  is what produces the up-front note.
- The Project card's picker lists the Project's own scripts **first** and
  opens on one; the Batch panel's picker gains a leading "Each project's own
  'batch' script (default)" entry, which stores no designation (the
  lazy-marker rule is unchanged). The seeded script is named `batch`, not
  after the built-in: it is the script a Batch Run executes, and the name
  says so. The legacy `batch` EXPERIMENT script (ADR-0006) is a different
  level reading a different yaml key, so the names cannot collide.

### A script action mirrors a button

Writing the default script into `project.yaml` exposed a mismatch it had been
possible to ignore while the default lived in code: the script registry
offered `run_all_analyses` and `build_combined_analysis` as separate steps,
but the Project card has no Run-all and no Build-combined button. The
Create-report button (`hub._project_report`) has always run all three calls —
`run_all()`, `build_combined_analysis()`, `create_report()` — so a user
reading the seeded script saw three steps for what is one click.

- **`project_report` becomes the whole button**, same three calls in the same
  order, with the button's own defaults (`reports=True`,
  `skip_analyzed=False`) exposed as params. Like the button, a replicate
  failure stops it before pooling.
- **`run_all_analyses` and `build_combined_analysis` are removed** from the
  registry. The rule going forward: a project action mirrors a Project-card
  button, so the script language cannot drift from the UI.
- **Saved scripts naming them still run.** `absorb_legacy_steps` drops the
  retired step when the script already has a `project_report`, and promotes
  it to `project_report` when it does not — absorbing must never turn a
  script into a no-op. The replacement inherits the *position* of the first
  step it absorbs, so a later `render_publication_figures` still finds
  analyzed replicates. The Script Editor flags the steps for cleanup rather
  than calling them unknown.
- The built-in pipelines lose those steps and put figures **after** the
  report, for the same ordering reason.

## Consequences

- Selection normalization (`_set_project_dir`) must stop at a Batch root
  instead of insisting on a Project root; the status readout gains a Batch
  form (batch path, N projects, designated script).
- "Batch" wording from the retired mode must be swept from help/UI so the
  word means only this level. **Batch Tools** collides head-on (it iterates
  a *Project's* subdirectories) and predates the Project structure: its
  launcher moves into the Batch panel and is disabled, pending a rework.
- The Report Pipeline's conditional figure step needs the figure action (or
  the built-in itself) to learn "skip when no `plot_specs.yaml`"; built-ins
  are code-defined, so the conditionality never appears in yaml.
- `batch.yaml` rides the same preserve-unknown-keys write path as
  `project.yaml`.
- The Script Editor is untouched: nothing new to author beyond Project
  Scripts it already edits. The Hub's Batch panel needs only a picker whose
  list is central + built-in Project Scripts.
- The Python `batch_analyze(parent)` helper (experiment-level, pre-Project)
  is unchanged; a Project-level equivalent can wrap the same designated-script
  loop.
