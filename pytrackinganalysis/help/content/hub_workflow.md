# Analysis Hub workflow

The Hub is the day-to-day driver: load an experiment, run analyses, view plots, run scripts.

## Cards

1. **Project** — choose the experiment folder and YAML; launch Config Editor or QC Viewer; Reload to re-scan.
2. **Load** — **Single project** caches the experiment for reuse. **Batch experiments** runs the `batch` script in every child folder (see Batch experiments help).
3. **Analyze** — **Run Analysis**, **Run QC only**, **Create PDF Report**, **Summarize**, **Run pairwise comparisons**. Tasks run in the background; logs stream to **Output**.
4. **Plots** — buttons for plots valid for the loaded tracking type. Each click adds a PlotDock tab. Toggle **Interactive plots** in the top bar for live zoom/pan.
5. **Scripts** — run saved recipes from the YAML `scripts:` section.
6. **Tools** — validate YAML, open `analysis/` / `qc/`, Batch tools, clear matplotlib cache.

## Faceting

When **Faceted** is checked, Summarize / Pairwise / Plots use the project’s `facet_cutoffs` (minute phases).

## Plot dock

- **Output** — chronological log.
- **Errors** — warnings and failures (batch skips, validation problems, task errors). Unseen issues show a count on the tab title.
- Plot / artifact tabs are closable; **Clear plots** closes them without removing Output/Errors.
