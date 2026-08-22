# PyTrackingAnalysis

Analysis pipeline and desktop UI for insect-tracking data exported from DTrack.
This glossary fixes the domain language; it is not a spec.

## Language

**Batch**:
A directory whose immediate subdirectories holding a `project.yaml` are its
Projects — the same structural rule a Project applies to its Experiments, one
level up. Only existing Projects qualify: a **Batch Run** (one execution of
batch mode over a Batch) never creates or upgrades a `project.yaml`, and
children that are not Projects are skipped with a log line. Purely a
processing convenience: it exists to run many Projects unattended, it is not
itself a Project and holds no analysis outputs of its own, it never pools
results across Projects (each Project has its own design; there is no
cross-Project analysis), and its only product is a per-Project run summary.
Nothing marks a Batch — being one is structural, and a `batch.yaml` at its
root appears only once batch-level scripting is authored, because unlike a
Project a Batch has no authority to declare. A Batch Run executes one
**designated Project Script** in every Project (continue-on-error,
per-Project log prefixes; default: the Report Pipeline, so zero authoring
means "Create report on every Project"). `batch.yaml` holds that
designation (`script:`) and a
central `project_scripts:` section — one recipe serving every Project without
being copied, the `experiment_scripts:` idea one level up.
_Avoid_: study, collection, batch root (the Batch IS the directory), batch
parent, batch script (there is no third script level — the thing a Batch Run
runs IS a Project Script). Unrelated to **Batch Tools** (per-Project
directory operations) and to the retired batch-over-experiments mode.

**Project**:
A directory with a `project.yaml` at its root whose immediate subdirectories
holding a `tracking_config.yaml` are its Experiments — replicates of one
design. The `project.yaml`'s `design:` section is the **authority** for the
shared parameters (experiment type, factors and levels, facets, quality
criteria, counting-region names); a Project owns the Combined Analysis, the
project-level `plot_specs.yaml`/`figures/`, and the Project Report.
_Avoid_: batch parent, parent directory

**Experiment Directory**:
One recording's directory — `tracking_config.yaml`, `data/`, `analysis/`,
`qc/`, its own report — either standalone or as a replicate inside a Project.
(Formerly called the "project directory".)

**Replicate**:
An Experiment inside a Project. Every replicate's resolved config is
hard-validated against the Project's `design:` section (experiment type,
factors and levels, facets, quality criteria, counting-region names in
order); region→treatment assignments, counting-region aliases, fly counts,
and rigs may differ. New replicates are scaffolded from the design.

**Combined Analysis**:
The Project-level results built by stacking each replicate's *filtered*
summaries (exclusions and flags already applied) with an `Experiment` column:
combined summary CSVs, aggregated exclusions, and statistics — pooled
per-fly tests (Welch/Tukey, matching the plots) beside a linear mixed model
(treatment fixed, experiment random) that accounts for between-replicate
variation.

**Project Report**:
`<project>/<project>_report.pdf`: pooled publication figures rendered by the
same Plot Spec/Style system the Plot Editor saves, the pooled + mixed
statistics tables, a per-replicate summary table, and an opt-in AI-written
narrative (same rule as AI Summary: it summarizes, never analyzes).

**Analysis Hub**:
The main app (`pytrack`): a left rail, a horizontal **tile strip** across the
top (Batch · Project · Analyze · Plots · Scripts · AI — each tile shows only
live status, with a **status readout** filling the strip to their right: the
loaded project and experiment in words), and a full-width output/plots area
below. All controls live in a
tile's **anchored panel** (one open at a time; launching a task closes it).
Tiles never move or hide — an inapplicable tile dims and its panel holds the
fix. The **selection names the working container — a Batch or a Project** —
and does only that one job: selecting a Batch lights the Batch tile and dims
the rest; double-clicking a row in its projects table is an ordinary selection
change down to that Project (no drill-in state, no up-button; ADR-0009). The
Hub is **Project-first**: an experiment is loaded only by
double-clicking its row in the Project panel's replicates table, and the
Project tile reports the loaded experiment (ADR-0008).
_Avoid_: card column (the pre-2026-08 layout), Experiment tile (removed)

**Experiment Script**:
A saved, re-runnable step list of experiment-level actions (run analysis,
plots, report…). Lives in an Experiment's `tracking_config.yaml` `scripts:` —
or, for replicates, centrally in the Project's `experiment_scripts:` section,
where one recipe serves every replicate without being copied into their
configs. Central scripts run only through the bridge (`run_in_experiments`,
broadcast or targeted); the Hub's Scripts tile lists solely the loaded
experiment's own `scripts:`.
_Avoid_: recipe, macro

**Project Script**:
A saved step list of project-level actions (`run_in_experiments`,
`run_all_analyses`, `build_combined_analysis`, `render_publication_figures`,
`project_report`, `generate_ai_narrative`, `validate_design`) in
`project.yaml` `scripts:`. Same shape and visual editor as an Experiment
Script, but a separate action registry — levels cannot mix; the only bridge
is `run_in_experiments`, which runs a named Experiment Script in every
replicate — or, with its optional `only:` list of replicate directory names,
in just those replicates (project-defined first, each replicate's own as
fallback, continue-on-error). A replicate where the name resolves nowhere is
logged, counted in the failure summary, and the run continues; unknown
replicate names and unresolvable script names are flagged by pre-run
validation when a Project is in hand.

**Standard Pipeline**:
A built-in Project Script every Project can run without authoring anything:
validate design → run all analyses → build combined analysis → render
publication figures → project report. Never written to `project.yaml`, so it
tracks the shipped default.

