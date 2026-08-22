# The Hub is Project-first: experiments load from the replicates table

## Context

ADR-0007 gave the Hub six tiles, Project and Experiment among them. That left
two ways to reach an experiment and two places that owned "which experiment am
I working on":

- The Project panel's replicates table, whose double-click only *selected* a
  replicate directory, and
- the Experiment panel, whose **Load experiment** button then loaded whatever
  directory happened to be selected.

Loading a replicate therefore took two clicks in two different panels, and the
Project and Experiment tiles could disagree about the current subject. The
alternative considered was to keep both entry points and make a loaded Project
and a loaded Experiment mutually exclusive, greying the Project card while an
experiment was open. That was rejected: it does not remove the second entry
point, and it takes away the replicates table exactly when the user is hopping
between replicates.

## Decision

- **The replicates table is the only way to load an experiment.** One
  double-click on a row selects that replicate *and* loads it (`Load + QC`, as
  the Experiment panel's button used to). A row without a
  `tracking_config.yaml` is not loadable: the double-click offers to scaffold
  the config from the project design and stops there, because region
  treatments still have to be assigned.
- **The Experiment tile, its panel, and the Load card are removed.** The strip
  is five tiles: **Project, Analyze, Plots, Scripts, AI**. The sidebar loses
  its Experiment entry for the same reason.
- **The Project tile carries load status.** Its second summary line is the
  loaded experiment (name, flies, excluded, flagged) once something is loaded,
  and the replicate/analysis counts before that.
- **The strip's leftover width is a status readout.** A tile line elides at
  196px, so the space right of the AI tile holds a non-clickable status panel:
  project name and type, path, replicate/analysis counts, and the loaded
  experiment ("none loaded" until there is one). It is filled from the Project
  object the tile refresh already loaded — never a second read — and the design
  factors go to its tooltip rather than a fifth line.
- **A Project is required to load anything.** A bare directory has no
  replicates table to double-click, so its Project tile hint is "not a project
  yet" and the Create/Load card's **Create config…** is the fix. When that
  directory is itself an experiment (it has a `tracking_config.yaml`),
  **Create config…** offers to write the `project.yaml` on the *parent*, so the
  experiment becomes a replicate — writing it in place would create a Project
  with zero replicates and nothing to load.
- **Scripts wait on a load too.** Experiment Scripts run against the loaded
  experiment, so the Scripts tile dims while nothing is loaded even when the
  selected config lists recipes. Project Scripts are unaffected: they live in
  the Project panel's Analysis card.

## Consequences

- Mutual exclusivity is unnecessary. There is one subject at a time because
  there is one way to change it, and drilling into a replicate keeps the
  enclosing Project's table and project-level actions available — the
  workflow ADR-0007's "effective project" already supported.
- The Python API is unchanged: `Experiment(directory)` still loads a
  standalone experiment. This is a Hub-level constraint, not a domain one.
- Any test that double-clicks a replicate row now triggers a real load. Tests
  that only care about navigation must stub `_load_experiment`; a failed load
  calls `_warn`, which is modal and will hang a headless run.
