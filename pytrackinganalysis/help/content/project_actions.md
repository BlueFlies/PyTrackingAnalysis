# Project actions

The Project panel's **Analysis** card runs work across the replicate set. Use it after the Project has a valid `project.yaml` and each replicate has a configured `tracking_config.yaml`.

## Replicate table

The table shows each configured replicate plus any data-looking folder that is still missing a config.

- **Config** is `yes` or `missing`.
- **Flies** is the analyzed fly count, `not analyzed`, or `no data`.
- **Excluded** and **Flagged** show Valence quality results when available.
- **Report** shows whether the per-replicate PDF exists.

Double-click a configured row to load that replicate and run QC. Double-click a missing-config row to create its config from the Project design.

## Setup actions

- **Experiment configs...** opens the config manager for all immediate subdirectories. Create missing configs, create all missing configs, or open an existing replicate in the Config Editor.
- **Add experiment...** creates a new replicate directory and scaffolds its config from `project.yaml`.

## Project pipeline

The Hub has one full Project refresh button:

- **Create report** appears when `<project>/<project>_report.pdf` does not exist.
- **Update report** appears after the Project report exists.

Both labels run the same sequence: unload any currently loaded replicate, analyze every configured replicate, create each per-replicate report, rebuild the Project Combined Analysis under `<project>/analysis/`, and write `<project>/<project>_report.pdf`. If any replicate fails, the Combined Analysis and Project report are not rebuilt.

Use the other Project actions around that full refresh:

- **Plot editor...** - open the Project-level publication figure editor after a report refresh has created combined faceted data. Save plot specs, then click **Update report** to rebuild the PDF with those specs.
- **AI narrative...** - write a Project AI narrative from the current Combined Analysis and rebuild the Project report so the narrative is embedded.

Rebuilding Combined Analysis deletes any saved Project AI narrative because the narrative describes one specific combined result. Because **Create report** and **Update report** rebuild Combined Analysis, run **AI narrative...** after the final report refresh if you want AI prose in the PDF.

## Project scripts

The Project **Script** picker runs Project Scripts from `project.yaml`, listing that file's own scripts first. Every Project is created with one already written there, named **Report pipeline**, so you can open the Script Editor and read exactly what the default run does.

Each script action mirrors a button on this card. **Create / update project report** is therefore the whole **Create report** sequence in one step - analyze every replicate, pool the results, build the PDF - and nothing needs to run before it. (There is no Run-all or Build-combined button, so there is no such action either; both were folded into the report step. Scripts saved before that still run, and the Script Editor flags the old steps so you can delete them.)

**Report pipeline** runs:

1. create / update project report
2. render publication figures - skipped when the Project has no `plot_specs.yaml`

**Standard pipeline (built-in)** is the same, with a `validate design` gate first. Both built-ins appear in the Project and Batch script pickers, below your own scripts.

Use **Edit scripts...** to author custom Project Scripts or centrally held Experiment Scripts. If you need something more specific than the Hub's full report refresh, use a Project Script: scripts still expose figure-rendering, report, AI, design-validation, and `run_in_experiments` steps for custom automation. `run_in_experiments` takes an optional `only:` list of replicate directory names; blank means all replicates, and the Script Editor shows `only:` as a checkable list of the Project's replicates. Before starting a script, the Hub pre-checks it and aborts on a mistyped replicate name or an experiment-script name that resolves nowhere; during a run, a name that matches no replicate is logged, counted in the failure summary, and the remaining replicates still run.

To run one script across many sibling Projects unattended, see the **Batch runs** help topic.