**Report Pipeline**:
The built-in Project Script matching the Hub's Create report button plus
curated figures: run all analyses → build combined analysis → render
publication figures (skipped when the Project has no `plot_specs.yaml`) →
project report. The default designation for a Batch Run — preferred there
over the Standard Pipeline because it neither gates on `validate_design`
(which would fail Projects mid-migration) nor renders uncurated default-spec
figures on an unattended run. Code-defined like every built-in; the
conditional figure step never appears in yaml. Listed beside the Standard
Pipeline in every script picker, Project and Batch alike.
_Avoid_: default batch, batch pipeline

**Experiment Type**:
A named bundle (e.g. Valence) that selects one Tracking Type and constrains the
rest of an experiment — the allowed rigs, the facets, the required counting
regions, the set of analyses that run, and the report produced. It is the
top-level thing a scientist chooses; everything else is derived or constrained
from it.
_Avoid_: assay, assay type, protocol, template

**Custom Experiment**:
The absence of a chosen Experiment Type — today's freeform mode, where the
config is driven directly by `tracking_type` with no constraints. A config with
no `experiment_type` key IS a Custom Experiment. Selectable explicitly too.
_Avoid_: generic, freeform, none

**Tracking Type**:
The tracker/counter class used to turn raw frames into metrics (e.g.
`TWOCHOICETRACKER`). An Experiment Type selects exactly one Tracking Type. This
is a lower-level, implementation-facing concept than Experiment Type.
_Avoid_: assay type

**Valence Experiment**:
The first Experiment Type. A two-choice light-preference assay: a two-choice
tracker, Light vs NoLight counting regions (in that order), on a Max or Colosseum
arena (preset calibration only), with the fixed three-phase structure below.

**Counting Region**:
A named group of raw DTrack region labels (its aliases) that an animal can
occupy. A Valence Experiment has exactly two: **Light** and **NoLight**, in that
order.

**Preference Index (PI)**:
A −1..+1 score of how strongly an animal favours the first counting region over
the second. For a Valence Experiment, Light is region-1, so **positive PI means
light-preference**; the group order is fixed to keep that sign stable.
_Avoid_: preference score

**Phase**:
A named time span within an Experiment Type's facet structure. A Valence
Experiment's phases come from its **default** cutoffs [10, 70] (which the user
may change):
- **Acclimation** — 0–10 min.
- **Experiment** — 10–70 min. The phase the primary result is read from.
- **Cooldown** — 70+ min.
The phase names apply only while the cutoffs are the default; changing them
yields plain minute-range labels instead.
_Avoid_: facet (facet = the generic windowing mechanism; a Phase is a named
facet at the type's default cutoffs).

**Primary Phase**:
The facet window the headline result — and the Low-Transition Exclusion — is
read from: the second window when there are two or more, else the only one.
Equals the Experiment phase at Valence's default cutoffs.
_Avoid_: middle facet, experiment window

**Low-Transition Exclusion**:
Valence-only inclusion criterion: a fly is kept only if its Transitions count
during the Primary Phase is at least `min_transitions` (yaml `global:` key;
Valence default 5; 0 = off; no data in the window counts as excluded).
_Avoid_: QC filter (data quality is a separate, always-reported concern)

**AI Summary**:
An optional, AI-written narrative (up to one page) of an experiment's analysis,
generated from the report's own content — figures, stats, and summary tables —
by a user-chosen provider (Anthropic or OpenAI). Opt-in per report, and offered
only when a provider API key is configured in `.env`. A failed generation never
blocks the report; the user gets an error message instead. The AI *summarizes*
the pipeline's analysis; it does not perform its own. An AI Summary is a
derivative of a single analysis run: re-running the analysis deletes it, and
the report embeds it only while the saved file exists.
_Avoid_: AI analysis, AI interpretation

**Excluded Fly**:
A fly removed by the Low-Transition Exclusion — absent from figures, summary
measures, statistics, and the summary CSVs, but listed with its transition
count in the report's removal table and `<exp>_Excluded.csv`, and still shown
in data-quality output.
_Avoid_: dropped fly, filtered fly

**Low-Movement Flag**:
Valence-only QC flag: a fly averaging less than `min_movement` mm/min (yaml
`global:` key; Valence default 140; 0 = off; no data counts as flagged) during
the *first* facet window is reported as potentially an issue — never removed
(`LowMovementFlag` column in the summary CSVs, table in the report). An
experiment with more than half of its analysed flies flagged is itself noted
as potentially an issue on the report cover.
_Avoid_: exclusion (a flag never removes a fly), QC filter

**Publication Figure**:
A hand-curated, journal-ready vector figure (SVG with editable text, or PDF)
rendered by plotnine from a Plot Spec + Plot Style and saved under
`<project>/figures/` — distinct from the matplotlib figures embedded in the
PDF report, and always regenerable from the spec.
_Avoid_: report figure, plot export

**Plot Style**:
A named, reusable look shared by every Publication Figure that references it:
figure size, theme, fonts, point/mean styling, and the treatment→color
mapping. Stored in the Project root's `plot_specs.yaml` under `styles:`;
`default_style:` names the one the Plot Editor auto-loads.
_Avoid_: theme (a plotnine theme is one field inside a style)

**Plot Spec**:
One Publication Figure's content decisions — axis labels, facet and treatment
inclusion/order/display names, y-limits, reference line — plus the name of
the Plot Style it uses. Stored in `plot_specs.yaml` under `plots:`, keyed by
plot id (e.g. `faceted_pi`).
_Avoid_: plot config, settings

**Plot Editor**:
The fourth PyQt6 app (`pytrack-plots`), a **Project-level** tool: opens a
Project, renders a live preview of the pooled figures from the same
Spec+Style that saving uses, and writes the vector Publication Figures.
Presentation only — it never alters `tracking_config.yaml`; opening a
replicate redirects up to its Project.
