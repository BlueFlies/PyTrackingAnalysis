# Analysis Hub workflow

The Hub is the day-to-day driver: load an experiment, run analyses, view
plots, run scripts. Its layout is a **tile strip** across the top — Project ·
Experiment · Analyze · Plots · Scripts · AI — over a **full-width output
area**. Each tile shows live status; clicking it (or its sidebar entry) opens
an anchored **panel** with all the controls. One panel opens at a time; Esc
or clicking elsewhere closes it, and launching a task closes it automatically
so the streaming output is visible. Dimmed tiles still open — their panel
holds the control that fixes the missing state.

## The panels

1. **Project** — choose the directory (experiment or Project); launch Config
   Editor / QC Viewer; the Project view with the replicates table,
   project-level actions (Run all, Build combined analysis, Project report,
   Plot editor, AI narrative), and the Project **Script** picker (the
   built-in **Standard pipeline** is always available).
2. **Experiment** — **Load experiment** caches the experiment for reuse;
   **Create project…** writes or edits a `project.yaml`.
3. **Analyze** — **Run Analysis**, **Run QC only**, **Create PDF Report**,
   **Summarize**, **Run pairwise comparisons**. Tasks run in the background;
   logs stream to **Output**. Run Analysis and Create PDF Report first ask
   for optional **run notes** (saved as `<Experiment>_Notes.txt`, rendered
   near the top of the report).
4. **Plots** — buttons for plots valid for the loaded tracking type. Each
   click adds an output tab. Toggle **Interactive plots** in the top bar for
   live zoom/pan.
5. **Scripts** — run saved experiment recipes from the YAML `scripts:`
   section.
6. **AI** — request the AI Summary (key-gated).
7. **Tools** (sidebar only) — validate YAML, open `analysis/` / `qc/`,
   Batch tools, clear matplotlib cache.

## Faceting

When **Faceted** is checked (Analyze panel), Summarize / Pairwise / Plots use
the experiment's `facet_cutoffs` (minute phases).

## The output area

- **Output** — chronological log.
- **Errors** — collects warnings/errors only; shows an unseen count.
- Every plot or artifact opens as an additional closable tab; **Clear
  plots** closes them all (Output and Errors stay).
