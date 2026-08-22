# Project directory layout

PyTrackingAnalysis uses two directory levels:

- An **Experiment Directory** holds one DTrack recording: `tracking_config.yaml`, `data/`, and that recording's results.
- A **Project** holds `project.yaml` and one subdirectory per replicate Experiment Directory.

The Hub works from the Project level. The Config Editor and QC Viewer work on one Experiment Directory at a time.

## Experiment Directory

```
MyExperiment/
├── tracking_config.yaml      <- required, top level
├── data/                     <- required
│   ├── ExperimentName.xlsx
│   ├── ExperimentName_Data_1.csv
│   ├── ExperimentName_Data_2.csv
│   └── ...
├── analysis/                 <- created by the pipeline
├── qc/                       <- created by the pipeline
└── ExperimentName_report.pdf <- created by Create PDF Report
```

### Naming rules

- The `.xlsx` workbook name becomes the experiment name used in output filenames.
- Per-tracker CSVs must match `<name>_Data_<N>.csv`. `_Data_1.csv` maps to YAML region `T_0`, `_Data_2.csv` maps to `T_1`, and so on.
- `tracking_config.yaml` must sit next to `data/`, not inside it.

## Project

A directory with `project.yaml` is a **Project**. Its immediate subdirectories that contain `tracking_config.yaml` are replicates. The Project's `design:` section is the authority for the shared design, and each replicate is hard-validated against it when the Project loads.

```
MyProject/
├── project.yaml              <- shared design and Project scripts
├── plot_specs.yaml           <- Plot Editor specs and styles
├── Rep1/
│   ├── tracking_config.yaml
│   └── data/ ...
├── Rep2/
│   └── ...
├── analysis/                 <- Combined Analysis
├── figures/                  <- publication figures
└── MyProject_report.pdf      <- Project Report
```

`project.yaml` owns the shared design: experiment type, design factors and levels, facet settings, quality criteria, and counting-region names. Each replicate's `tracking_config.yaml` owns recording-specific details: rig, tracking-region treatment assignments, counting-region aliases, and optional experiment scripts. A Project root should not have its own `tracking_config.yaml`.

## Project panel

The Hub's **Project** panel has two cards:

- **Create/Load** chooses the folder, reloads it, and edits or creates `project.yaml`.
- **Analysis** shows the replicate table plus Project actions: **Experiment configs...**, **Add experiment...**, **Create report** or **Update report**, **Plot editor...**, **AI narrative...**, and Project scripts.

Double-click a replicate row to load that experiment. Rows marked **Config: missing** are folders with data but no `tracking_config.yaml`; double-clicking offers to create the config from the project design. Use **Experiment configs...** to create or edit replicate configs in bulk. **Create report** appears before the Project PDF exists; **Update report** appears after it exists. Both run every replicate, rebuild Combined Analysis, and write the Project report.

## Migrating an old batch parent

The old Hub batch mode has been absorbed into Projects. Point the Hub at the parent folder and use **Create project** to write `project.yaml`. The dialog can infer the design from the first existing replicate config, and the existing subfolders become replicates. Use **Create report** or the built-in **Standard pipeline** instead of the retired Batch experiments panel.
