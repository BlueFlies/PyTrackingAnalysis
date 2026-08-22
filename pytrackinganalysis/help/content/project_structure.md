# Project directory layout

There are two levels, each with its own marker file:

- An **Experiment Directory** holds one recording — its `tracking_config.yaml`, `data/`, and results.
- A **Project** holds `project.yaml` and a subdirectory per **replicate** — Experiment Directories of one shared design.

Pass either to the Hub; the Config Editor and QC Viewer work on an Experiment Directory.

## Experiment Directory

```
MyExperiment/
├── tracking_config.yaml      ← required (top level)
├── data/                     ← required
│   ├── ExperimentName.xlsx
│   ├── ExperimentName_Data_1.csv
│   ├── ExperimentName_Data_2.csv
│   └── ...
├── analysis/                 ← created by the pipeline
├── qc/                       ← created by the pipeline
└── ExperimentName_report.pdf ← created by Create PDF Report
```

### Naming rules

- The `.xlsx` name becomes the experiment name; outputs are prefixed with it.
- Per-tracker CSVs must match `<name>_Data_<N>.csv`. `N` maps to region `T_N-1` in the YAML (`_Data_1.csv` → `T_0`).
- `tracking_config.yaml` must sit next to `data/`, **not** inside it.

## Project

A directory with a `project.yaml` is a **Project**. Its immediate subdirectories that hold a `tracking_config.yaml` are its replicates, each hard-validated against the Project's `design:` section (experiment type, factors and levels, facets, quality criteria, counting-region names). Region treatments, aliases, fly counts, and rigs may still differ between replicates.

```
MyProject/
├── project.yaml              ← the shared design (the authority)
├── plot_specs.yaml           ← Plot Specs + Styles (Plot Editor)
├── Rep1/                     ← a replicate: a full Experiment Directory
│   ├── tracking_config.yaml
│   └── data/ ...
├── Rep2/
│   └── ...
├── analysis/                 ← the Combined Analysis (pooled CSVs + stats)
├── figures/                  ← publication figures (SVG / PDF)
└── MyProject_report.pdf      ← the Project Report
```

The Hub's **Project** panel drives all of this: the **Create/Load** card picks the folder and edits its `project.yaml` (**Edit config…**, or **Create config…** when the file is missing — both open the Project editor), and the **Analysis** card shows per-replicate status plus **Run all experiments**, **Build combined analysis** (pooled CSVs and pooled + mixed-model statistics into `analysis/`), **Project report**, **Plot editor…**, and **AI narrative…**.

### Two levels, two files

`project.yaml` holds the shared **design**; each replicate holds its own `tracking_config.yaml` (rig, region treatments, aliases). A Project directory therefore has **no** tracking config of its own — nothing at the Project root should be named `tracking_config.yaml`.

To give the replicate directories their configs, use **Experiment configs…** in the **Analysis** card. It lists every subdirectory with its config status, creates the missing ones from the project design (so they validate by construction — you still assign region treatments), and opens an existing one in the Config Editor. Folders without a config are listed in the Experiments table as `missing`; double-clicking one offers to create it. **Add experiment…** does the same for a replicate directory that does not exist yet.

## Migrating an old batch parent

The old "batch parent" mode has been absorbed into Projects. Point the Hub at the parent folder and use **Create project** (left sidebar) to write its `project.yaml`: the design is inferred from the first subdirectory that already has a config, and the existing subfolders become replicates. Then use **Run all experiments** instead of a `batch` script.
