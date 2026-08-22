# Analysis Hub workflow

The Hub is the main day-to-day surface. It is Project-first: open a Project, manage its replicates, double-click one replicate to load it, then run experiment-level analysis or project-level combined results.

## Layout

Across the top is a live tile strip: **Project**, **Analyze**, **Plots**, **Scripts**, and **AI**. Tiles show status only. Click a tile, or the matching sidebar item, to open its anchored panel. One panel opens at a time; Esc or clicking elsewhere closes it. Starting a task closes the panel so the streaming output remains visible.

Dimmed tiles still open. Their panels usually contain the next control you need, such as the Project browser or the reminder to load a replicate.

The status readout to the right of the AI tile shows the current Project, path, replicate and analysis counts, and the loaded experiment. Hover it for design details.

## Project panel

The Project panel contains two cards.

**Create/Load** chooses the folder, reloads it, and edits `project.yaml`. The config button reads **Edit config...** when the selected folder is already a Project and **Create config...** when it is not. If the selected folder is a single Experiment Directory, the Hub offers to create the Project on its parent so the experiment becomes a replicate.

**Analysis** is the main Project workspace. It shows the replicate table with config, fly, excluded, flagged, and report status. Double-click a row to load that replicate and run QC. Rows with **Config: missing** are folders with data but no `tracking_config.yaml`; create the config before assigning region treatments.

Project actions:

- **Experiment configs...** - create or edit each replicate's `tracking_config.yaml`.
- **Add experiment...** - create a new replicate directory and config from the Project design.
- **Create report** / **Update report** - analyze every replicate, rebuild Combined Analysis, and write the Project PDF report. The label changes depending on whether `<project>_report.pdf` already exists.
- **Plot editor...** - curate pooled publication figures after a report refresh has created combined faceted data.
- **AI narrative...** - create an optional Project-level AI narrative from the current Combined Analysis and rebuild the PDF to embed it.
- **Script** picker - run the built-in **Standard pipeline** or saved Project Scripts.

For a custom sequence, use **Edit scripts...** and make a Project Script. Scripts can run lower-level steps such as replicate analysis, Combined Analysis, publication figure rendering, report creation, AI narrative, or a named Experiment Script in every replicate.

## Experiment panels

After a replicate is loaded:

- **Analyze** runs the loaded experiment's analysis, QC-only task, report build, summary export, or pairwise comparisons. Run Analysis and Create PDF Report ask for optional run notes.
- **Plots** shows only plots valid for the loaded tracking type. The top-bar **Interactive plots** toggle controls whether plot tabs are live canvases or faster static PNGs.
- **Scripts** runs experiment scripts from the loaded replicate's `scripts:` block.
- **AI** creates an optional AI Summary for the loaded experiment, when an AI provider key is available.

## Faceting

When **Faceted** is checked in the Analyze panel, summaries, pairwise comparisons, and plot buttons use the loaded experiment's `facet_cutoffs`. Button labels add `(facet)` so the output mode is visible before you click.

## Tools

The **Tools** panel lives in the sidebar only. It can open `analysis/` or `qc/`, validate the loaded replicate's YAML, open Batch tools for parent-folder cleanup, and clear the matplotlib cache.

## Output area

- **Output** is the chronological log.
- **Errors** collects warnings and failures, with an unseen count when issues arrive in the background.
- Plots and surfaced text/CSV/PNG artifacts open as additional closable tabs.
- **Clear plots** closes artifact and plot tabs but keeps Output and Errors.
