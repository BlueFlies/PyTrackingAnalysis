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
- **`scripts`** and **`experiment_scripts`** hold the two script levels - see **Scripts sections** below.

Advanced hand-edited keys placed under `design.global` are enforced too. Use that deliberately: if you put a key there, every replicate must resolve to the same value.

## Scripts sections

Two-level scripting lives in `project.yaml`:

- **`scripts`** holds Project Scripts: named step lists of project-level actions (`run_all_analyses`, `build_combined_analysis`, `render_publication_figures`, `project_report`, `generate_ai_narrative`, `validate_design`, `run_in_experiments`). Run them from the Project panel's **Script** picker, where the built-in **Standard pipeline** and **Report pipeline** are always listed; built-ins are never written to the file.
- **`experiment_scripts`** holds centrally managed Experiment Scripts: one recipe serving every replicate without being copied into their configs. They run only through a Project Script's `run_in_experiments` step - in every replicate, or just the ones its `only:` list names. The Hub's Scripts tile lists solely the loaded experiment's own scripts, not these.

Both sections are optional; **Edit scripts...** (the Script Editor) writes them, and other keys in the file are preserved. See the **Scripts and Script Editor** and **Project actions** help topics.

One level up, a Batch has the analogous lazy file: `batch.yaml`, holding the designated Project Script (`script:`) and centrally held Project Scripts (`project_scripts:`). Unlike `project.yaml` it never marks the folder - a Batch is structural, and the file appears only once batch-level scripting is authored. See the **Batch runs** help topic.

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
