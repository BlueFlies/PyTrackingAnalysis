# Analysis Hub workflow

The Hub is the main day-to-day surface. It is Project-first: open a Project, manage its replicates, double-click one replicate to load it, then run experiment-level analysis or project-level combined results.

## Layout

Across the top is a live tile ribbon: **Batch**, **Project**, and **Experiment**, one per level of the hierarchy. Batch and Project work on containers; Experiment is the loaded replicate. Click **Experiment** to expand a row of four sub-tiles beneath it — **Analyze**, **Plots**, **Scripts**, and **AI**, the tools that act on the loaded experiment — and click it again to fold them away (choosing Batch or Project, or clicking into the output, folds them away too). Tiles show status only. Click Batch, Project, or a sub-tile to open its anchored panel under the ribbon. One panel opens at a time; Esc or clicking elsewhere closes it. Running tasks keep the panel in place while the output streams below.

Dimmed tiles still open. Their panels usually contain the next control you need, such as the Project browser or the reminder to load a replicate. The Experiment tile is the exception: with nothing loaded it has nothing to expand, so it stays dimmed and inert until you double-click a replicate.

The status readout to the right of the Experiment tile shows the current Project, path, replicate and analysis counts, and the loaded experiment. Hover it for design details.

## Batch panel

The selection names a Batch or a Project. Selecting a folder with Projects anywhere beneath it lights the **Batch** tile: its panel holds **Choose batch folder...** (pick the folder and every Project inside it auto-loads, at any depth), a checkable projects table showing usable replicates and blocked experiments, **Rescan folder**, a **Script** picker for the designated Project Script, and **Run batch** — which opens a review window before anything runs. Double-click a row to select that Project; right-click it to fix a blocked experiment or edit its removed regions. See the **Batch runs** help topic for the full reference.

## Project panel

The Project panel contains three cards, in the order the work happens: the Project, its experiments, then the analysis over them.

**Create/Load** is the Project itself: one button per way in, then what is loaded — name, experiment type, replicate count, design factors and any load warnings. See the **Creating and opening a Project** help topic.

- **Open Project** - the directory and its `project.yaml` both exist. Picking the one already open re-reads it from disk.
- **Create project...** - the Project does not exist yet. Choose where it goes and name it; the directory is created and `project.yaml` written into it.
- **Initialize existing directory...** - the directory exists but has no `project.yaml`. Choose it and it becomes the Project, keeping its own name; any experiment subdirectories already in it become the replicates, and the shared design is inferred from the first one that has a config.
- **Edit config...** - reopen the Project editor on the selected directory's `project.yaml`. It reads **Create config...** when the selected folder is not a Project yet; if that folder is a single Experiment Directory, the Hub offers to create the Project on its parent so the experiment becomes a replicate.
- **Validate YAMLs** - not a way in, but the check over the Project that is open: it reads this Project's `project.yaml` *and* every replicate's `tracking_config.yaml` in one pass. See **Validating** below.

**Experiments** is the replicates themselves. It shows the replicate table with config, fly, excluded, flagged, and report status. Double-click a row to load that replicate. A replicate without an analysis runs QC as it loads and opens the QC viewer and the Analyze panel; an analyzed one loads as it is and opens the Experiment group, where **Run QC** and **Run Analysis** redo either on request. Rows with **Config: missing** are folders with data but no `tracking_config.yaml`; create the config before assigning region treatments. All three buttons wait for a Project, because a replicate's design is inherited from `project.yaml`. See the **Creating experiments** help topic.

- **Create experiment...** - the replicate does not exist at all. Give it a name; the directory, its `data/` folder and a `tracking_config.yaml` scaffolded from `project.yaml` are created for you. Nothing else is asked, because everything else is the Project's. The scaffold is then finished one of two ways, and the Hub asks which: **Edit config...** opens it in the Config Editor, **Copy config from...** replaces it with a config from an experiment that already works — checked against the project design before it is written, and refused (scaffold intact) if it would not conform.
- **Experiment configs...** - create or edit each replicate's `tracking_config.yaml`.
- **Initialize existing directory...** - the directory is already in the Project but has no `tracking_config.yaml`. Pick it from the list of config-less folders: a recording still loose at its root is filed into `data/` and every other loose file into `extra_files/`, the config is scaffolded from the project design, and the Config Editor opens on it so you can set the rig and assign region treatments.

**Analysis** is what you do with the Project once its experiments exist:

- **Create report** / **Update report** - analyze every replicate, rebuild Combined Analysis, and write the Project PDF report. The label changes depending on whether `<project>_report.pdf` already exists.
- **Plot editor...** - curate pooled publication figures after a report refresh has created combined faceted data.
- **AI narrative...** - create an optional Project-level AI narrative from the current Combined Analysis and rebuild the PDF to embed it.
- **View reports** - open the pooled Project report alongside the per-replicate ones.
- **Removed regions...** - declare the tracking regions the experimenter removed, so their flies leave the figures, statistics and summary CSVs.
- **Script** picker, at the bottom - run the built-in **Report pipeline** or **Standard pipeline**, or saved Project Scripts.

For a custom sequence, use **Edit scripts...** and make a Project Script. Scripts can run lower-level steps such as replicate analysis, Combined Analysis, publication figure rendering, report creation, AI narrative, or a named Experiment Script in every replicate.

## Experiment panels

After a replicate is loaded:

- **Analyze** runs the loaded experiment's analysis, QC-only task, report build, summary export, or pairwise comparisons. Run Analysis and Create PDF Report ask for optional run notes. The **Outputs** help topic lists every file these write and where it lands; **QC Viewer** covers the per-tracker quality table.
- **Plots** shows only plots valid for the loaded tracking type. Each plot opens as a static PNG tab in the output area.
- **Scripts** runs experiment scripts from the loaded replicate's `scripts:` block.
- **AI** creates an optional AI Summary for the loaded experiment, when an AI provider key is available.

## Faceting

When **Faceted** is checked in the Analyze panel, summaries, pairwise comparisons, and plot buttons use the loaded experiment's `facet_cutoffs`. Button labels add `(facet)` so the output mode is visible before you click.

## Validating

**Validate YAMLs** lives at the bottom of the Project panel's **Create/Load** section. With a Project open it checks that Project's `project.yaml` *and* every replicate's `tracking_config.yaml` in one pass — parse errors and semantic problems (unknown rig, missing calibration, design mismatch) alike — reporting each file separately with a count at the end. With a standalone experiment loaded it checks that one config.

There is no Tools tile: folder-opening is the file manager's job, and matplotlib's cache is now cleared automatically every time the Hub closes, so a stale font cache can never break the next session's figures.

## Output area

- **Output** is the chronological log.
- **Errors** collects warnings and failures, with an unseen count when issues arrive in the background.
- Plots and surfaced text/CSV/PNG artifacts open as additional closable tabs.
- **Clear plots** closes artifact and plot tabs but keeps Output and Errors.

Artifacts surfaced here are the same files written under `analysis/`, `qc/`, and `figures/` - see the **Outputs** help topic for the full list.
