# Scripting goes two-level: one language, separate registries per level

## Context

Scripts were experiment-scoped: step lists in `tracking_config.yaml`,
dispatched through one action registry, authored in the visual Script Editor,
with a legacy convention that batch mode ran a script named `batch` from each
subdirectory's own config. Projects (ADR-0005) need scripting too — partly
pass-through ("run this in every replicate"), partly genuinely project-level
work (combined analysis, pooled publication figures, the Project Report, the
AI narrative).

## Decision

- **One script language, two registries.** Project Scripts live in
  `project.yaml` `scripts:` with the SAME `{name, steps:[{action, params}]}`
  shape as experiment scripts — one visual editor, one yaml splicer — but
  dispatch through a separate project-action registry with a
  `ProjectRunContext` (holds the loaded `Project`, not an `Experiment`).
  Levels cannot mix by construction; a level-tagged shared registry was
  rejected because every palette, validator, and runner would grow
  level-awareness and hand-edited configs could smuggle wrong-level steps.
- **The bridge is one explicit action.** `run_in_experiments(script: NAME)`
  runs an *experiment-level* script in every replicate: resolved first from
  the Project's central `experiment_scripts:` section (design-authority
  spirit — one recipe, never copied into replicate configs), falling back to
  a script of that name in each replicate's own `tracking_config.yaml`
  (which also absorbs the legacy `batch` convention:
  `run_in_experiments(script: batch)` runs an old batch parent unchanged).
  Execution is replicate-by-replicate with per-replicate log prefixes and
  continue-on-error, failures summarized — the `run_all` semantics. Inline
  nested steps were rejected (canvas-in-canvas editing, no reuse).
- **Initial project-action roster** — thin wrappers over existing, tested
  `Project` methods: `validate_design`, `run_in_experiments`,
  `run_all_analyses`, `build_combined_analysis`,
  `render_publication_figures` (SVG/PDF from `plot_specs.yaml` over the
  pooled data), `project_report`, `generate_ai_narrative` (soft-fail: a
  provider error logs and continues rather than killing a pipeline). No
  shell escape hatch — scripts stay safe to run on sight.
  *(Amended by ADR-0009, 2026-08-22: `run_all_analyses` and
  `build_combined_analysis` were folded into `project_report`, which is now
  the whole Create-report button. A script action mirrors a Project-card
  button, and neither had one.)*
- **Authoring and running.** The existing Script Editor opens `project.yaml`
  with a level switcher: the project `scripts:` (project palette) and the
  central `experiment_scripts:` (the familiar experiment palette). The Hub's
  Project card gains a script picker + Run + Edit scripts….
- **A built-in "Standard pipeline"** (validate design → run all analyses →
  build combined analysis → render publication figures → project report)
  always appears in the picker and is never written to yaml, so zero
  authoring yields a complete run and the default tracks the shipped
  pipeline. The old per-subdir batch runner method is retired.

## Consequences

- `project.yaml` gains two sections (`scripts:`, `experiment_scripts:`);
  both ride the existing preserve-unknown-keys write path.
- The Script Editor becomes level-aware but stays one app with one canvas;
  experiment-level scripting inside a replicate's config is untouched.
- A future project-level action is one registry entry wrapping a `Project`
  method — the same extension pattern as experiment actions.
- `run_in_experiments` loads each replicate fresh; long projects pay N load
  times per bridge step, the price of isolation between replicates.
