# Batch + scripting implementation plan (merged)

Working plan merging the 2026-08-21 grilling session (decisions in
CONTEXT.md and ADR-0009) with the sibling session's completed work. Delete
once shipped. Decisions live in the ADRs; this file is only the remaining
work.

**STATUS 2026-08-21: Lanes 1 and 2 are IMPLEMENTED and green (full suite:
452 passed).** New code: `pytrackinganalysis/batch.py` (detection,
batch.yaml IO, resolution, Batch Run executor), Batch tile/panel/state in
`apps/hub.py`, `REPORT_PIPELINE` + `report_pipeline_for` + `only:` +
`preflight_project_script_issues` in `script_editor/project_actions.py`,
the `multilist` inspector kind fed by `window.py`, the `batch_run` help
topic, and tests (`tests/test_batch.py`, extended `test_hub_tiles.py` /
`test_project_scripts.py`). Since then: full docs/help sweep done (guide
§8.5, all 16 help pages audited against code), question-mark help buttons on
every card/dialog, a Choose-batch-folder picker on the Batch panel, and an
adversarial review pass whose confirmed findings are fixed and pinned by
tests (preflight hardened against lenient script shapes; empty-error-message
summary guards; central-first designation resolution pinned — it was once
flipped on disk without attribution). Final suite: 466 passed. Lane 3
(Batch tools rework) remains parked.

## Already done (verified in repo)

- Two-level scripting (ADR-0006) fully implemented: `PROJECT_ACTIONS`
  (validate_design, run_in_experiments with central-first resolution and
  continue-on-error, run_all_analyses(skip_analyzed), build_combined_analysis,
  render_publication_figures(format), project_report, generate_ai_narrative),
  the Standard Pipeline built-in, and the Hub's Project-panel script picker.
- Project-first Hub (ADR-0008); Scripts tile lists only the loaded
  experiment's own `scripts:` (confirmed deliberate — central
  `experiment_scripts:` run solely via the bridge).
- ADR-0009 written and refined (Report Pipeline default, checkable projects
  table, name-order execution, Batch Tools disposition); CONTEXT.md carries
  Batch / Batch Run / Report Pipeline and the sharpened script entries.
- Help/guide wording updates from the sibling session's commits
  ("more progress" ×2).
- Confirmed no-ops: report + publication-figure script actions already cover
  Scott's plan items; "update report" semantics = run_all_analyses with
  skip_analyzed. Whole-set figure rendering is enough — no per-figure param.

## Lane 1 — Batch level (ADR-0009 contract; not started)

1. Selection model: `_set_project_dir` stops at a Batch root; selection kind
   Batch|Project drives tile dimming (Batch selected → Project-and-below dim
   with "select a project"; Project selected → Batch tile dims).
2. Batch tile, leftmost (strip: Batch · Project · Analyze · Plots · Scripts ·
   AI) + anchored panel: projects table (checkable rows, all on by default,
   name order; double-click = ordinary selection change down to that
   Project), script picker, Run batch.
3. Report Pipeline built-in (code-defined): run all analyses → build combined
   analysis → render publication figures *only if `plot_specs.yaml` exists* →
   project report. Needs the conditional-skip mechanism (in the built-in or
   the figure action).
4. `batch.yaml` read/write: `script:` designation + central
   `project_scripts:`; preserve-unknown-keys write path; file appears lazily.
5. Batch Run executor: designated-script loop over checked Projects —
   resolution central → each Project's own `scripts:` → built-ins (Report,
   Standard); never creates/upgrades `project.yaml`; non-Projects skipped
   with a log line; continue-on-error with per-Project prefixes; unloads the
   loaded experiment first; per-Project run summary in the output area.
6. Status readout Batch form: batch path, N projects, designated script.
7. Batch Tools launcher: move from the Tools tile into the Batch panel,
   disabled (rework parked — see Lane 3).
8. Legacy "batch" wording sweep: finish once the tile ships (batch_tools.md,
   hub_workflow.md, guide §5.x) so "Batch" means only the new level.
9. Optional Python helper: project-level equivalent of `batch_analyze`
   wrapping the same loop.
10. Tests: batch detection (structural, non-Project children), resolution
    order incl. built-ins, never-upgrade rule, checkable-subset run, unload
    on run, tile dim states, `_set_project_dir` normalization stopping at
    Batch root.

## Lane 2 — Targeted bridge (`only:`; not started)

1. `run_in_experiments` gains optional `only:` (list of replicate directory
   names); absent/empty = all replicates — existing scripts untouched.
2. Executor filters `project.experiment_names` by `only:`; resolution and
   miss handling unchanged (central first, own fallback; a miss logs
   SKIPPED, lands in the failure summary, run continues).
3. Validation: `_validate_run_in_experiments` accepts the param; pre-run
   check with a Project in hand flags unknown replicate names and script
   names that resolve nowhere (central + named replicate's config +
   built-ins considered).
4. Script Editor inspector: replicate multi-picker for the param when a
   Project is open.
5. Help (project_actions.md) + tests: targeted subset runs, unknown-name
   validation, miss-is-loud behavior.

## Lane 3 — Parked (do not start without Scott)

- Batch Tools rework for the new directory structure (Scott: "we will
  return to that later"). Until then: button lives in the Batch panel,
  disabled.

## Open flags for Scott

- Report Pipeline default — RESOLVED, no veto needed: Scott sanctioned it
  twice in the sibling session ("This is what I would like the default batch
  to do", then explicitly chose it over a Standard Pipeline default when the
  conflict with the ADR draft was surfaced).
- Report Pipeline picker visibility — RESOLVED (Scott, 2026-08-21): it
  appears in BOTH pickers, Project panel and Batch panel, beside the
  Standard Pipeline. Built-ins are context-free. (Adds a small item to
  Lane 1 step 3: register it in the Project panel picker too.)
