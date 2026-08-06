# Experiment Type owns and derives config

## Context

We are introducing **Experiment Types** (see [CONTEXT.md](../../CONTEXT.md)) — named
bundles like *Valence* that standardize an assay end to end. The question was
where the truth for an experiment's fixed settings lives: written explicitly in
`tracking_config.yaml`, or owned by the Experiment Type.

## Decision

The Experiment Type **owns** its fixed fields. A typed `tracking_config.yaml`
stays minimal — `experiment_type: Valence` plus only user-owned fields (rig
choice, Light/NoLight aliases, treatment assignments, design factors). The
derived fields — `tracking_type`, `facet_cutoffs`/phases, and the report/output
specs — come from the Experiment Type definition in code and are **never written
to disk**. A hand-set field that conflicts with the type is a hard validation
error.

`experiment_type` is **optional**: a config without it is a *Custom Experiment*
(today's freeform, `tracking_type`-driven, unconstrained behavior), so existing
projects are untouched. For a **typed** experiment, `Experiment.__init__`
validates the config through the type and **fails hard** on any violation
(closing the prior gap where `config_validation` was not run at load); Custom
stays lenient. Each Experiment Type also declares a **curated output manifest**
and the runner produces exactly that set of files, nothing else.

## Consequences

- A future reader will see a Valence config with **no `tracking_type`** and no
  facets — that is deliberate, not an omission. Do not "add them back".
- Config editing tools must treat owned fields as derived (hidden/read-only),
  never persisting them, to avoid drift.
- Reversing this (moving truth back into the yaml) would change the file format
  and every consumer, hence recording it here.
