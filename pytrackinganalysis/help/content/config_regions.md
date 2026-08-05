# Tracking and counting regions

## Tracking regions

Each row is one tracking region (tube / well). Region names usually follow `T_0`, `T_1`, … matching DTrack `*_Data_1.csv` → `T_0`, etc.

- Assign a level for every experimental-design factor from the Global tab.
- **X / Y multipliers** are `1` or `-1` to flip coordinates when arenas are mirrored.
- **Generate N regions** bulk-fills `T_0` … `T_(N-1)`.

## Counting regions

Used by two-choice and counter assays. Each row maps a **treatment label** to one or more **aliases** found in the data’s counting-region column.

Example: label `Light` with aliases `Light, LL, L` assigns the Light treatment whenever the file says Light, LL, or L.

Rules:

- Two-choice types need **exactly two** counting regions.
- Every counting-region entry needs an `alias` key.

After editing regions, save the YAML and **Reload** / re-load the experiment in the Hub so analyses see the change.
