# Project YAML

`project.yaml` is the marker file that makes a parent folder a Project. It is also the authority for the shared design every replicate must match.

## What it owns

Typical keys:

```
name: My Study
notes: Optional Project notes.
design:
  global:
    experiment_type: Valence
    experimental_design_factors:
      Genotype: [CS, Mutant]
    facet_cutoffs: [10, 70]
    facet_labels: [Acclimation, Experiment, Cooldown]
    min_transitions: 5
    min_movement: 140
  counting_regions:
  - Light
  - NoLight
scripts: []
experiment_scripts: []
```

- **`name`** is the display name used in the Hub, combined outputs, and Project report.
- **`notes`** are optional and appear near the top of the Project report.
- **`design.global`** is the shared global design: experiment type, design factors and levels, facets, phase names, and type-specific quality criteria.
- **`design.counting_regions`** fixes the treatment-region names and their order. Aliases stay per replicate.
- **`scripts`** holds Project Scripts.
- **`experiment_scripts`** holds centrally managed Experiment Scripts that can run in every replicate.

Advanced hand-edited keys placed under `design.global` are enforced too. Use that deliberately: if you put a key there, every replicate must resolve to the same value.

## What stays out

Do not put a `tracking_config.yaml` at the Project root. Each replicate directory has its own `tracking_config.yaml` for recording-specific details:

- tracking rig and calibration overrides
- tracking-region treatment assignments
- counting-region aliases from that DTrack export
- replicate-local experiment scripts

## Validation

When a Project loads, every configured replicate is checked against `project.yaml`.

Hard failures include:

- different Experiment Type
- missing or extra design factors
- different factor levels
- counting-region names out of order
- any enforced `design.global` key resolving to a different value

Region assignments, aliases, fly counts, and rigs may differ unless you explicitly enforce them in `design.global`.

## Creating replicate configs

**Experiment configs...** and **Add experiment...** scaffold `tracking_config.yaml` files from `project.yaml`. The scaffold matches the shared design by construction, but you still need to assign region treatments, check aliases, choose the rig when needed, and add the DTrack export under `data/`.
