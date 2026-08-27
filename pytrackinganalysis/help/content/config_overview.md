# Config file overview

`tracking_config.yaml` describes one Experiment Directory. In a Project, it is the per-replicate config; the shared design lives in the Project's `project.yaml`.

## Top-level sections

- **`global`** - experiment type or tracking type, rig, design factors, facet settings, quality criteria, and optional parameter overrides.
- **`tracking_regions`** - one entry per tube, well, or tracked animal region.
- **`counting_regions`** - treatment labels and DTrack aliases for two-choice and counter assays.
- **`scripts`** - optional experiment-level scripts run from the Hub's **Scripts** tile or from a Project Script (the `run_in_experiments` bridge - every replicate, or only ones named in its `only:` list).

Project-level scripts live in `project.yaml`, not in a replicate's `tracking_config.yaml`.

## Creating a valid config

1. In the Hub Project panel, use **Experiment configs...** to scaffold missing replicate configs from the Project design.
2. Open a replicate in **Config Editor** to assign rig, tracking-region treatments, and aliases.
3. Copy an existing config with the Hub's **Copy config from...**, offered right after **Create experiment...**. The chosen file is checked against the project design *before* it is written; a config that would not conform is refused and nothing is overwritten. Copy only when the region layout truly matches as well — conforming to the design does not mean the treatments belong to this recording.
4. For a standalone experiment outside a Project, the Config Editor's new-file flow can create a starter Experiment Directory.

## Rules

- The file must be named exactly `tracking_config.yaml`.
- It belongs at the Experiment Directory root, beside `data/`.
- A Project root uses `project.yaml`; it should not contain its own `tracking_config.yaml`.
- In a Project, enforced keys must match `project.yaml`'s `design:` section. Region treatments, aliases, fly counts, and rigs may differ between replicates.
- `TWOCHOICETRACKER` and `TWOCHOICECOUNTER` need exactly two counting regions, each with an `alias`.
- Typed Experiment Types, such as Valence, may fix or constrain fields. The editor disables fixed fields and validates required regions before saving.

Validate from the Hub with **Project -> Create/Load -> Validate YAMLs**. With a Project selected it checks the `project.yaml` *and* every replicate's `tracking_config.yaml` in one pass, reporting each file separately with a count at the end; with a standalone experiment it checks that one config. Use **Experiment configs...** to open a replicate config you want to edit.

## Minimal Custom example

```
global:
  tracking_type: TWOCHOICETRACKER
  tracking_rig: colosseum
  experimental_design_factors:
    Genotype: [CS, Mutant]
tracking_regions:
  T_0:
    experimental_factors: CS
    x_location_multiplier: 1
    y_location_multiplier: 1
counting_regions:
  Light:
    alias: Light
  Dark:
    alias: Dark
```

Open **Global settings** or **Tracking and counting regions** for field details.
