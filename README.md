# PyTrackingAnalysis

A Python pipeline and desktop UI for analysing insect-tracking data exported
from DTrack. Describe an experiment once in a single `tracking_config.yaml` —
the tracking hardware, the experimental design, and how each physical tracking
region maps to a treatment group — and the pipeline produces summary CSVs,
pairwise statistics, publication-quality plots, and a multi-page PDF report.

## What's included

Three PyQt6 desktop apps sharing a common theme, plus a full Python API:

| Interface | Purpose |
|-----------|---------|
| **Analysis Hub** (`pytrack`) | Day-to-day driver — load experiments, run single or batch analyses, view plots in a tabbed dock |
| **Config Editor** (`pytrack-config`) | Structured editor for `tracking_config.yaml`, with a visual Script Editor for saved analysis recipes |
| **QC Viewer** (`pytrack-qc`) | Per-tracker data-quality tables with XY, distance, and quality-timeline plots |
| **Python API** | Everything scriptable from a notebook or script (`Experiment`, `batch_analyze`, …) |

Supported assay types: plain position tracking, two-choice (tracker or
counter), X-choice, and pairwise-interaction (tracker or counter), with
built-in calibration presets for the small arena, arena max, colosseum, and
obscura rigs.

## Installation

Requires Python ≥ 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/spletcher1/PyTrackingAnalysis.git
cd PyTrackingAnalysis
uv sync
```

`uv sync` creates the virtual environment and installs everything, including
the `pytrack*` commands below.

On Linux, optionally install launcher/taskbar entries for the apps:

```bash
uv run pytrack-install-desktop
```

## Quick start

### Desktop UI

```bash
uv run pytrack                        # Analysis Hub
uv run pytrack /path/to/MyExperiment  # Hub with a project pre-loaded
uv run pytrack-config                 # Config Editor
uv run pytrack-qc /path/to/MyExperiment
```

A *project* is a folder containing a `tracking_config.yaml` plus a `data/`
sub-folder with the DTrack export. In the Hub: pick the project folder, click
**Load experiment**, then run analyses from the cards — output streams to the
dock on the right, and every plot opens as a tab.

### Python

```python
from pytrackinganalysis.Experiment import Experiment

exp = Experiment("/path/to/MyExperiment/")
exp.run_analysis()      # summary → QC → CSVs → statistics → plots
exp.create_report()     # multi-page PDF in analysis/

# Or the same fixed pipeline over every experiment under a parent folder:
from pytrackinganalysis.Experiment import batch_analyze
results = batch_analyze("/path/to/AllExperiments/")
```

Results are written into each project's own `analysis/` and `qc/` folders.

## Documentation

- **[User guide](doc/guide.md)** — environment setup per OS, project
  directory layout, the complete `tracking_config.yaml` reference, all three
  desktop apps, the Python API, batch analysis, and a quick reference.
- **[Scripts & the Script Editor](doc/scripts_guide.md)** — saved analysis
  recipes: authoring them visually, every available action and its
  parameters, faceting rules, and the special `batch` script that powers
  batch mode.

## Repository layout

```
pytrackinganalysis/    the package: analysis pipeline, PyQt6 apps, script engine
doc/                   user guides (start with doc/guide.md)
Testing/               sample projects and test data
```
