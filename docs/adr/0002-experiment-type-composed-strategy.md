# Experiment Type is a composed base-class strategy

## Context

Experiment Types need a definition mechanism that makes adding a new type easy
and lets a type override behavior where necessary. The obvious, lighter option
was a declarative registry of dataclass definitions (mirroring the existing
`_TRACKING_TYPE_PLOTS` / `_TRACKING_TYPE_METRICS` policy tables). The heavier
option was an object hierarchy.

## Decision

Experiment Types are an **`ExperimentType` base class with one subclass per
type** (`ValenceExperimentType`), **composed into** the existing `Experiment`
class as a strategy. `Experiment` remains the single orchestrator
(`run_analysis`, `create_report`, delegation to `Arena`) and delegates
type-specific decisions — allowed rigs, phase labels, config validation, plot/
metric selection, report spec, output manifest — to its `ExperimentType` via
base-class methods that subclasses override.

We chose this over:

- **A declarative registry** — simpler, but a type can only ever be *data*;
  there is no override point when a future type needs bespoke behavior.
- **Subclassing `Experiment` per type** — would bloat the already-large
  `Experiment` class and couple orchestration to each type.

## Consequences

- Adding a type = adding an `ExperimentType` subclass + registering it, not
  editing the orchestrator.
- The base class defines the type interface; keep orchestration out of it.
- More indirection than a registry, accepted deliberately for override headroom.
