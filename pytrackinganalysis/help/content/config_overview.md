# Config file overview

`tracking_config.yaml` describes the experiment: hardware, design, regions, and optional scripts.

## Top-level sections

- **`global`** (required) — tracking type, rig, experimental design, optional parameters.
- **`tracking_regions`** (required) — one entry per tube/well / tracked animal.
- **`counting_regions`** — required for two-choice and counter types (treatment labels + DTrack aliases).
- **`scripts`** (optional) — saved analysis recipes for the Hub / batch mode.

## Creating a valid file

1. **Config Editor** (recommended) — structured forms, bulk region generation, live validation.
2. **Copy** a working YAML into a new project (Batch tools can push one file into every subfolder).
3. **Write by hand** — plain YAML in any text editor.

Rules:

- File name `tracking_config.yaml` at the project root (batch mode matches case-insensitively).
- An experimental design is required for load.
- `TWOCHOICETRACKER` / `TWOCHOICECOUNTER` need **exactly two** counting regions, each with an `alias`.

Validate anytime from the Hub: **Tools → Validate YAML**.

## Minimal example

```
global:
  tracking_type: TWOCHOICETRACKER
  tracking_rig: colosseum
  experimental_design:
    Genotype: [CS, Mutant]
tracking_regions:
  T_0:
    experimental_factors: CS
    XLocationMultiplier: 1
    YLocationMultiplier: 1
counting_regions:
  Light:
    alias: Light
  Dark:
    alias: Dark
```

Open **Global settings** or **Tracking and counting regions** for field details.
