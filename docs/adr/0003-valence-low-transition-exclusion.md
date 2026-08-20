# Low-transition exclusion is Valence policy applied as an Arena row filter

## Context

The standard Valence analysis must exclude flies that made too few region
transitions during the Primary Phase (default: fewer than 5 during the
Experiment phase) from every result — figures, summary measures, statistics,
and the `_Summary.csv` / `_Summary_Facet.csv` outputs. Three questions had
real alternatives: whose rule is it (Valence-only vs. any two-choice
experiment), where is it enforced (per consumer vs. one choke point vs.
deleting trackers), and what happens to a fly with no data in the Primary
Phase (`Transitions = NA`).

## Decision

- **Valence-only policy.** The criterion is part of what the Valence
  Experiment Type means. `ValenceExperimentType` computes the excluded set
  (from an unfiltered Primary-Phase summary) and supplies the default
  threshold. Custom Experiments are never filtered, so existing projects are
  untouched.
- **`global: min_transitions`** in the yaml, user-editable (ADR-0001: written
  by the create wizard, validated, shown in the Config Editor). Default 5 when
  absent; a fly is kept iff `Transitions >= min_transitions`; `0` disables the
  exclusion.
- **Enforced once, in Arena.** `Experiment` hands the excluded tracker names
  to `Arena`, and `summarize()` / `summarize_facet()` drop those rows on the
  way out (the per-window cache stays unfiltered). Plots, stats, and CSVs all
  read through these methods, so they cannot disagree about the analysis
  population. We rejected filtering at each consumer (any forgotten call site
  silently reintroduces excluded flies) and physically removing trackers
  (data-quality reporting and interactive inspection must still see every
  fly).
- **`NA` excludes.** No occupancy data in the Primary Phase (dead, lost,
  truncated) is treated as failing the criterion — that is precisely the
  inactive-fly case the rule exists to catch. With `min_transitions: 0`, off
  means off and `NA` rows are kept.
- **Exclusions are always accounted for**: a table in the report, a
  `<exp>_Excluded.csv` in `analysis/` (written even when empty, so absence
  never needs interpreting), and a count line in `Stats.txt`.

## Consequences

- Filtered summaries change scientific results relative to pre-exclusion
  runs of the same data; the audit outputs exist so any reader can
  reconstruct who was removed and why.
- Data-quality output deliberately still shows excluded flies — QC describes
  the recording, not the analysis population.
- A future type wanting the same rule should promote the mechanism (the
  Arena filter is already generic); only the policy lives in Valence.
