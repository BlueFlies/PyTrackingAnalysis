# PyTrackingAnalysis

Analysis pipeline and desktop UI for insect-tracking data exported from DTrack.
This glossary fixes the domain language; it is not a spec.

## Language

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
mapping. Stored in `plot_specs.yaml` under `styles:`; `default_style:` names
the one the Plot Editor auto-loads.
_Avoid_: theme (a plotnine theme is one field inside a style)

**Plot Spec**:
One Publication Figure's content decisions — axis labels, facet and treatment
inclusion/order/display names, y-limits, reference line — plus the name of
the Plot Style it uses. Stored in `plot_specs.yaml` under `plots:`, keyed by
plot id (e.g. `faceted_pi`).
_Avoid_: plot config, settings

**Plot Editor**:
The fourth PyQt6 app (`pytrack-plots`): opens a project, renders a live
preview from the same Spec+Style that saving uses, and writes the vector
Publication Figures. Presentation only — it never alters the experiment
definition in `tracking_config.yaml`.
