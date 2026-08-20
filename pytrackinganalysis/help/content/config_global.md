# Global settings

The **Global** tab edits the `global:` section of `tracking_config.yaml`.

## Tracking type

Chooses the analysis mode (must match how DTrack recorded the data):

- `TRACKER` — distance / speed only
- `TWOCHOICETRACKER` — preference index (PI), percentage, transitions
- `XCHOICETRACKER` — adjusted X position along an axis
- `PAIRWISEINTERACTIONTRACKER` — proximity interactions
- `COUNTER` / `TWOCHOICECOUNTER` / `PAIRWISEINTERACTIONCOUNTER` — occupancy-based (no continuous identity between frames)

## Tracking rig

Calibration preset (`small_arena`, `arena_max`, `colosseum`, …). Sets `fps` / `mm_per_pixel` from known hardware. Unknown names keep generic defaults — double-check spelling.

## Experimental design factors

Define factor names and levels (e.g. Genotype: CS, Mutant). Tracking-region rows then pick a level per factor. An experiment will not load without a parseable design.

## Optional fields

Common optional keys include:

- **`facet_cutoffs`** — minute boundaries for faceted summaries/plots (e.g. `10, 70`).
- **`facet_labels`** — optional names for the resulting phases, one per phase (e.g. `Acclimation, Experiment, Cooldown`). Falls back to the Experiment Type's defaults, then plain minute ranges.
- **`min_transitions`** — (Valence) the low-transition exclusion: flies with fewer transitions than this during the primary phase (default 5) are excluded from every result and listed in `*_Excluded.csv`; `0` turns the exclusion off.
- **`min_movement`** — (Valence) the low-movement flag: flies averaging less than this (mm/min, default 140) during the first phase are flagged as potentially an issue but kept in every result (`LowMovementFlag` column); more than half flagged marks the whole experiment as potentially an issue; `0` turns the flagging off.
- Parameter overrides (sleep threshold, walking speed, interaction distances, …) when you need to leave rig defaults.

Use the Hub **Faceted** checkbox / plot buttons with the same cutoffs after load.
