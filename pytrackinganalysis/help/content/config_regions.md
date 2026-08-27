# Tracking and counting regions

These tabs edit the replicate-specific parts of `tracking_config.yaml`.

## Tracking regions

Each row is one tracking region, such as a tube or well. Region names usually follow DTrack numbering: `T_0`, `T_1`, and so on. `ExperimentName_Data_1.csv` maps to `T_0`; `ExperimentName_Data_2.csv` maps to `T_1`.

For each row:

- Pick one level for every design factor from the **Global** tab.
- Set **X multiplier** and **Y multiplier** to `1` or `-1` when a mirrored arena needs its coordinates flipped.
- Use **Generate N regions** for Custom layouts, or let a typed rig such as Valence on Arena Max or Colosseum lay out the required plate. Arena Max is always 36 wells (`T_0`..`T_35`); the Colosseum is run at either 24 (`T_0`..`T_23`) or 18 (`T_0`..`T_17`), and both validate. A config laid out from scratch gets 24 — to run 18, remove the last six rows. An existing plate of either size is left alone.

In a Project, region-to-treatment assignments remain per replicate. The shared design says which factor levels exist; each recording still chooses which physical region belongs to which level.

## Counting regions

Counting regions map DTrack strings to treatment labels. Each row has:

- **Treatment label** - the label used in summaries and plots.
- **Aliases** - comma-separated strings that may appear in the data file.

Example: label `Light` with aliases `Light, LL, L` assigns the Light treatment whenever DTrack reports any of those aliases.

Rules:

- Two-choice types need exactly two counting-region names.
- Each counting-region entry needs an `alias`.
- In a Project, `project.yaml` enforces the counting-region names and their order; aliases remain per replicate because DTrack exports can differ.

After saving, reload the replicate in the Hub so analyses use the updated config.
