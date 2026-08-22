# Analysis Hub workflow

The Hub is the day-to-day driver: load an experiment, run analyses, view
plots, run scripts. Its layout is a **tile strip** across the top — Project ·
Analyze · Plots · Scripts · AI — over a **full-width output
area**. Each tile shows live status; clicking it (or its sidebar entry) opens
an anchored **panel** with all the controls. One panel opens at a time; Esc
or clicking elsewhere closes it, and launching a task closes it automatically
so the streaming output is visible. Dimmed tiles still open — their panel
holds the control that fixes the missing state.

Right of the AI tile, the **status readout** always shows what is open: the
project's name and type, its path, the replicate and analysis counts, and the
loaded experiment (or "none loaded"). Hover it for the design factors.

## The panels

1. **Project** — two cards, and the only way into an experiment.
   **Create/Load** chooses the folder and edits its `project.yaml` (**Edit
   config…**, or **Create config…** when the file is missing).
   **Analysis** holds the replicates table — **double-click a row to load
   that replicate** — the project-level actions (Run all, Build combined
   analysis, Project report, Plot editor, AI narrative), and the Project
   **Script** picker (the built-in **Standard pipeline** is always
   available). **Create project…** (also in the sidebar) writes or edits a
   `project.yaml` for a directory you choose.
2. **Analyze** — **Run Analysis**, **Run QC only**, **Create PDF Report**,
   **Summarize**, **Run pairwise comparisons**. Tasks run in the background;
   logs stream to **Output**. Run Analysis and Create PDF Report first ask
   for optional **run notes** (saved as `<Experiment>_Notes.txt`, rendered
   near the top of the report).
3. **Plots** — buttons for plots valid for the loaded tracking type. Each
   click adds an output tab. Toggle **Interactive plots** in the top bar for
   live zoom/pan.
4. **Scripts** — run saved experiment recipes from the YAML `scripts:`
   section. They run against the loaded experiment, so this tile stays dimmed
   until one is loaded.
5. **AI** — request the AI Summary (key-gated).
6. **Tools** (sidebar only) — validate YAML, open `analysis/` / `qc/`,
   Batch tools, clear matplotlib cache.

## Faceting

When **Faceted** is checked (Analyze panel), Summarize / Pairwise / Plots use
the experiment's `facet_cutoffs` (minute phases).

## The output area

- **Output** — chronological log.
- **Errors** — collects warnings/errors only; shows an unseen count.
- Every plot or artifact opens as an additional closable tab; **Clear
  plots** closes them all (Output and Errors stay).
