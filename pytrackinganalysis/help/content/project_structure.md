# Project directory layout

A **project directory** is the root folder for one experiment. Pass this folder to the Hub / Config Editor / QC Viewer.

## Required layout

```
MyExperiment/
├── tracking_config.yaml      ← required (top level)
├── data/                     ← required
│   ├── ExperimentName.xlsx
│   ├── ExperimentName_Data_1.csv
│   ├── ExperimentName_Data_2.csv
│   └── ...
├── analysis/                 ← created by the pipeline
└── qc/                       ← created by the pipeline
```

## Naming rules

- The `.xlsx` name becomes the experiment name; outputs are prefixed with it.
- Per-tracker CSVs must match `<name>_Data_<N>.csv`. `N` maps to region `T_N-1` in the YAML (`_Data_1.csv` → `T_0`).
- `tracking_config.yaml` must sit next to `data/`, **not** inside it.

## Batch parent layout

For **Batch experiments** mode, select a **parent** folder whose children are full projects:

```
AllExperiments/          ← select this in batch mode
├── Trial1/
│   ├── tracking_config.yaml
│   └── data/ ...
├── Trial2/
│   ├── tracking_config.yaml
│   └── data/ ...
└── ...
```

Each subfolder needs its own config (and, for Hub batch mode, a script named `batch`). See **Batch experiments** and **Batch tools** for more.


## Projects (replicates)

A directory with a `project.yaml` is a **Project**: its subdirectories holding a `tracking_config.yaml` are replicate experiments of one design (validated to share factors and levels exactly). The Hub shows a Project view with per-replicate status, **Run all experiments**, **Build combined analysis** (pooled CSVs + pooled & mixed-model stats into `analysis/`), and **Project report** (`<project>_report.pdf` with pooled publication figures, the stats tables, a per-replicate summary, and an optional AI narrative).

### Two levels, two files

`project.yaml` holds the shared **design**; each experiment directory holds its own `tracking_config.yaml` (rig, region treatments, aliases). A Project directory therefore has **no** tracking config of its own — the Hub's `Config:` selector is empty while one is open, and its **Edit config…** button is off.

To give the experiment directories their configs, use **Experiment configs…** in the Project panel. It lists every subdirectory with its config status, creates the missing ones from the project design (so they validate by construction — you still assign region treatments), and opens an existing one in the Config Editor. Folders without a config are listed in the Experiments table as `missing`; double-clicking one offers to create it. **Add experiment…** does the same for a replicate directory that does not exist yet.
