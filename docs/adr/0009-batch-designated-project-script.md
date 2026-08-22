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
