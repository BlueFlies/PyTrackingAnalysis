# PyTrackingAnalysis — User Guide

## Table of contents

1. [Overview](#1-overview)
2. [Environment setup with uv](#2-environment-setup-with-uv)
   - [Windows](#21-windows)
   - [macOS](#22-macos)
   - [Linux](#23-linux)
3. [Directory structure: experiments and Projects](#3-directory-structure-experiments-and-projects)
4. [The tracking\_config.yaml reference](#4-the-tracking_configyaml-reference)
5. [The desktop UI](#5-the-desktop-ui)
   - [Launching the apps](#51-launching-the-apps)
   - [Analysis Hub](#52-analysis-hub-pytrack-hub)
   - [Config Editor](#53-config-editor-pytrack-config)
   - [QC Viewer](#54-qc-viewer-pytrack-qc)
6. [Running the pipeline from a notebook or script](#6-running-the-pipeline-from-a-notebook-or-script)
7. [Understanding the outputs](#7-understanding-the-outputs)
8. [Projects: replicates, combined analysis, and batch runs](#8-projects-replicates-combined-analysis-and-batch-runs)
9. [Quick reference](#9-quick-reference)

> Scripts (saved analysis recipes) and the visual Script Editor have their own
> dedicated guide: **[scripts_guide.md](scripts_guide.md)**.

---

## 1. Overview

PyTrackingAnalysis is a Python pipeline for analysing insect-tracking data exported
from DTrack.  A single configuration file (`tracking_config.yaml`) describes the
experiment — the tracking hardware, the experimental design, and how each physical
tracking region maps to a treatment group.  From that one file the pipeline can
produce summary CSVs, statistical comparisons, publication-quality plots, and a
multi-page PDF report.  Several experiment directories can be grouped into a
**Project** of replicates (§8) with a pooled Combined Analysis, project-level
publication figures, and a Project Report; and any report can carry an
optional **AI-written summary** (§5.2, §6).

There are several ways to drive the pipeline:

| Interface | Best for |
|-----------|----------|
| **Analysis Hub** (`pytrack-hub`) | Day-to-day use; loads experiments and Projects, runs analyses, shows plots in a tabbed dock |
| **Config Editor** (`pytrack-config`) | Authoring `tracking_config.yaml` + visual Script Editor for saved recipes |
| **QC Viewer** (`pytrack-qc`) | Per-tracker data-quality tables + XY / distance / timeline plots |
| **Plot Editor** (`pytrack-plots`) | Project-level publication figures (plotnine, vector SVG/PDF output) |
| **Jupyter notebook** (`Notebooks/SimpleTracker.ipynb`) | Exploratory work; custom plots |
| **Python script / REPL** | Automation; integration with other tools |

---

## 2. Environment setup with uv

[uv](https://docs.astral.sh/uv/) is a fast Python package manager that reads
`pyproject.toml` and locks exact dependency versions.  The project requires
**Python 3.13 or later**.

### 2.1 Windows

**Install uv**

Open PowerShell and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart the terminal so `uv` is on `PATH`.

**Clone the repository and create the environment**

```powershell
git clone https://github.com/your-org/PyTrackingAnalysis.git
cd PyTrackingAnalysis

# Create a virtual environment using the Python version in .python-version (3.13)
uv sync
```

`uv sync` reads `pyproject.toml`, downloads and installs all dependencies into
`.venv\`, and is idempotent — safe to run again after pulling updates.

**Activate the environment (optional — uv run works without it)**

```powershell
.venv\Scripts\Activate.ps1
```

**Run the UI**

```powershell
# With the environment activated:
pytrack                        # Analysis Hub (default entry point)
pytrack-hub                    # Analysis Hub (same as pytrack)
pytrack-config                 # Config Editor
pytrack-qc                     # QC Viewer

# Or without activating, using uv run:
uv run pytrack-hub

# With an explicit experiment (or Project) directory:
uv run pytrack-hub "C:\Users\you\Experiments\Trial1"
```

> **PyQt6 note on Windows:** If a "platform plugin not found" error appears,
> install the Visual C++ Redistributable from Microsoft's website, then retry.

---

### 2.2 macOS

**Install uv**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart the terminal (or run `source ~/.zshrc` / `source ~/.bash_profile`).

**Clone the repository and create the environment**

```bash
git clone https://github.com/your-org/PyTrackingAnalysis.git
cd PyTrackingAnalysis
uv sync
```

**Activate the environment (optional)**

```bash
source .venv/bin/activate
```

**Run the UI**

```bash
# With environment activated:
pytrack                        # Analysis Hub (default entry point)
pytrack-hub                    # Analysis Hub (same as pytrack)
pytrack-config                 # Config Editor
pytrack-qc                     # QC Viewer

# Without activating:
uv run pytrack-hub

# With an experiment (or Project) directory:
uv run pytrack-hub /path/to/Trial1
```

> **macOS display server note:** PyQt6 requires a display.  Confirm XQuartz is
> not needed (native macOS Cocoa backend is used automatically).

---

### 2.3 Linux

**Install uv**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or via pip if curl is unavailable:
pip install uv
```

Restart the terminal or run `source ~/.bashrc`.

**Install system Qt dependencies (if missing)**

On Debian/Ubuntu:

```bash
sudo apt install libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0
```

On Fedora/RHEL:

```bash
sudo dnf install xcb-util-cursor libxkbcommon-x11
```

**Clone the repository and create the environment**

```bash
git clone https://github.com/your-org/PyTrackingAnalysis.git
cd PyTrackingAnalysis
uv sync
```

**Activate the environment (optional)**

```bash
source .venv/bin/activate
```

**Run the UI**

```bash
pytrack-hub                          # Analysis Hub
uv run pytrack-hub                   # works from any directory
uv run pytrack-hub /path/to/Trial1   # open a specific project
uv run pytrack-config                # Config Editor
uv run pytrack-qc /path/to/Trial1    # QC Viewer
```

> **Headless / SSH note:** PyQt6 requires an X11 or Wayland display.  If running
> over SSH, forward the display with `ssh -X` or use a VNC/RDP session.  For fully
> headless batch processing, use the Python API (§6) instead.

---

### Updating the environment

After pulling new commits:

```bash
git pull
uv sync          # installs / removes packages to match the updated lock file
```

---

## 3. Directory structure: experiments and Projects

An **experiment directory** is the root folder for a single recording. It must
contain `tracking_config.yaml` and a `data/` sub-folder with the DTrack export
files.  The pipeline creates `analysis/` and `qc/` automatically on first run.
(Several experiment directories become replicates of a **Project** — see the
Projects section below.)

```
MyExperiment/                        ← experiment directory (pass this to the UI)
├── tracking_config.yaml             ← experiment configuration (required)
├── data/                            ← DTrack export files (required)
│   ├── ExperimentName.xlsx          ← main DTrack workbook
│   ├── ExperimentName_Data_1.csv    ← per-tracker CSV, one per tracking region
│   ├── ExperimentName_Data_2.csv
│   ├── ...
│   ├── ExperimentName_BG.jpg        ← background image (optional)
│   ├── LeftProgram.txt              ← stimulus program files (optional)
│   └── RightProgram.txt
├── analysis/                        ← created by the pipeline
│   ├── ExperimentName_experiment_summary.txt
│   ├── ExperimentName_Summary.csv
│   ├── ExperimentName_Summary_Facet.csv
│   ├── ExperimentName_Stats.txt
│   ├── ExperimentName_Notes.txt     ← run notes typed in at Run Analysis (optional)
│   ├── ExperimentName_plot_pi_facet.png
│   ├── ExperimentName_plot_percentage_facet.png
│   ├── ExperimentName_plot_transitions_facet.png
│   └── ExperimentName_plot_totaldistance_facet.png
└── qc/                              ← created by the pipeline
    └── ExperimentName_data_quality.csv
```

**Naming rules:**

- The `.xlsx` file determines the experiment name.  Every output file is
  prefixed with that name.
- The per-tracker CSVs must follow the pattern `<name>_Data_<N>.csv`.
  `N` is matched to tracking region `T_N-1` in the YAML
  (i.e. `_Data_1.csv` → region `T_0`).
- `tracking_config.yaml` must be at the **top level** of the experiment
  directory — not inside `data/`.

### Projects (replicates of one design)

A **Project** is a directory with a `project.yaml` marker whose immediate
subdirectories containing a `tracking_config.yaml` are its **Experiments** —
replicates of one design (see `docs/adr/0005`):

```
MyProject/
├── project.yaml                 ← makes it a Project (name, notes, design, scripts)
├── plot_specs.yaml              ← project-level publication figure specs
├── analysis/                    ← Combined Analysis (pooled CSVs + stats + AI narrative)
├── figures/                     ← project publication figures (SVG/PDF)
├── MyProject_report.pdf         ← Project Report
├── Trial1/                      ← an Experiment (replicate)
│   ├── tracking_config.yaml
│   ├── data/  analysis/  qc/
│   └── Trial1_report.pdf
└── Trial2/ ...
```

`project.yaml`'s **`design:` section is the authority** for everything the
replicates share: the experiment type, design factors *and levels*, facet
cutoffs and phase names, quality criteria (`min_transitions`,
`min_movement`), and the counting-region **names** (aliases stay
per-experiment). Opening the Project **hard-validates** every replicate's
resolved config against it (a config omitting a key the type defaults still
matches a design stating that default); region→treatment assignments, fly
counts, and rigs may differ. The Create/Edit Project dialog edits the design
and **Add experiment** scaffolds new replicate configs from it — so an empty
Project is a valid starting point. Projects also have their own scripts:
`project.yaml` can carry **Project Scripts** (`scripts:`) and centrally-held
**Experiment Scripts** (`experiment_scripts:`); the Project card's script
picker always includes the built-in **Standard pipeline**. See
**scripts_guide.md §8**. Flies from
the same treatments are **pooled across replicates** for the combined plots,
data, and statistics: the Combined Analysis stacks each replicate's
*filtered* summaries with an `Experiment` column, and its statistics show the
pooled per-fly Welch/Tukey tests beside a **linear mixed model** (treatment
fixed, experiment random intercept) that accounts for between-replicate
variation. An old batch parent becomes a Project by writing a `project.yaml`
into it (the Hub's **Create project** button does exactly that).

`project.yaml` may also hold two script sections (see §8.3): `scripts:` —
**Project Scripts**, step lists of project-level actions — and
`experiment_scripts:` — experiment-level scripts held centrally so one recipe
serves every replicate without being copied into their configs.

---

## 4. The tracking\_config.yaml reference

`tracking_config.yaml` has four possible top-level sections: `global`,
`tracking_regions`, `counting_regions`, and `scripts`.  `global` and
`tracking_regions` are required for every experiment; `counting_regions` is
required for the two-choice and counter tracking types; `scripts` is optional.

### Creating a valid file

There are three equally valid ways to create one:

1. **Config Editor** (recommended) — `pytrack-config` gives you structured
   forms for every section, bulk region generation, and a live YAML preview,
   so the file is valid by construction.
2. **Copy an existing config** — copy a working `tracking_config.yaml` into
   the new experiment directory and edit it.  The Hub's **Batch tools → Copy
   YAML** can push one file into every sub-directory of a parent; inside a
   Project, **Experiment configs…** scaffolds a design-conformant config for
   every experiment directory that lacks one (and **Add experiment…** does it
   for a directory that does not exist yet).
3. **Write it by hand** — any text editor works; the file is plain YAML.

Rules that make a file *valid*:

- The file must be named `tracking_config.yaml` (exact lowercase) and live in
  the experiment directory (next to `data/`, not inside it).
- An experimental design is **required** — an experiment will refuse to load
  without a parseable config.
- `tracking_type` must be one of the values in §4.1 (only a *missing* key
  falls back to `TRACKER`; a wrong value is an error).
- `TWOCHOICETRACKER` and `TWOCHOICECOUNTER` must define **exactly two**
  `counting_regions` entries.
- Every `counting_regions` entry must have an `alias` key.

Check a file at any time with the Hub's **Tools → Validate YAML** button —
parse errors are reported in the Output and Errors tabs.

### 4.1 `global` — required fields

```yaml
global:
  tracking_type: TWOCHOICETRACKER   # see table below
  tracking_rig:  colosseum          # see table below
```

#### `experiment_type` (recommended)

An **Experiment Type** is a named bundle that standardizes an assay end to end:
it fixes the tracking type, the phases, and the required regions, constrains the
rig, and produces a report tailored to that assay. Choose one and the fields it
owns are supplied for you — you do **not** write them in the file.

```yaml
global:
  experiment_type: Valence     # fixes tracking_type + phases; constrains the rig
  tracking_rig:    colosseum   # you choose: arena_max or colosseum
```

| Value | What it fixes |
|-------|---------------|
| `Valence` | Two-choice light-preference assay. Tracking type `TWOCHOICETRACKER`; **Light/NoLight** counting regions (in that order, so positive PI = light-preference); phases **Acclimation (0–10) / Experiment (10–70) / Cooldown (70+)**; rig must be `arena_max` (36 regions, `T_0`–`T_35`) or `colosseum` (24 regions, `T_0`–`T_23`); calibration from the rig preset only. |

For a type whose plate is fixed by the rig (like Valence), the Config Editor
lays out the exact tracking regions when you choose the rig — 36 rows for Arena
Max, 24 for Colosseum — and a typed config is checked to have exactly that set.
You still assign each region's treatment; the region names and count are fixed.

Rules for a typed experiment:

- The file omits `tracking_type` — it comes from the type; a conflicting value
  is an error. `facet_cutoffs` is an **editable default** (10, 70 for Valence):
  it *is* written to the file and you may change it. The same goes for
  `facet_labels`, the phase names (Acclimation, Experiment, Cooldown for
  Valence): written to the file by default, yours to rename.
- **Low-transition exclusion** (Valence only, `min_transitions`, default 5,
  editable in the Config Editor): a fly with fewer than this many transitions
  during the **primary phase** (the Experiment phase — the second facet window,
  or the only one) is excluded from every result — figures, summary measures,
  statistics, and the summary CSVs. A fly with *no* data in that window counts
  as excluded too. Set `min_transitions: 0` to turn the exclusion off. Excluded
  flies are listed in the report and in `*_Excluded.csv` (written even when
  empty), and still appear in data-quality output. See `docs/adr/0003`.
- **Low-movement flag** (Valence only, `min_movement`, default 140 mm/min,
  editable in the Config Editor): a fly averaging less than this movement
  during the **first** facet window (Acclimation at default cutoffs) is flagged
  as potentially an issue — reported, **never removed**. Flagged flies stay in
  every figure, statistic, and CSV, marked by a `LowMovementFlag` column in the
  saved summary CSVs and listed in the report. When more than half of the
  analysed flies are flagged, the whole experiment is noted as potentially an
  issue on the report cover and in `*_Stats.txt`. `min_movement: 0` turns the
  flagging off.
- A typed config is validated **at load** and **fails hard** on any violation
  (wrong rig, missing Light/NoLight, a disallowed override), rather than
  crashing mid-analysis.
- Omitting `experiment_type` entirely is a **Custom** experiment: the freeform,
  `tracking_type`-driven behavior described below, unchanged. Existing configs
  keep working as-is.

The fastest way to start is the **Create experiment** button on the Analysis
Hub's sidebar: pick the type and rig, optionally set facets (default 10, 70)
and design factors, and it writes a ready-to-edit `tracking_config.yaml` and the
`data/`/`analysis/`/`qc/` folders. For Valence it also lays out the plate — 36
regions for Arena Max (with the first 18 X-flipped) or 24 for Colosseum, plus the
Light/NoLight aliases. You then assign each region's treatment and drop the DTrack
export into `data/`. You can also pick the Experiment Type from the dropdown at the
top of the Config Editor's **Global** tab. See `docs/adr/0001` and `0002`.

The rest of §4.1 describes the fields a **Custom** experiment sets directly.

#### `tracking_type`

Selects the analysis mode.  Choose the one that matches how DTrack recorded
your data.  The value is upper-cased before matching, so `twochoicetracker`
works too.  If the key is missing entirely, `TRACKER` is assumed; an
unrecognized value is an error that lists the valid choices.

| Value | Description |
|-------|-------------|
| `TRACKER` | Position tracking only — computes distance and speed |
| `TWOCHOICETRACKER` | Two-region choice assay — computes PI, percentage time, transitions |
| `XCHOICETRACKER` | Multi-region assay along a linear axis — computes adjusted X position |
| `PAIRWISEINTERACTIONTRACKER` | Proximity-based interaction scoring between pairs of tracked animals |
| `COUNTER` | Frame-count based occupancy (no continuous position) |
| `TWOCHOICECOUNTER` | Counter-based two-region choice — PI and percentage |
| `PAIRWISEINTERACTIONCOUNTER` | Counter-based pairwise interaction scoring |

#### `tracking_rig`

Selects the hardware calibration preset.  `fps` and `mm_per_pixel` are set
automatically from the preset; all other parameters use the defaults shown
below.  The value is matched case-insensitively with spaces/hyphens treated as
underscores (`Arena Max` → `arena_max`), and the common misspelling
`colloseum` is accepted for `colosseum`.  An unknown rig name is not an
error — the tracking type is still applied but all calibration values stay at
their generic defaults, so double-check the spelling.

| Value | mm per pixel | Notes |
|-------|-------------|-------|
| `small_arena` | 0.056 | |
| `arena_max` | 0.145 | |
| `colosseum` | 0.108 | |
| `obscura` | 0.131 | |
| `movie` | — | You **must** supply `fps` and `mm_per_pixel` manually |

> `fps` for all hardware rigs is read from the timestamps in the DTrack export
> rather than set to a fixed value.  Only the `movie` rig requires an explicit
> `fps`.

---

### 4.2 `global` — experimental design

```yaml
global:
  experimental_design_factors:
    feeding: [Starved, Control]
    sex:     [Male, Female]
```

List every factor and its levels.  These are used for axis labels and plot titles.
The actual assignment of factors to each physical tracking region is made in
`tracking_regions` (see §4.4).

---

### 4.3 `global` — optional fields

```yaml
global:
  # Split the recording into time phases for faceted plots and statistics.
  # [10, 70] creates three phases: 0–10 min, 10–70 min, 70+ min.
  # Remove this key entirely to disable faceted analysis.
  facet_cutoffs: [10, 70]

  # Optional names for those phases, one per phase (= one more than the number
  # of cutoffs). Used in faceted figures, the report, and project summaries;
  # omit it to fall back to the Experiment Type's defaults (for Valence:
  # Acclimation / Experiment / Cooldown) or plain minute ranges.
  facet_labels: [Acclimation, Experiment, Cooldown]

  # Only needed for the 'movie' rig, or to override a hardware preset.
  fps: 30
  mm_per_pixel: 0.108

  # Smoothing window for speed calculation (seconds). Default: 1
  speed_window_seconds: 1

  # Speed range [min, max] mm/s that defines micro-movement. Default: [0.2, 2]
  micromove_speed_mm_sec: [0.2, 2]

  # Minimum speed (mm/s) to count as walking. Default: 2
  walking_speed_mm_sec: 2

  # Minimum continuous resting duration (minutes) to count as sleep. Default: 5
  sleep_threshold_min: 5

  # Distance thresholds (mm) for interaction detection.
  # Only used with PAIRWISEINTERACTIONTRACKER / PAIRWISEINTERACTIONCOUNTER.
  interaction_distances: [8]
```

**How overrides are interpreted:** the rig preset is applied first, then any of
the recognized parameter keys present in `global:` override the preset value.
Exactly these keys are recognized as overrides — `fps`, `mm_per_pixel`,
`speed_window_seconds`, `micromove_speed_mm_sec`, `walking_speed_mm_sec`,
`sleep_threshold_min`, `interaction_distances`.  Any other key in `global:` is
carried along but ignored by the parameter system, so a typo like
`walking_speed` will not error — it simply won't take effect.

`facet_cutoffs` is read separately (not a parameter override): it becomes the
default for every faceted plot, summary, and statistics run, and is inherited
by script steps whose own `cutoffs` field is blank (see
[scripts_guide.md](scripts_guide.md)).  `facet_labels` names those phases; it
must list exactly one name per phase (cutoffs + 1) and is validated against
`facet_cutoffs`.

**How time windows are defined.**  Every window — a `facet_cutoffs` phase or an
explicit `range_minutes=(start, end)` — is *half-open*: it contains rows where
`start ≤ Minutes < end`.  `facet_cutoffs: [10, 70]` therefore produces the
phases `[0, 10)`, `[10, 70)`, and `[70, ∞)`, and each frame belongs to exactly
one of them.  `range_minutes=(0, 0)` still means "the whole recording".

Accumulated quantities such as `TotalDistance` are computed *within* the window.
Each per-frame step is credited to the window containing the frame it arrives
at, so a step spanning a cutoff is counted once, in the later phase.  The phase
totals of a faceted summary therefore add up to the flat summary total exactly.

**Which frames count.**  `DataQuality` is reported, not enforced: `TotalDistance`
sums every step in the window, including steps into and out of frames where
tracking was lost.  Those frames carry real coordinate jumps rather than blanks,
so on real recordings they inflate `TotalDistance` by up to ~19 % for the worst
animal, in proportion to how poor the tracking was.  The summary therefore also
reports **`TotalDistanceHighQualityOnly`**, which discards any step with a lost
endpoint, alongside `PercHighQuality`.  Compare the two on your own data before
reporting distances; if tracking quality correlates with treatment, part of a
distance difference between arms is a tracking artifact rather than behaviour.

A frame whose speed is undefined — a duplicate or stalled timestamp, or the
lead-in rows of the rolling speed window — cannot be classified as walking,
micro-moving or resting.  Such frames are counted in **`PercUnmeasurable`** and
excluded from the denominator of the other four fractions, so those four still
sum to 1 over the frames that were actually measurable.  Previously they fell
through to `PercResting`, making "the animal was still" indistinguishable from
"we could not tell".  A window in which *every* frame is unmeasurable reports
`NA` for the activity fractions rather than 100 % resting.

Windows used to include *both* endpoints, so a frame landing exactly on a cutoff
was counted in the phase before it and the phase after it.  How much that
mattered depends on the time base.  With `fps: 0` (the default for every rig
preset) minutes come from the DTrack `MSec` column and essentially never land on
an exact cutoff, so those results were already correct.  With an explicit `fps`,
minutes are `Frame / (fps × 60)` and hit integer cutoffs exactly — one frame per
boundary was double-counted, inflating a faceted total by roughly one sampling
interval of movement per cutoff.  `XChoiceTracker`'s `TotalXDistance_mm` had the
mirror-image problem and lost one step per window.

---

### 4.4 `tracking_regions`

One entry per DTrack tracking region.  Region names must match the naming scheme
used in the CSV files: region `T_0` corresponds to `_Data_1.csv`, `T_1` to
`_Data_2.csv`, and so on.

```yaml
tracking_regions:
  T_0:
    experimental_factors: Starved, Female   # comma-separated, order must match
                                            # experimental_design_factors order
    x_location_multiplier: 1               # set to -1 to flip the X axis
    y_location_multiplier: 1               # set to -1 to flip the Y axis
  T_1:
    experimental_factors: Control, Male
    x_location_multiplier: 1
    y_location_multiplier: 1
  # ... one entry per region
```

**How each field is interpreted:**

- `experimental_factors` — a free-form string that becomes the region's
  *Treatment* label used in grouping, plots, and statistics.  For multi-factor
  designs list the levels comma-separated in the same order as
  `experimental_design_factors` (e.g. `Starved, Female`).  Regions sharing the
  same string are analysed as one group.  A missing key means the region has
  an empty treatment (it still loads, but groups as blank — the experiment
  summary lists such regions as *(unassigned)*).
- `x_location_multiplier` / `y_location_multiplier` — correct for physical
  differences in camera orientation between regions.  Use `1` for no
  correction and `-1` to mirror an axis.  Only `1` and `-1` are meaningful:
  any other value (or a missing key) is silently treated as `1`.

The experiment summary text file (§7) includes a formatted description of the
loaded design — factors, region assignments, non-unit multipliers, counting
regions, and cutoffs — so you can verify the YAML was interpreted the way you
intended.

---

### 4.5 `counting_regions`

Maps the region labels used inside the DTrack data to canonical choice names.
Required for the counter types (`COUNTER`, `TWOCHOICECOUNTER`,
`PAIRWISEINTERACTIONCOUNTER`) **and** for `TWOCHOICETRACKER` — both two-choice
types are validated to have **exactly two** counting regions and will refuse
to load otherwise.

```yaml
counting_regions:
  Light:
    alias: Light, LL, L      # any of these strings in the data = "Light"
  NoLight:
    alias: NoLight, NL, N
```

**How it is interpreted:** each key (`Light`, `NoLight`) is a canonical
characteristic name; `alias` is a comma-separated list of the raw region
labels that map to it (whitespace around each alias is stripped).  Matching is
exact and case-sensitive after stripping.  Every entry **must** have an
`alias` key — omitting it is a config error that prevents the design from
loading.

---

### 4.6 `scripts` — saved analysis recipes (optional)

Saved, re-runnable step lists that the Hub's **Scripts** card executes.
Normally you author these visually in the Script Editor rather than by hand:

```yaml
scripts:
- name: nightly
  steps:
  - action: load_experiment
    params: {path: '.', force_preprocessing: false}
  - action: run_analysis
    params: {facet: true, cutoffs: ''}
```

Each script is `{name, steps}`; each step is `{action, params}` where `action`
is one of the registered action keys and `params` matches that action's
schema.  Inside a **Project**, experiment-level scripts can instead be held
centrally in `project.yaml`'s `experiment_scripts:` section, and the Project
Script action `run_in_experiments` runs a named experiment script in every
replicate — resolved from the Project's central section first, falling back
to a script of that name in each replicate's own `tracking_config.yaml`
(which is how a legacy `batch` script still runs; see §8.3).  See
**[scripts_guide.md](scripts_guide.md)** for the full action reference,
validation rules, and hand-editing guidance.

---

### 4.7 Complete minimal example

```yaml
global:
  tracking_type: TWOCHOICETRACKER
  tracking_rig:  colosseum
  experimental_design_factors:
    genotype: [WT, Mutant]
  facet_cutoffs: [10, 60]

tracking_regions:
  T_0:
    experimental_factors: WT
    x_location_multiplier: 1
    y_location_multiplier: 1
  T_1:
    experimental_factors: Mutant
    x_location_multiplier: 1
    y_location_multiplier: 1
```

---

## 5. The desktop UI

PyTrackingAnalysis ships four independent PyQt6 apps, each launched as its own
window.  They share a common pyflic-style theme (category-colored cards, top
bar, PlotDock) so the visual language is consistent across all of them.

| Command | Window | Purpose |
|---------|--------|---------|
| `pytrack-hub` (or just `pytrack`) | Analysis Hub  | Day-to-day Project driver: manage replicates, load experiments, run analyses, build combined results, render figures in a tabbed dock, launch Config + QC + Plot Editor |
| `pytrack-config` | Config Editor | Structured editor for `tracking_config.yaml` + visual Script Editor for saved recipes |
| `pytrack-qc`     | QC Viewer     | Per-tracker data-quality table + XY / distance / quality-timeline plots |
| `pytrack-plots`  | Plot Editor   | Publication figures (project-level): live-edit pooled plots' style and content, save vector output (SVG/PDF) for Illustrator |

### 5.1 Launching the apps

```bash
# With the environment active:
pytrack                                  # Hub (shorthand)
pytrack-hub                              # Hub
pytrack-hub /path/to/MyProject           # Hub, pre-loaded Project

pytrack-config                           # Config Editor (opens last-used or ./tracking_config.yaml)
pytrack-config /path/to/MyExperiment     # Config Editor, pre-loaded tracking_config.yaml

pytrack-qc /path/to/MyExperiment         # QC Viewer, pre-loaded experiment

pytrack-plots /path/to/MyProject         # Plot Editor (Project directories only)

# Without activating, through uv:
uv run pytrack-hub
uv run pytrack-config /path/to/Trial1

# Dev shortcut (equivalent to the console scripts above):
python -m pytrackinganalysis hub /path/to/Trial1
python -m pytrackinganalysis config /path/to/Trial1
python -m pytrackinganalysis qc /path/to/Trial1
```

**Desktop launcher / taskbar icon (Linux).** The apps set their own window
icon (a fly in a tracking reticle), but on Wayland/GNOME the *taskbar* icon
comes from a `.desktop` entry. Install entries for the desktop apps once per
environment with:

```bash
uv run pytrack-install-desktop
```

This also adds the apps to your desktop's application launcher. Re-run it if
you move the project or recreate `.venv` (the entries embed absolute paths).

All four apps persist the light/dark theme choice to
`~/.config/pytrackinganalysis/ui.json`.  Recent projects — and the last-used
AI provider/model — are tracked there too.

---

### 5.2 Analysis Hub (`pytrack-hub`)

The Hub's layout (see `docs/adr/0007`) is a **tile strip** across the top —
five compact live-status tiles: **Project · Analyze · Plots · Scripts · AI**
— with the **output area at full width** underneath. A tile
shows only status (the project's name and replicate health, the loaded
experiment's fly counts, whether analysis is faceted, …); **clicking it
drops an anchored panel** holding all of that area's controls. One panel is
open at a time; **Esc** or clicking anywhere else closes it, and **starting
any task closes it automatically** so the streaming log and plots are
immediately visible. Tiles never move or hide: an inapplicable tile is
dimmed with a hint, and its panel contains exactly the control that fixes
the missing state (the dimmed Analyze tile opens the panel that tells you to
load an experiment first).

The Hub is **Project-first** (`docs/adr/0008`): an experiment is loaded only
by double-clicking its row in the Project panel's replicates table, so there
is one subject at a time because there is one way to change it.  There is no
Experiment tile — the Project tile reports the loaded experiment on its
second line, and the **status readout** filling the strip right of the AI tile
spells the same state out in full: project name and type, path, replicate and
analysis counts, and the loaded experiment (design factors in its tooltip).

The left sidebar opens the same panels (Tools lives *only* there), and
carries the two creation shortcuts — **Create project** (write or edit a
`project.yaml`, turning a directory of replicates into a Project) and
**Create experiment** (scaffold a new experiment directory from an
Experiment Type).

The panels:

- **Project** — two cards, **Create/Load** and **Analysis** (the panel itself is
  already titled Project, so neither card repeats it).
  **Create/Load** picks the folder (an experiment directory *or* a Project; the
  text box shows just the folder name to stay readable; hover it for the full
  path), **Load…** opens or re-scans it, and one button edits the Project's own
  config: **Edit config…** when `project.yaml` is present, **Create config…**
  when it is missing (which writes a default and opens the same Project
  editor).  Pointing it at a folder that is *itself* an experiment
  makes **Create config…** offer the **parent** instead, so the experiment
  becomes a replicate — a `project.yaml` written beside a
  `tracking_config.yaml` would be a Project with nothing to load.  Beside it,
  **Create project…** does the same for a directory you pick, so a new Project
  can be started without first opening it.  There is
  no tracking-config picker here — `project.yaml` is fixed at the Project
  root, and each experiment's `tracking_config.yaml` lives one level down
  (use **Experiment configs…** in the Analysis card); QC is experiment-level
  and opens on load.
- **Analysis** (the second card in the Project panel; populated when the
  selected directory is — or sits inside — a Project) —
  the main working surface for replicates: a table with per-replicate status
  (**Experiment, Config, Flies, Excluded, Flagged, Report**; **double-click a
  row to load that replicate** — this is the only way to load an experiment,
  and it runs QC as it loads), plus **Experiment configs…** and
  **Add experiment…** (below), the project-level actions — **Create report** or
  **Update report**, **Plot editor…**, **AI narrative…** — and a **Script** picker with
  **Run script** / **Edit scripts…** (§8.3; the built-in **Standard
  pipeline** is always available).  Subdirectories that hold no
  `tracking_config.yaml` are listed too, in italics with **Config: missing**
  — they are not replicates until they have one.
- **Analyze** — **Run Analysis**, **Run QC only**, **Create PDF Report** for
  the loaded experiment.  All tasks run on a background thread; stdout/stderr
  streams to the **Output** tab in real time.
- **Plots** — dynamically populated with the faceted plots valid for the loaded
  tracking type (`plot_pi_facet`, `plot_totaldistance_facet`, etc.).  Each click
  adds a new tab to the PlotDock.  Toggle **Interactive plots** in the top bar
  to switch between static PNG rendering (fast) and a live canvas with pan /
  zoom / save toolbar.
- **Scripts** — lists saved analysis recipes from the active YAML's `scripts:`
  section.  **Run Script** / **Run All** executes them and routes each step's
  log output to the Output tab and each figure to a PlotDock tab.  Author
  scripts from the Config Editor (see 5.3 and
  [the scripts guide](scripts_guide.md)).
- **AI** — **AI summary…** opens a dialog to pick a provider (Anthropic or
  OpenAI) and model, then writes a one-page, clearly-labeled **AI Summary**
  of the loaded experiment's analysis to `analysis/<name>_AI_Summary.txt` and
  rebuilds the report PDF to embed it.  The action is offered only when an
  API key is present (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in a `.env` file
  or the environment); the model dropdown refreshes itself monthly from the
  providers, with a manual refresh button.  Re-running the analysis deletes
  the saved summary so stale prose never sits beside fresh figures —
  regenerate it afterwards if wanted.  A failed call shows an error and never
  blocks the report.
- **Tools** — validate YAML, open the `analysis/` or `qc/` folder in the system
  file browser, open the **Batch tools** dialog (convert sub-directory layouts,
  bulk-rename sub-directories, copy a YAML into every sub-directory, combine
  summary CSVs across sub-directories), and clear the matplotlib cache.

#### The output area (below the strip)

- The first tab is always **Output** — the chronological log of everything the
  Hub does.
- The second tab is **Errors** — a permanent tab that collects only warnings
  and errors (failed tasks with tracebacks, skipped or failed replicates, YAML
  validation problems, dismissed warning pop-ups, …) so they can't get lost in
  the normal output.  When issues arrive while you're on another tab, the tab
  title shows an unseen count, e.g. **Errors (3)**; viewing the tab resets it.
- Every plot or artifact opens as an additional closable tab.  The
  **Clear plots** button in the tab-bar corner closes all of them at once and
  returns to the Output tab (Output and Errors are never closed).

---

### 5.3 Config Editor (`pytrack-config`)

Structured editor for `tracking_config.yaml` with three tabs wrapped in a Card:

- **Global** — drop-downs for `tracking_type` and `tracking_rig`; a table for
  experimental-design factors; optional facet cutoffs; text fields for each
  parameter override.
- **Tracking regions** — one row per region.  **Generate N regions** bulk-fills
  `T_0`…`T_(N-1)`.  X/Y multipliers are restricted to `1` / `-1`.
- **Counting regions** — treatment label → DTrack aliases.

A **YAML preview** Card below the tabs renders the live serialization for
trust / debugging; an amber `●` dirty indicator surfaces unsaved edits.

#### Visual Script Editor

Open via the scripts icon in the top bar.  A non-modal window with three panes:

- **Palette** (left) — category-grouped tile list of the registered actions
  (`load_experiment`, `filter_by_quality`, `filter_by_region`, `run_qc`,
  `run_analysis`, `summarize`, `run_pairwise_comparisons`, `create_report`,
  plus one plot action per plot valid for the project's tracking type).
  Double-click to add a step.
- **Canvas** (center) — ordered step cards with the action's icon, a
  parameter-summary chip, and move-up / move-down / delete buttons.
- **Inspector** (right) — dynamic form for the selected step with widgets
  derived from the action's param schema (spinbox, combo, line edit, checkbox,
  browse-for-path, comma-list).  Red banner reports validation errors inline.
- **Preview** (bottom) — live YAML of the current script.

Scripts are stored under the `scripts:` key of the surrounding
`tracking_config.yaml`.  The Hub's **Scripts** card reads the same file, so
saving in the Script Editor makes scripts immediately runnable from the Hub.

Opened on a Project's `project.yaml` (Project view → **Edit scripts…**), the
same editor gains a **level switcher**: **Project scripts** (the
project-action palette — §8.3) and **Experiment scripts** (the familiar
experiment palette, held centrally for every replicate).

**Full documentation — every action and its parameters, faceting rules, and
the two-level Project scripting model (§8.3) — lives in
[scripts_guide.md](scripts_guide.md).**

---

### 5.4 QC Viewer (`pytrack-qc`)

- Left pane — **Trackers** table with columns `Tracker, HighQuality, NotFound,
  Indiscernible, StartMinutes, EndMinutes`. Rows tint green, yellow, or red
  against the experiment's QC cutoff, with the exact thresholds shown under
  the table; a filter box narrows by tracker name.
- Right pane — `PlotDock` that updates when you select a tracker with
  four tabs:
  - **XY trajectory** — RelX/RelY scatter coloured by time (viridis).
  - **Total distance over time** — cumulative `Dist_mm` vs `Minutes`.
  - **X / Y vs time** — stacked RelX(t), RelY(t) line plots.
  - **Data quality timeline** — per-frame `DataQuality` category plotted as a
    time series so bad-tracking regions jump out visually.
- **Export data_quality.csv** writes the full table to disk for external
  review.

### 5.5 Plot Editor (`pytrack-plots`)

Publication figures for Valence experiments (see `docs/adr/0004`), rendered by
**plotnine** — a separate path from the PDF-report figures that shares the same
summarized, exclusion-filtered data.

- **Project-level tool.** Open a **Project directory** (or launch from the
  Hub's Project card): the four faceted plots show all flies **pooled across
  replicates** (built from the replicates' filtered summaries), and a
  **Mark experiments** option gives each replicate its own point shape with a
  legend. `plot_specs.yaml` and `figures/` live at the **project root**.
  Opening a replicate directory redirects up to its Project; a standalone
  experiment is refused with guidance to create a Project around it first.
- **Two-layer model.** A named **Plot Style** holds the look shared across
  plots (figure size in mm, theme, font, geometry — jittered dots, boxplots,
  or both — point/mean styling, line weight for axes/ticks/borders, facet
  strip style: plain text or the ggplot-default bordered grey box with a
  choosable fill, an optional panel background color, and treatment colors); a
  per-plot **Plot Spec** holds content (labels, facet and treatment
  inclusion/order/renames, y-limits, reference line, independent per-facet
  y axes (`free_y`, the default for movement and transitions), and optional
  per-facet **p-value brackets** — Welch's t-test for two treatments, Tukey
  HSD beyond, the same policy as Stats.txt). Both persist in
  `<project>/plot_specs.yaml`, written only by this app.
- **Save style as…** captures the current look under a name so subsequent
  plots come out identical; **Set as project default** makes it the style the
  app auto-loads for this project.
- **Save SVG… / Save PDF…** write vector files (default
  `<project>/figures/<plot>.svg`). SVG text stays *editable text* in Adobe
  Illustrator (`svg.fonttype='none'`); PDF embeds TrueType fonts. The live
  preview is rendered from the same figure object that saving uses, so the
  file always matches the screen.
- **Headless re-render**: `Project(project_dir).render_figures(formats=("svg", "pdf"))`
  regenerates every figure defined in `plot_specs.yaml` without the app —
  also available as the `render_publication_figures` Project Script action.

---

## 6. Running the pipeline from a notebook or script

The analysis pipeline is also available as a Python API.  This is the approach
used in `Notebooks/SimpleTracker.ipynb`.

### Setup

```python
import warnings
warnings.filterwarnings("ignore")

# PyTrackingAnalysis is installed as a package by `uv sync`, so import it by its
# full dotted path. This works from any working directory — no os.chdir needed.
from pytrackinganalysis.Experiment import Experiment, batch_analyze
```

### Single experiment

```python
# Pass the experiment directory — the one containing tracking_config.yaml and data/
exp = Experiment("./Data/Trial1/")

# To analyse a project against a second config in the same directory, name it.
# Without this the filename tracking_config.yaml was joined on unconditionally,
# so an alternative config could be validated but never actually used.
exp_alt = Experiment("./Data/Trial1/", config_path="alt_config.yaml")

# Human-readable summary of the loaded experiment
print(exp)

# Detailed per-tracker overview (also saved to analysis/)
exp.experiment_summary()

# Data quality report (also saved to qc/)
exp.qc(cutoff=0.9)       # cutoff = minimum fraction of valid frames per tracker

# Save summary CSVs (flat + faceted) to analysis/
exp.save_summary()

# Run pairwise statistical comparisons and save results to analysis/
exp.stats()

# Save plots to analysis/ as PNG files
exp.save_plots()

# Build a multi-page PDF report in analysis/
exp.create_report()

# Optionally attach run notes — rendered near the top of the report and saved
# as <Experiment>_Notes.txt in analysis/ (the Hub prompts for these when you
# press Run Analysis / Create PDF Report; blank clears saved notes).
exp.create_report(notes="Pilot run; lights at 50% intensity.")

# Optional AI Summary (needs ANTHROPIC_API_KEY or OPENAI_API_KEY in .env or
# the environment). Writes analysis/<name>_AI_Summary.txt; the report embeds
# it while that file exists, and run_analysis() deletes it (it describes a
# single analysis run).
exp.generate_ai_summary("anthropic")            # or "openai"; model=... to pick one
exp.create_report()                             # now carries the AI Summary section

# ── OR run the complete pipeline in one call: ────────────────────────────────
exp.run_analysis()       # summary → qc → save_summary → save_plots → stats
exp.create_report()      # PDF report (separate call so you can skip it)
```

For a **Valence Experiment** the report opens with type-specific sections
before the generic figures: the **headline result** (per-animal PI during the
Experiment phase — the phase the primary result is read from — with a
pairwise-comparison table), **preference over time** (sliding-window PI,
treatment mean ± SEM, phase boundaries marked), and **emergence &
persistence** (each animal's PI across phases plus the within-animal change
from Acclimation to Experiment). A Custom Experiment gets the generic report
unchanged.

### Accessing individual plots interactively

Inside a Jupyter notebook with `%matplotlib inline`:

```python
# These display the plot inline in the notebook (not saved to disk).
exp.arena.plot_pi()
exp.arena.plot_pi_facet(cutoffs=[10, 70])
exp.arena.plot_percentage_facet(cutoffs=[10, 70])
exp.arena.plot_transitions_facet(cutoffs=[10, 70])
exp.arena.plot_totaldistance_facet(cutoffs=[10, 70])
```

Every `*_facet` method requires `cutoffs`, either explicitly or via
`facet_cutoffs` in the config; calling one without them raises rather than
guessing.  They previously defaulted to a literal `(10, 70)`, so a project with
no cutoffs configured produced plots split at 10 and 70 minutes sitting beside
whole-recording p-values, with nothing marking the discrepancy.

The available plot methods depend on `tracking_type`:

| `tracking_type` | Plot methods |
|-----------------|-------------|
| `TRACKER` | `plot_totaldistance_facet` |
| `TWOCHOICETRACKER` | `plot_pi_facet`, `plot_percentage_facet`, `plot_transitions_facet`, `plot_totaldistance_facet` |
| `TWOCHOICECOUNTER` | `plot_pi_facet`, `plot_percentage_facet` |
| `XCHOICETRACKER` | `plot_adjusted_x_position_facet`, `plot_totaldistance_facet` |
| `PAIRWISEINTERACTIONTRACKER` | `plot_interactions_facet`, `plot_totaldistance_facet` |
| `PAIRWISEINTERACTIONCOUNTER` | `plot_interactions_facet` |

### Projects from Python

The `Project` object (§8) mirrors everything the Hub's Project view does:

```python
from pytrackinganalysis.project import Project, create_project_file

# One-time: turn a directory of replicate experiment directories into a
# Project by writing the project.yaml marker (idempotent; preserves keys).
create_project_file("./MyStudy/", name="MyStudy")

prj = Project("./MyStudy/")        # discovers replicates, validates the design
print(prj.experiment_names)        # the replicate directories
print(prj.warnings)                # non-fatal differences (rigs, cutoffs, …)

prj.run_all()                      # run_analysis + report in every replicate
prj.build_combined_analysis()      # pooled CSVs + pooled/mixed stats → <project>/analysis/
prj.render_figures(formats=("svg",))   # publication figures from plot_specs.yaml
prj.generate_ai_summary("anthropic")   # optional AI narrative (embedded below)
prj.create_report()                # <project>/<name>_report.pdf
```

`Project(...)` raises with a per-replicate problem list when a replicate does
not match the design in `project.yaml` (or, without a `design:` section, when
replicates disagree on experiment type or design factors/levels).
`build_combined_analysis()` deletes any saved AI narrative — like
`run_analysis()`, the narrative describes a single build.

### Batch processing from a script

```python
results = batch_analyze("./Data/")

for path, status in results.items():
    tag = "OK  " if status == "ok" else "FAIL"
    print(f"  {tag}  {path}")
    if status != "ok":
        print(f"       {status}")
```

`batch_analyze` scans every immediate sub-directory of the supplied path,
identifies valid experiment directories, runs `exp.run_analysis()` and
`exp.create_report()` on each, and returns a `{path: "ok" | error_message}`
dictionary.

---

## 7. Understanding the outputs

All outputs are written relative to the experiment directory (project-level
outputs to the Project root — see the last table below).

### `analysis/` — main results

| File | Contents |
|------|----------|
| `*_experiment_summary.txt` | Rig settings, parameters, a formatted description of the experimental design (factors, region assignments, non-unit multipliers, counting regions, cutoffs), data quality overview, per-tracker table |
| `*_Summary.csv` | Per-tracker summary statistics (one row per tracker). For Valence, a `LowMovementFlag` column marks flies flagged by the low-movement check (they remain in the data) |
| `*_Summary_Facet.csv` | Same, split into the time phases defined by `facet_cutoffs` |
| `*_Excluded.csv` | (Valence) Flies removed by the low-transition exclusion — name, region, treatment, and transition count in the primary phase. Written even when no fly was excluded, so absence never needs interpreting |
| `*_Stats.txt` | Pairwise statistical comparisons across treatment groups: independent two-sample **Welch's** t-test (unequal variance) when there are exactly two treatment levels, Tukey HSD when there are three or more. Each line carries both groups' N, mean and SD, and any trackers dropped for having no numeric value in the window are counted explicitly. Faceted runs append a note stating how many uncorrected tests were run and the Bonferroni-adjusted threshold. Pass `equal_var=True` to `run_pairwise_comparisons` for the classic Student's test. |
| `*_plot_*.png` | One PNG per plot type, named after the plot method |
| `*_AI_Summary.txt` | (Optional) The saved AI Summary; provenance (provider, model, date) on the first line. The report embeds it while this file exists; **every `run_analysis()` deletes it** so it can never describe a stale run |
| `<name>_report.pdf` | **Written to the experiment directory root** (beside `tracking_config.yaml`), named and titled after that directory. Multi-page PDF: cover with status lines → notes and AI Summary (when present) → analysis figures (per-phase when faceted) → statistical-comparisons table → structured experiment summary → QC figures (data quality plus per-tracker transitions/min and movement bars) |

### `qc/` — data quality

| File | Contents |
|------|----------|
| `*_data_quality.csv` | Per-tracker fraction of valid (non-missing) frames; trackers below `cutoff` are flagged |

### Project outputs (Projects only — at the Project root)

| File | Contents |
|------|----------|
| `analysis/<project>_Summary.csv` / `_Summary_Facet.csv` | The Combined Analysis: each replicate's *filtered* summaries stacked with an `Experiment` first column |
| `analysis/<project>_Excluded.csv` | All replicates' excluded flies, tagged by replicate |
| `analysis/<project>_Stats.txt` | Pooled per-fly Welch/Tukey tests beside the mixed-model p-values (treatment fixed, experiment random intercept), plus any cross-replicate warnings |
| `analysis/<project>_AI_Summary.txt` | (Optional) The AI narrative; deleted by every `build_combined_analysis()` and recreated by **AI narrative…** |
| `plot_specs.yaml` | Publication-figure Plot Specs + Plot Styles (written by the Plot Editor) |
| `figures/*.svg` / `*.pdf` | Vector publication figures rendered from the pooled data |
| `<project>_report.pdf` | The Project Report: cover with per-replicate status → AI narrative (when present) → pooled publication figures → pooled + mixed statistics table → per-replicate summary table |

---

## 8. Projects: replicates, combined analysis, and batch runs

A **Project** groups replicate experiment directories of one design under a
parent directory marked by a `project.yaml` (layout and design rules in §3;
`docs/adr/0005`).  It replaces the old "batch mode": the Hub's Project view
runs every replicate, pools their results into a Combined Analysis, renders
project-level publication figures, and builds a Project Report.

### 8.1 Creating a Project

- **New study** — Hub sidebar → **Create project**: pick/create the parent
  directory and edit the project **design** (experiment type, design factors
  and levels, facets, quality criteria, counting-region names).  The design
  is seeded from the Experiment Type's defaults.  An empty Project is valid —
  add replicates with **Add experiment…**, which scaffolds each new
  `tracking_config.yaml` *from the design*.
- **Existing replicates / old batch parent** — run **Create project** on the
  parent: the dialog infers the design from the first replicate and writes
  `project.yaml`; nothing inside the replicate directories changes.
- **Existing folders without configs** — the subdirectories are listed in the
  replicate table as **Config: missing**.  **Experiment configs…** gives each
  one a `tracking_config.yaml` from the project design (**Create all
  missing** does the lot), then opens any of them in the Config Editor to
  assign that recording's regions.  Existing configs are never overwritten.

Opening a Project **hard-validates** every replicate's resolved config
against the design and refuses to load on a mismatch, naming the offending
replicate and key.  Region→treatment assignments, counting-region aliases,
fly counts, and rigs may differ; differing cutoffs or quality criteria are
surfaced as warnings, not errors.

### 8.2 The Project view workflow

With a Project selected, the Hub shows the **Project view** (§5.2): the
replicate table plus project actions.  For a full refresh, use **Create
report** before `<project>_report.pdf` exists or **Update report** after it
exists; both labels run every replicate, rebuild Combined Analysis, and write
the Project report.

The remaining Project actions build on that refresh:

1. **Plot editor…** — curate the pooled publication figures (§5.5) from the
   Combined Analysis created by the report refresh.  Save plot specs, then run
   **Update report** to rebuild the PDF with those specs.
2. **AI narrative…** — optional AI-written narrative for the Project Report
   (same rules as the per-experiment AI Summary: key-gated, clearly labeled,
   deleted by the next combined-analysis build).  It rebuilds the Project
   report immediately so the PDF and saved text agree.

Double-click a replicate row to open it as the current experiment; the
regular Analyze/Plots/Scripts/AI cards then apply to it, while the project
actions above keep applying to the whole set.  The two contexts are
independent, so nothing has to be closed to get back to the Project.  A report
refresh rewrites every replicate's analysis and therefore unloads the current
experiment rather than leave it holding results that no longer exist.

For anything more specific than the Hub's full report refresh, use a Project
Script.  Scripts expose the lower-level project steps — replicate analysis,
Combined Analysis, publication figure rendering, report creation, AI narrative,
and `run_in_experiments` — without putting all of those partial actions back
into the main Hub.

### 8.3 Project Scripts (two-level scripting)

Projects have their own saved scripts (`docs/adr/0006`) — same
`{name, steps}` shape and the same visual editor as experiment scripts, but a
separate **project-action** palette: `validate_design`, `run_in_experiments`,
`run_all_analyses`, `build_combined_analysis`, `render_publication_figures`,
`project_report`, and `generate_ai_narrative` (soft-fail).  They live under
`scripts:` in `project.yaml`; the levels cannot mix.

The one bridge to experiment level is **`run_in_experiments(script: NAME)`**:
it runs the named *experiment-level* script in every replicate — resolved
first from the Project's central `experiment_scripts:` section (one recipe
for all replicates, never copied into their configs), falling back to a
script of that name in each replicate's own `tracking_config.yaml`.  A legacy
batch parent therefore still works: `run_in_experiments(script: batch)` runs
the old per-folder `batch` scripts unchanged.  Execution is
replicate-by-replicate with per-replicate log prefixes and continue-on-error.

The Project view's **Script** picker always includes the built-in **Standard
pipeline** (validate design → run all analyses → build combined analysis →
render publication figures → project report) — zero authoring gets a
complete run.  **Edit scripts…** opens the Script Editor on `project.yaml`
with the level switcher (§5.3).

### 8.4 Fixed pipeline from Python

```python
from pytrackinganalysis.Experiment import batch_analyze

results = batch_analyze("./ParentFolder/")   # {path: 'ok' | error message}
```

`batch_analyze` runs `run_analysis()` + `create_report()` on every immediate
sub-directory that contains a `tracking_config.yaml` and a `data/` folder with
at least one `.xlsx`; other directories are skipped.  Optional arguments:
`cutoffs` (override every experiment's facet cutoffs), `qc_cutoff` (default
0.9), and `force_preprocessing`.  It needs no `project.yaml` and builds
nothing at the parent level — for the pooled Combined Analysis and Project
Report, use the `Project` API (§6) or the Hub's Project view.

**Preparing many folders at once:** the Hub's **Tools → Batch tools** dialog
can copy one master YAML into every sub-directory, bulk-rename
sub-directories, convert flat layouts into the `data/` structure, and combine
summary CSVs across sub-folders.

### Results

Per-replicate results always land in each experiment's own `analysis/` and
`qc/` folders; the pooled artifacts land at the Project root (§7) — the two
levels never mix outputs.

---

## 9. Quick reference

### Starting the UI

```bash
# Analysis Hub (the default entry point):
pytrack                       # shorthand for pytrack-hub
pytrack-hub /absolute/path/to/project

# Via uv (works from any directory, no activation needed):
uv run pytrack-hub /absolute/path/to/project

# Standalone Config Editor (with visual Script Editor):
pytrack-config
pytrack-config /path/to/ExperimentDirectory

# Standalone QC Viewer:
pytrack-qc /path/to/ExperimentDirectory

# Plot Editor (publication figures; Project directories only):
pytrack-plots /path/to/MyProject

# One-time: install launcher entries + taskbar icon (Linux):
pytrack-install-desktop
```

### Minimal tracking\_config.yaml

```yaml
global:
  tracking_type: TWOCHOICETRACKER
  tracking_rig:  colosseum
  experimental_design_factors:
    treatment: [A, B]

tracking_regions:
  T_0:
    experimental_factors: A
    x_location_multiplier: 1
    y_location_multiplier: 1
  T_1:
    experimental_factors: B
    x_location_multiplier: 1
    y_location_multiplier: 1
```

### One-line pipeline (Python)

```python
from pytrackinganalysis.Experiment import Experiment
exp = Experiment("/path/to/experiment/")
exp.run_analysis()
exp.create_report()
```

### Project pipeline (Python)

```python
from pytrackinganalysis.project import Project
prj = Project("/path/to/MyProject/")
prj.run_all()
prj.build_combined_analysis()
prj.create_report()
```

### AI features

Put `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` in a `.env` file (next to
where you launch from, or `~/.config/pytrackinganalysis/.env`).  The Hub's
**AI** card (per-experiment summary) and the Project view's **AI narrative…**
then light up; without a key they stay disabled and everything else works
unchanged.

### Rig calibration values

| `tracking_rig` | mm / pixel |
|----------------|-----------|
| `small_arena` | 0.056 |
| `arena_max` | 0.145 |
| `colosseum` | 0.108 |
| `obscura` | 0.131 |
| `movie` | user-supplied |

### Default analysis parameters

| Parameter | Default | YAML key |
|-----------|---------|----------|
| Speed smoothing window | 1 second | `speed_window_seconds` |
| Micro-movement range | 0.2 – 2 mm/s | `micromove_speed_mm_sec` |
| Walking threshold | 2 mm/s | `walking_speed_mm_sec` |
| Sleep threshold | 5 min continuous rest | `sleep_threshold_min` |
| Interaction distance | 8 mm | `interaction_distances` |

### Environment commands

```bash
uv sync                   # install / update all dependencies
uv add <package>          # add a new dependency
uv run python <script>    # run without activating the environment
source .venv/bin/activate # activate on macOS / Linux
.venv\Scripts\Activate.ps1  # activate on Windows PowerShell
```
