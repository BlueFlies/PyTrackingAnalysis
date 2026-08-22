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

The Project **Script** picker runs Project Scripts from `project.yaml`. **Standard pipeline (built-in)** is always available and runs:

1. validate design
2. run all analyses
3. build combined analysis
4. render publication figures
5. create Project report

Use **Edit scripts...** to author custom Project Scripts or centrally held Experiment Scripts. If you need something more specific than the Hub's full report refresh, use a Project Script: scripts still expose lower-level run, combined-analysis, figure-rendering, report, AI, and `run_in_experiments` steps for custom automation.
