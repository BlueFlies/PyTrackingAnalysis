# PyTrackingAnalysis — Scripts & the Script Editor

Scripts are saved, re-runnable analysis recipes. Instead of clicking the same
sequence of Hub buttons for every experiment, you record the sequence once —
as an ordered list of *steps* — and run it with one click, or automatically
across every replicate of a Project.

This guide covers everything about scripts: where they live, how to author
them in the visual Script Editor, what every action does, how they run, and
Project-level scripting (`project.yaml`).

## Table of contents

1. [Concepts](#1-concepts)
2. [Opening the Script Editor](#2-opening-the-script-editor)
3. [The editor, pane by pane](#3-the-editor-pane-by-pane)
4. [Building your first script](#4-building-your-first-script)
5. [Action reference](#5-action-reference)
6. [Faceting: how `facet` and `cutoffs` work](#6-faceting-how-facet-and-cutoffs-work)
7. [Running scripts](#7-running-scripts)
8. [Project scripts (two-level scripting)](#8-project-scripts-two-level-scripting)
9. [The YAML behind it all](#9-the-yaml-behind-it-all)
10. [Validation and troubleshooting](#10-validation-and-troubleshooting)

---

## 1. Concepts

- A **script** is a named, ordered list of steps:
  `{name: "...", steps: [...]}`.
- A **step** is one action plus its parameters:
  `{action: run_analysis, params: {facet: true}}`.
- Scripts exist at **two levels** (see `docs/adr/0006`):
  - **Experiment Scripts** use experiment-level actions (load, QC, analysis,
    plots, report) and are stored in an experiment's `tracking_config.yaml`
    under `scripts:` — or, for the replicates of a Project, centrally in the
    Project's `project.yaml` under `experiment_scripts:` (one recipe for
    every replicate, never copied around).
  - **Project Scripts** use project-level actions (run in experiments,
    combined analysis, publication figures, project report, AI narrative) and
    live in `project.yaml` under `scripts:`. See [§8](#8-project-scripts-two-level-scripting).
- A file can hold **any number of scripts**, each with its own name.
- Steps execute **top to bottom**. State flows through the run: the
  `load_experiment` step sets the current experiment, and every later step
  operates on it. Filters permanently modify the in-memory experiment for the
  remainder of the run (they never touch the data on disk).

---

## 2. Opening the Script Editor

There are two routes into the same editor:

- **Experiment scripts** — launch the Config Editor (`pytrack-config`, or
  **Edit config…** from the Hub), open the experiment's
  `tracking_config.yaml`, and click the **scripts icon** in its top bar.
- **Project scripts** — click **Edit scripts…** on the Hub's Project card.
  The editor opens on `project.yaml` with a **level switcher** in the top
  bar: *Project scripts* shows the project-action palette; *Experiment
  scripts* shows the familiar experiment palette editing the centrally-held
  `experiment_scripts:` recipes.

The editor opens as its own window, titled with the YAML file it edits. It is
non-modal, so you can keep the Config Editor and Hub open alongside it.

> The editor reads the YAML's `global.tracking_type` to decide which plot
> actions to offer, and `global.facet_cutoffs` to show inherited cutoff
> defaults — so open it on the same YAML your experiment uses.

---

## 3. The editor, pane by pane

```
┌─────────────┬──────────────────────┬────────────────┐
│   Palette   │        Canvas        │   Inspector    │
│  (actions)  │   (ordered steps)    │  (parameters)  │
├─────────────┴──────────────────────┴────────────────┤
│                YAML preview          [Reload] [Save] │
└──────────────────────────────────────────────────────┘
```

**Top bar — script switcher.** A drop-down of every script in the file, plus
three small buttons: **new** (create a named empty script), **rename**, and
**delete** (with confirmation). The path bar below shows the YAML file being
edited and an amber `● unsaved changes` indicator when there are unsaved
edits.

**Palette (left).** Every available action as a tile, grouped by category
(Load, QC, Analyze, Plots). Plot actions are filtered to the project's
`tracking_type` — e.g. the *PI* tile only appears for two-choice types.
**Double-click a tile** to append it as a step to the current script.

**Canvas (center).** The script itself: one card per step, in execution
order. Each card shows the action's icon and title, a short summary of its
parameters, and buttons to **move up / move down / delete**. Click a card to
select it and edit its parameters in the Inspector. Cards with invalid
parameters get a red error marker (hover it for the message).

**Inspector (right).** A form generated from the selected action's parameter
schema — spin boxes for numbers, checkboxes for booleans, browse buttons for
paths, plain text fields for comma-separated lists. Grey placeholder text
shows values inherited from the YAML (currently the project's
`facet_cutoffs`). Fields that only apply when a checkbox is on (like
`cutoffs` under `Faceted`) are greyed out when it's off; their values are kept
and restored when you re-enable the checkbox.

**Preview + Save (bottom).** A live YAML rendering of the current script —
exactly what will be written to disk. **Save** writes *all* scripts back into
the `tracking_config.yaml` (everything else in the file is preserved);
**Reload** discards unsaved changes and re-reads the file.

---

## 4. Building your first script

A typical everyday recipe — load, drop bad trackers, analyse, report:

1. Open the Script Editor, click **new**, and name the script (e.g.
   `full-run`).
2. Double-click **Load experiment** in the palette. Leave *Project dir* as
   `.` — it resolves to whatever project the script runs against.
3. Double-click **Filter trackers by quality**; in the Inspector set
   `min_high_quality` to `0.9`.
4. Double-click **Run Full Analysis**; leave *Faceted* checked and *cutoffs*
   blank to inherit the project's `facet_cutoffs`.
5. Double-click **Create PDF Report**.
6. Click **Save**.

The script now appears in the Hub's **Scripts** card (click the Project
card's **Reload** if the Hub was already open), ready to run.

**Rule of thumb: start every script with `Load experiment`.** Steps that need
an experiment raise *"no experiment loaded — add a 'Load experiment' step
first"* otherwise. The only exception is a script you always run from the Hub
*after* loading an experiment there — a script without a load step reuses the
Hub's currently-loaded experiment (see §7). Scripts run across replicates always
start from nothing, so for them the load step is mandatory.

---

## 5. Action reference

### Load

| Action | Key | Parameters | What it does |
|--------|-----|------------|--------------|
| **Load experiment** | `load_experiment` | `path` (default `.`), `force_preprocessing` (default off) | Loads the experiment from a project directory (`data/*.xlsx` + `tracking_config.yaml`) and makes it the current experiment for all later steps. `path` of `.` (or blank) resolves to the script's own directory — the loaded experiment's dir, or the replicate being processed in a `run_in_experiments` run. `force_preprocessing` recomputes cached nearest-neighbour preprocessing. |

### QC / filtering

| Action | Key | Parameters | What it does |
|--------|-----|------------|--------------|
| **Filter trackers by quality** | `filter_by_quality` | `min_high_quality` (0–1, default 0.8) | Drops every tracker whose fraction of high-quality frames is below the threshold. Logs how many were kept. |
| **Filter trackers by region** | `filter_by_region` | `regions` (comma-separated, e.g. `T_0, T_1`) | Keeps only trackers whose tracking region matches the list (prefix matching as a fallback). At least one region is required. |
| **Run QC** | `run_qc` | — | Prints the data-quality report and writes `{exp}_data_quality.csv` to `qc/`. |

Filters change the in-memory experiment for the rest of the run — steps after
a filter only see the surviving trackers. Order matters: filter *before* the
analysis steps.

### Analyze

| Action | Key | Parameters | What it does |
|--------|-----|------------|--------------|
| **Run Full Analysis** | `run_analysis` | `facet`, `cutoffs` | The complete pipeline: experiment summary → QC → summary CSVs → statistics → plots. Mirrors the Hub's Run Analysis button. |
| **Summarize** | `summarize` | `facet`, `cutoffs` | Writes `{exp}_Summary.csv` and, when faceted, `{exp}_Summary_Facet.csv`. |
| **Run pairwise comparisons** | `run_pairwise_comparisons` | `facet`, `cutoffs` | Treatment-vs-treatment statistics for every metric relevant to the tracking type. Faceted runs write `{exp}_Stats.txt`; flat runs write `{exp}_Stats_flat.txt`. |
| **Create PDF Report** | `create_report` | — | Builds `{exp}_report.pdf` with QC tables, tracker grids, and plots. |

### Plots

One action per plot type; the palette only shows those valid for the
project's `tracking_type`. All take the same `facet` / `cutoffs` pair.

| Action | Key | Available for |
|--------|-----|---------------|
| **PI** | `plot_pi` | `TWOCHOICETRACKER`, `TWOCHOICECOUNTER` |
| **Percentage** | `plot_percentage` | `TWOCHOICETRACKER`, `TWOCHOICECOUNTER` |
| **Transitions** | `plot_transitions` | `TWOCHOICETRACKER` |
| **Total distance** | `plot_totaldistance` | `TRACKER`, `TWOCHOICETRACKER`, `XCHOICETRACKER`, `PAIRWISEINTERACTIONTRACKER` |
| **Adjusted X position** | `plot_adjusted_x_position` | `XCHOICETRACKER` |
| **Interactions** | `plot_interactions` | `PAIRWISEINTERACTIONTRACKER`, `PAIRWISEINTERACTIONCOUNTER` |

When run from the Hub, every figure a plot step produces opens as a tab in
the plot dock (respecting the **Interactive plots** toggle). Faceted variants
get an "(facet)" suffix in the tab title.

---

## 6. Faceting: how `facet` and `cutoffs` work

Every analysis and plot action shares the same two parameters:

- **`facet`** (checkbox) — run the faceted variant, splitting the recording
  into time phases.
- **`cutoffs`** (comma-separated minutes, e.g. `10, 70`) — the phase
  boundaries. `10, 70` creates three phases: 0–10, 10–70, 70+ minutes.

Resolution order at run time:

1. `facet` off → flat (non-faceted) behaviour; `cutoffs` is ignored.
2. `facet` on and `cutoffs` filled in → those cutoffs are used.
3. `facet` on and `cutoffs` blank → the experiment's own
   `global.facet_cutoffs` from its YAML is used. (The Inspector shows this
   inherited value as grey placeholder text.)
4. `facet` on but no cutoffs anywhere → the step logs a notice and **falls
   back to flat** — it never fails just because cutoffs are missing.

Leaving `cutoffs` blank is the recommended default: across replicates each
sub-experiment then uses *its own* configured cutoffs.

---

## 7. Running scripts

### From the Hub (single project)

The **Scripts** card lists every script in the currently-selected YAML:

- **Run Script** runs the one selected in the drop-down.
- **Run All** runs every script in file order. The experiment state carries
  over from one script to the next (a script without a load step continues on
  whatever the previous script loaded).

Runs execute on a background thread — the log streams to the **Output** tab
when the run completes, failures (with tracebacks) also land in the
**Errors** tab, and figures open as plot tabs.

If an experiment is already loaded in the Hub, a script that has *no*
`load_experiment` step operates directly on it — handy for quick
"filter-and-replot" recipes. A script *with* a load step always reloads
fresh.

### From a Project

The Hub's Project card has its own **Script** picker and **Run script**
button for Project Scripts — including the built-in **Standard pipeline**.
See §8.

### Editing while the Hub is open

The Hub re-reads scripts when the project is (re)loaded. After saving in the
Script Editor, click **Reload** in the Hub's Project card to pick up changes.

---

## 8. Project scripts (two-level scripting)

A **Project** (a directory of replicate experiments, see the user guide §3)
has its own scripting level. Project Scripts live in `project.yaml` under
`scripts:` and use **project actions**; they cannot contain experiment steps,
and experiment scripts cannot contain project steps — the two levels meet in
exactly one place, the `run_in_experiments` bridge.

### Project actions

| Action | What it does |
|--------|--------------|
| `validate_design` | Re-checks every replicate against the project design; fails the script on any mismatch. A cheap guard for the top of a pipeline. |
| `run_in_experiments` | Runs a named **Experiment Script** in every replicate (see below). |
| `run_all_analyses` | Full analysis (and report) for every replicate — the Project card's Run-all as a step. Options: create reports, skip already-analyzed. |
| `build_combined_analysis` | Stacks the replicates' filtered summaries into the project `analysis/` with pooled + mixed-model statistics. |
| `render_publication_figures` | Writes the pooled publication figures to `figures/` from `plot_specs.yaml` (SVG, PDF, or both) — the Plot Editor's saves, headless. |
| `project_report` | Builds `<project>_report.pdf`. |
| `generate_ai_narrative` | Asks an AI provider to write the project narrative. **Soft-fails by default** — a provider error is logged and the script continues. |

### The `run_in_experiments` bridge

`run_in_experiments` takes one parameter — the **name** of an Experiment
Script — and resolves it per replicate:

1. the Project's central **`experiment_scripts:`** section in `project.yaml`
   (author once, runs identically in every replicate), then
2. a script of that name in the replicate's own `tracking_config.yaml`.

Replicates run in order with a `[name]` prefix on every log line. A failing
replicate does **not** stop the others; all failures are summarized when the
script ends. Because each replicate is loaded fresh, the script does *not*
need a `load_experiment` step.

> **Migrating from the old batch mode:** the retired *Batch experiments* mode
> ran a script named `batch` from each sub-folder's own config. That still
> works unchanged through the fallback: add a `project.yaml` to the parent
> (Hub → Create project) and run a Project Script containing
> `run_in_experiments` with `script: batch`.

### The built-in Standard pipeline

The Project card's script picker always offers **Standard pipeline
(built-in)** — it is never written to your yaml, so it always matches the
shipped default:

1. `validate_design`
2. `run_all_analyses`
3. `build_combined_analysis`
4. `render_publication_figures` (SVG)
5. `project_report`

Zero authoring gets a complete project run; your own scripts appear alongside
it in the picker.

### Central experiment scripts

`project.yaml`'s `experiment_scripts:` holds experiment-LEVEL scripts at the
project, in the same spirit as the `design:` section: one definition, every
replicate. Edit them in the Script Editor's *Experiment scripts* level — the
palette and validation are exactly the experiment ones (filtered by the
design's experiment type).

```yaml
# project.yaml
design: { ... }
experiment_scripts:
- name: nightly
  steps:
  - action: run_analysis
    params: {}
  - action: create_report
    params: {}
scripts:
- name: full-pipeline
  steps:
  - action: validate_design
    params: {}
  - action: run_in_experiments
    params: {script: nightly}
  - action: build_combined_analysis
    params: {}
  - action: render_publication_figures
    params: {format: both}
  - action: project_report
    params: {}
```

---

## 9. The YAML behind it all

The Script Editor is a front-end for a plain YAML structure you can also read
and edit by hand. Scripts live under the top-level `scripts:` key of
`tracking_config.yaml`:

```yaml
scripts:
- name: nightly
  steps:
  - action: load_experiment
    params:
      path: '.'
      force_preprocessing: false
  - action: filter_by_quality
    params:
      min_high_quality: 0.9
  - action: run_analysis
    params:
      facet: true
      cutoffs: ''
  - action: create_report
    params: {}
- name: quick-pi                 # ← a second, ordinary script
  steps:
  - action: load_experiment
    params: {path: '.'}
  - action: plot_pi
    params: {facet: true, cutoffs: '10, 70'}
```

Hand-editing rules:

- `scripts:` is a **list**; each entry needs `name` (string) and `steps`
  (list). A missing name displays as "Untitled".
- Each step needs `action` (one of the keys in §5) and `params` (a mapping;
  `{}` or omitted is fine for actions without parameters).
- Unknown `action` keys and malformed parameter values are caught by
  validation before anything runs (§10).
- Parameters you omit take their defaults; parameters not in the action's
  schema are ignored.
- Saving from the Script Editor rewrites only the `scripts:` key — the rest
  of the YAML (global, regions) is preserved. Deleting the last script
  removes the `scripts:` key entirely.

---

## 10. Validation and troubleshooting

Scripts are validated at two points:

- **In the editor**, continuously: step cards with problems get a red marker,
  and the Inspector shows the messages inline. Some checks (anything
  depending on the tracking type) can only run once an experiment is loaded,
  so they are deferred to run time.
- **At run time**, before any step executes: the whole script is checked
  (unknown actions, missing required parameters, malformed `cutoffs`, …). If
  anything fails, the run aborts with a list like `Step 2: cutoffs must be a
  comma-separated list of integers` and **no steps run at all** — a script
  never executes halfway on a validation error.

Common messages and their fixes:

| Message | Fix |
|---------|-----|
| `Script has no steps` | The script is empty — add steps, or delete it. |
| `<action>: no experiment loaded — add a 'Load experiment' step first.` | Put `Load experiment` at the top. (Not needed for scripts run via `run_in_experiments` — each replicate is pre-loaded.) |
| `cutoffs must be a comma-separated list of integers` | Use e.g. `10, 70` — minutes, integers only. |
| `unknown action '<key>'` | Hand-edited YAML has a typo in `action:` — compare with the keys in §5. |
| `run_in_experiments: <rep>: no script named '…'` | Define the script in `project.yaml` `experiment_scripts:` (preferred) or in that replicate's own `tracking_config.yaml`. |
| Script ran but faceted output is missing | No cutoffs anywhere (step blank + no `facet_cutoffs` in the YAML) — the step fell back to flat. Add cutoffs in either place. |

Where to look when something goes wrong: the **Output** tab holds the full
chronological log of the run (each step logs a `── Step i/N: …` header), and
the **Errors** tab collects just the failures and warnings, with tracebacks,
so nothing scrolls out of sight.
