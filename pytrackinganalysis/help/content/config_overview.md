# Config file overview

`tracking_config.yaml` describes one Experiment Directory. In a Project, it is the per-replicate config; the shared design lives in the Project's `project.yaml`.

## Top-level sections

- **`global`** - experiment type or tracking type, rig, design factors, facet settings, quality criteria, and optional parameter overrides.
- **`tracking_regions`** - one entry per tube, well, or tracked animal region.
- **`counting_regions`** - treatment labels and DTrack aliases for two-choice and counter assays.
- **`scripts`** - optional experiment-level scripts run from the Hub's **Scripts** tile or from a Project Script.

Project-level scripts live in `project.yaml`, not in a replicate's `tracking_config.yaml`.

## Creating a valid config

1. In the Hub Project panel, use **Experiment configs...** to scaffold missing replicate configs from the Project design.
2. Open a replicate in **Config Editor** to assign rig, tracking-region treatments, and aliases.
3. Copy an existing config only when the design and region layout truly match; then edit per-replicate details.
4. For a standalone experiment outside a Project, the Config Editor's new-file flow can create a starter Experiment Directory.

## Rules

- The file must be named exactly `tracking_config.yaml`.
- It belongs at the Experiment Directory root, beside `data/`.
- A Project root uses `project.yaml`; it should not contain its own `tracking_config.yaml`.
- In a Project, enforced keys must match `project.yaml`'s `design:` section. Region treatments, aliases, fly counts, and rigs may differ between replicates.
- `TWOCHOICETRACKER` and `TWOCHOICECOUNTER` need exactly two counting regions, each with an `alias`.
- Typed Experiment Types, such as Valence, may fix or constrain fields. The editor disables fixed fields and validates required regions before saving.

Validate a loaded replicate config from the Hub with **Tools -> Validate YAML**. At a Project root, use **Experiment configs...** to open the replicate config you want to inspect.

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
