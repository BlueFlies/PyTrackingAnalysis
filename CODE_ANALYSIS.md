# Code Analysis - PyTrackingAnalysis

Date: 2026-08-01

## Summary

PyTrackingAnalysis has a usable shape: the domain concepts are recognizable, the package imports are mostly relative, the desktop apps share common UI helpers, and the current working tree has already fixed several issues from the older `REVIEW.md`. The highest-risk problem is not in the UI, though: time-windowed summaries use distances computed before filtering, and faceted windows include the shared edge row in both phases. That can silently overstate `TotalDistance` and `TotalDistancePerMin`, including in QC and plots, so I would not ask a scientist to trust faceted distance numbers until that is fixed and pinned with tests. The next most important fixes are the movie/fps crash, counter alias aggregation, pairwise validity mask, and counter-QC paths. The Config Editor also has a real data-loss path: saving from the main editor reconstructs only the visible config sections and drops top-level keys such as `scripts`. There is no automated test suite or CI test job, so several subtle pandas and numerical assumptions are unguarded. The codebase can get to a trustworthy state without a rewrite, but the first pass should focus on shared windowing, config round-tripping, and small synthetic DataFrame tests.

## Critical Bugs

### 1. Windowed and faceted distance summaries overcount movement

- Location: `pytrackinganalysis/Tracker.py:172`, `pytrackinganalysis/Tracker.py:186`, `pytrackinganalysis/Tracker.py:208`, `pytrackinganalysis/Arena.py:386`, `pytrackinganalysis/Arena.py:396`
- Severity: critical
- Confidence: high
- Trigger: call `Tracker.summarize(range_minutes=(start, end))`, `Arena.summarize_facet(...)`, QC faceted total-distance plots, or any plot/stat using `TotalDistance` after the animal moved across the start of a time window.
- Incorrect behavior: `Dist_mm` is computed over the full trajectory in `Tracker.calculate_speeds_and_feeds()` before the range filter. The first row inside a window still contains the movement from the previous row outside the window. Facets also use inclusive `>= start` and `<= end`, so edge rows can contribute to both adjacent phases.
- Verification: a synthetic tracker with minutes `0, 1, 2` and positions `0, 10, 20` returned `TotalDistance=20` for `(1, 2)`. The within-window movement is `10`. Facets `(0, 1)` and `(1, inf)` returned `10` and `20`, proving the shared edge is counted twice.
- Suggested fix: centralize time slicing and recompute per-window deltas, or at least zero the first in-window delta. Use half-open windows for all non-final facets.

```python
def get_data_subset(self, range_minutes=(0, 0), *, include_end=True):
    if len(range_minutes) != 2:
        raise ValueError("range_minutes must contain exactly two values")
    if tuple(range_minutes) == (0, 0):
        return self.rawdata.copy().reset_index(drop=True)

    start, end = range_minutes
    mask = self.rawdata["Minutes"] >= start
    mask &= self.rawdata["Minutes"] <= end if include_end else self.rawdata["Minutes"] < end
    return self.rawdata.loc[mask].copy().reset_index(drop=True)

def _with_window_deltas(data_subset):
    data_subset = data_subset.copy()
    dx = data_subset["Xpos_mm"].diff().fillna(0)
    dy = data_subset["Ypos_mm"].diff().fillna(0)
    data_subset["Dist_mm"] = np.hypot(dx, dy)
    data_subset["DeltaSec"] = data_subset["Minutes"].diff().fillna(0) * 60
    return data_subset
```

For `summarize_facet`, pass `include_end=False` except for the final `(last_cutoff, inf)` phase.

### 2. Movie/fps tracker input crashes after `Frame` becomes the index

- Location: `pytrackinganalysis/Tracker.py:31`, `pytrackinganalysis/Tracker.py:67`, `pytrackinganalysis/Experiment.py:191`
- Severity: critical
- Confidence: high
- Trigger: `tracking_rig: movie` or any explicit `fps > 0` for tracker-class data.
- Incorrect behavior: `Tracker.__init__()` does `self.rawdata.set_index("Frame", inplace=True)`, which removes the `Frame` column. `calculate_minutes()` then tries `self.rawdata["Frame"] / (fps * 60)` and raises `KeyError: 'Frame'`.
- Verification: instantiating a synthetic `Tracker` with `Parameters(fps=30)` raised `KeyError: 'Frame'`.
- Suggested fix: keep the column when indexing, or compute from the index.

```python
# In Tracker.__init__
self.rawdata = rawdata.set_index("Frame", drop=False).sort_index()

# Or, if the column should stay removed:
self.rawdata["Minutes"] = self.rawdata.index.to_series() / (self.parameters.fps * 60)
```

### 3. Pairwise interaction validity admits low-quality frames

- Location: `pytrackinganalysis/PairwiseInteractionTracker.py:47`, `pytrackinganalysis/PairwiseInteractionTracker.py:52`
- Severity: critical
- Confidence: high
- Trigger: one tracker has `DataQuality != "High"` while the two rows still sum to `NObjects == 2` and have a finite neighbor distance.
- Incorrect behavior: `final_quality = (quality | one_blob) & ...` marks the frame valid if either both data-quality labels are high or the object count sums to two. That means a `NotFound`/`High` pair can be treated as a valid neighbor-distance observation.
- Verification: a synthetic row with self `DataQuality="NotFound"`, neighbor `DataQuality="High"`, `NObjects=1+1`, and `ClosestNeighbor=5` evaluates to `IsNeighborValid=True` with the current mask.
- Suggested fix: require both high quality and a valid pair-distance observation. If collapsed-one-blob frames are scientifically meaningful, keep them as a separate flag and do not mix them into valid distance frames.

```python
both_high = (
    (self.rawdata["DataQuality"] == "High")
    & (self.neighbor_tracker.rawdata["DataQuality"] == "High")
)
exactly_two_objects = (
    self.rawdata["NObjects"] + self.neighbor_tracker.rawdata["NObjects"]
) == 2
valid_distance = (
    self.rawdata["ClosestNeighbor"].notna()
    & self.neighbor_tracker.rawdata["ClosestNeighbor"].notna()
    & (self.rawdata["ClosestNeighbor"] != -1)
    & (self.neighbor_tracker.rawdata["ClosestNeighbor"] != -1)
)
self.rawdata["IsNeighborValid"] = both_high & exactly_two_objects & valid_distance
```

### 4. `TwoChoiceCounter` aliases overwrite instead of summing

- Location: `pytrackinganalysis/TwoChoiceCounter.py:104`, `pytrackinganalysis/TwoChoiceCounter.py:115`, `pytrackinganalysis/TwoChoiceCounter.py:126`
- Severity: critical
- Confidence: high
- Trigger: a canonical counting region has multiple aliases in `tracking_config.yaml`, and more than one alias appears in the data.
- Incorrect behavior: the loop assigns `pivot_table[key] = pivot_table[column]` for each matching alias. The last alias wins instead of summing all aliases. Counts, `PI`, `Percentage`, and downstream stats become wrong.
- Verification: with `Light: ["Light", "LL", "L"]`, minute 0 containing `Light` and `LL` produced `Light=1` instead of `2`; minute 1 containing `Light` and `L` produced `Light=0` instead of `2`.
- Suggested fix: rename the raw canonical column before creating the canonical aggregate, then sum every alias column explicitly.

```python
for key, aliases in self.counting_regions_design.items():
    raw_key = key
    if raw_key in pivot_table.columns:
        pivot_table.rename(columns={raw_key: f"{raw_key}_CountingRegion"}, inplace=True)

    alias_cols = [
        f"{key}_CountingRegion" if alias == key and f"{key}_CountingRegion" in pivot_table.columns else alias
        for alias in aliases
    ]
    alias_cols = [col for col in alias_cols if col in pivot_table.columns]
    pivot_table[key] = pivot_table[alias_cols].sum(axis=1) if alias_cols else 0
```

### 5. Counter experiments crash in the default analysis QC path

- Location: `pytrackinganalysis/Experiment.py:426`, `pytrackinganalysis/Experiment.py:437`, `pytrackinganalysis/Experiment.py:519`, `pytrackinganalysis/Experiment.py:1360`, `pytrackinganalysis/Arena.py:432`, `pytrackinganalysis/Arena.py:444`
- Severity: critical
- Confidence: high
- Trigger: call `Experiment.run_analysis()` or Hub "Run analysis" on `COUNTER`, `TWOCHOICECOUNTER`, or `PAIRWISEINTERACTIONCOUNTER`.
- Incorrect behavior: `run_qc()` knows counters do not support `get_data_quality()`, but `run_analysis()` calls `self.qc()` directly. `qc()` calls `arena.get_data_quality()`, which calls `tracker.get_data_quality()` on counter objects, where the method does not exist.
- Suggested fix: have `run_analysis()` call the guarded QC suite, and make `qc()` fail loudly or skip gracefully when unsupported.

```python
def qc(self, cutoff=0.9, save=True):
    first = next(iter(self.arena.trackers.values()), None)
    if first is None or not hasattr(first, "get_data_quality"):
        print("Skipping data-quality table (not supported for this tracking type).")
        return None
    dq = self.arena.get_data_quality()
    ...

def run_analysis(self, cutoffs=None, qc_cutoff=0.9):
    ...
    self.run_qc(cutoffs=cutoffs, qc_cutoff=qc_cutoff)
    ...
```

Also update `pytrackinganalysis/apps/hub.py:875` and `pytrackinganalysis/script_editor/actions.py:217` to call `run_qc()` when the user requests the full QC suite.

### 6. Script `filter_by_quality` crashes on tracker data and cannot support counters

- Location: `pytrackinganalysis/script_editor/actions.py:177`, `pytrackinganalysis/script_editor/actions.py:184`, `pytrackinganalysis/script_editor/actions.py:185`, `pytrackinganalysis/script_editor/actions.py:188`
- Severity: critical
- Confidence: high
- Trigger: run a documented script step with `filter_by_quality`.
- Incorrect behavior: `tracker.get_data_quality()` returns a one-row DataFrame, and `dq.get("HighQuality", 0.0)` returns a Series. `float(pd.Series([0.95]))` raises `TypeError: float() argument must be a string or a real number, not 'Series'`.
- Verification: reproduced the pandas conversion error directly. The script guide documents this exact action as the first recommended filter.
- Suggested fix: read the first scalar value, skip unsupported counter types with a clear message, and invalidate cached summaries after filtering.

```python
for key, tracker in arena.trackers.items():
    if not hasattr(tracker, "get_data_quality"):
        ctx.log(f"[filter_by_quality] {key}: data quality not available; skipped")
        continue
    dq = tracker.get_data_quality()
    hq = float(dq["HighQuality"].iloc[0])
    if hq >= threshold:
        keep[key] = tracker

arena.trackers = type(arena.trackers)(keep.items())
arena.computed_summaries.clear()
```

### 7. Config Editor can delete `scripts:` and unknown YAML keys on save

- Location: `pytrackinganalysis/apps/config_editor.py:180`, `pytrackinganalysis/apps/config_editor.py:188`, `pytrackinganalysis/apps/config_editor.py:213`, `pytrackinganalysis/apps/config_editor.py:228`, `pytrackinganalysis/apps/_config_tabs.py:320`
- Severity: critical
- Confidence: high
- Trigger: open a YAML file containing `scripts:` or any top-level key not represented by the three visible tabs, then save from the main Config Editor.
- Incorrect behavior: `_dump_config()` creates a new dict from only the Global, Tracking Regions, and Counting Regions tabs. Top-level `scripts:` is dropped, contradicting `doc/scripts_guide.md:322`, which says the editor preserves the rest of the YAML. Unknown nested `global:` keys are also dropped by `GlobalTab.dump()`.
- Suggested fix: keep the loaded YAML as the base document and replace only sections controlled by the main editor.

```python
# Set during _load_path
self._loaded_config = config

def _dump_config(self) -> dict:
    config = dict(getattr(self, "_loaded_config", {}) or {})
    current_global = dict(config.get("global", {}) or {})
    current_global.update(self._global_tab.dump()["global"])
    config["global"] = current_global
    config["tracking_regions"] = self._tracking_tab.dump().get("tracking_regions", {})
    dumped_counting = self._counting_tab.dump()
    if "counting_regions" in dumped_counting:
        config["counting_regions"] = dumped_counting["counting_regions"]
    return config
```

Add a round-trip test that loads a YAML with `scripts:` and an unknown key, saves it, and asserts both are still present.

## Correctness Risks

### 8. DTrack `MSec` time is absolute, so facet phases may be shifted

- Location: `pytrackinganalysis/Tracker.py:62`, `pytrackinganalysis/Counter.py:43`
- Severity: high
- Confidence: medium
- Trigger: standard rig presets set `fps=0`, so minutes come from `MSec / (1000 * 60)`.
- Incorrect behavior: sample data starts around `MSec=182158`, so `Minutes` starts at `3.035968` instead of `0`. A requested phase `(0, 10)` then covers only the first 6.96 minutes of recording, not the first 10 minutes. Different files with different DTrack offsets would not have comparable phase labels.
- Verification: `Testing/TestProject/Data/MaxIRSetup_Data_1.csv` starts at `Minutes=3.035968`; the existing sample summary reports `StartMinutes=3.035968`.
- Suggested fix: decide whether facets should be relative to recording start. If yes, normalize `MSec` by its first value.

```python
msec = self.rawdata["MSec"].astype(float)
self.rawdata["Minutes"] = (msec - msec.iloc[0]) / (1000 * 60)
```

If absolute DTrack time is intentional, add a separate `ElapsedMinutes` column and make faceting explicitly use that.

### 9. Empty windows and zero-duration windows still crash or produce infinities

- Location: `pytrackinganalysis/Counter.py:132`, `pytrackinganalysis/Counter.py:136`, `pytrackinganalysis/Tracker.py:146`, `pytrackinganalysis/Tracker.py:153`, `pytrackinganalysis/Tracker.py:213`, `pytrackinganalysis/TwoChoiceTracker.py:49`, `pytrackinganalysis/TwoChoiceCounter.py:66`, `pytrackinganalysis/PairwiseInteractionTracker.py:128`
- Severity: high
- Confidence: high
- Trigger: a requested time window contains no rows, a single row, or the same start/end minute.
- Incorrect behavior: `Counter.summarize()` indexes `.at[0]` and `.at[lastrow]` without an empty guard. `Tracker.get_data_quality()` divides by `len(data_subset)` and uses `.iat[0]`. `Tracker.summarize()` divides by `obs_minutes` without checking zero. Time-dependent methods read first/last rows before validating the subset.
- Suggested fix: implement a shared empty-window result and use `pd.NA` for rates when denominator is zero.

```python
if data_subset.empty:
    return self._empty_summary(range_minutes)
obs_minutes = data_subset["Minutes"].iat[-1] - data_subset["Minutes"].iat[0]
total_distance_min = pd.NA if obs_minutes == 0 else total_distance / obs_minutes
```

### 10. Facet APIs reject list cutoffs even though docs and config use lists

- Location: `pytrackinganalysis/Arena.py:386`, `pytrackinganalysis/Arena.py:390`, `pytrackinganalysis/Arena.py:1524`, `doc/guide.md:753`
- Severity: high
- Confidence: high
- Trigger: notebook user calls `exp.arena.plot_pi_facet(cutoffs=[10, 70])` or similar guide examples.
- Incorrect behavior: `summarize_facet()` and several special-analysis facet methods only accept `tuple` or `int`, not `list`, and raise `ValueError`.
- Suggested fix: accept any simple numeric sequence and normalize it once.

```python
from collections.abc import Sequence

def _normalize_cutoffs(cutoffs):
    if isinstance(cutoffs, (int, float)):
        values = [cutoffs]
    elif isinstance(cutoffs, Sequence) and not isinstance(cutoffs, (str, bytes)):
        values = list(cutoffs)
    else:
        raise ValueError("cutoffs must be a number or a sequence of numbers")
    return [float(v) for v in values]
```

### 11. Summary cache becomes stale after scripts filter trackers

- Location: `pytrackinganalysis/Arena.py:470`, `pytrackinganalysis/Arena.py:472`, `pytrackinganalysis/Arena.py:488`, `pytrackinganalysis/script_editor/actions.py:188`, `pytrackinganalysis/script_editor/actions.py:210`
- Severity: high
- Confidence: high
- Trigger: call `arena.summarize()` for a range, then run a script filter that mutates `arena.trackers`, then summarize the same range again.
- Incorrect behavior: `computed_summaries` is keyed only by `range_minutes`. It does not know that the tracker set changed, so it can return rows for trackers that have been filtered out.
- Suggested fix: clear `computed_summaries` whenever `arena.trackers` is replaced, or route mutations through an Arena method that owns invalidation.

```python
def set_trackers(self, trackers):
    self.trackers = OrderedDict(trackers)
    self.computed_summaries.clear()
```

### 12. `XCHOICETRACKER` total-distance buttons and reports silently no-op

- Location: `pytrackinganalysis/Experiment.py:33`, `pytrackinganalysis/Experiment.py:35`, `pytrackinganalysis/apps/hub.py:95`, `pytrackinganalysis/apps/hub.py:97`, `pytrackinganalysis/script_editor/actions.py:397`, `pytrackinganalysis/Arena.py:571`, `pytrackinganalysis/Arena.py:584`, `pytrackinganalysis/Arena.py:586`, `pytrackinganalysis/Arena.py:599`
- Severity: high
- Confidence: high
- Trigger: run total-distance plot from Hub, script action, or `Experiment.save_plots()` for `XCHOICETRACKER`.
- Incorrect behavior: callers advertise/register `plot_totaldistance` for X-choice experiments, but `Arena.plot_totaldistance()` and `_facet()` only dispatch for `TRACKER`, `TWOCHOICETRACKER`, and `PAIRWISEINTERACTIONTRACKER`; otherwise they `pass`.
- Suggested fix: include `XCHOICETRACKER` in the Arena dispatcher or remove the button/registry entries.

```python
distance_types = {
    Parameters.TrackingType.TRACKER,
    Parameters.TrackingType.TWOCHOICETRACKER,
    Parameters.TrackingType.XCHOICETRACKER,
    Parameters.TrackingType.PAIRWISEINTERACTIONTRACKER,
}
if self.parameters.get_tracking_type() in distance_types:
    return self.plot_totaldistance_generaltracker(range_minutes)
raise ValueError(...)
```

### 13. Statistical tests do not match the user guide

- Location: `pytrackinganalysis/Arena.py:17`, `pytrackinganalysis/Arena.py:19`, `pytrackinganalysis/Arena.py:1572`, `pytrackinganalysis/Arena.py:1585`, `pytrackinganalysis/Arena.py:1595`, `doc/guide.md:800`
- Severity: high
- Confidence: high
- Trigger: user reads the guide, runs stats, and interprets `*_Stats.txt`.
- Incorrect behavior: the guide says pairwise comparisons are Mann-Whitney U. The code runs `ttest_ind` for exactly two treatment levels and Tukey HSD for more than two.
- Suggested fix: either update the guide and output labels to say t-test/Tukey, or change the code to the non-parametric tests the guide promises. The safer scientific fix is to make the chosen test explicit in config and in the saved output.

```python
from scipy.stats import mannwhitneyu

stat, p_value = mannwhitneyu(group1, group2, alternative="two-sided")
print("############# Mann-Whitney U #############")
```

### 14. Movie rig silently uses defaults if calibration is missing

- Location: `pytrackinganalysis/Experiment.py:191`, `pytrackinganalysis/Experiment.py:192`, `pytrackinganalysis/Experiment.py:193`, `pytrackinganalysis/Arena.py:113`
- Severity: high
- Confidence: medium
- Trigger: `tracking_rig: movie` without explicit `fps` or `mm_per_pixel`.
- Incorrect behavior: the code defaults to `fps=30` and `mm_per_pixel=0.1`. If those are wrong for the movie, every time and distance value is wrong without a warning.
- Suggested fix: require both values for movie rig.

```python
elif rig == "movie":
    missing = [k for k in ("fps", "mm_per_pixel") if k not in global_cfg]
    if missing:
        raise ValueError(f"movie rig requires: {', '.join(missing)}")
    p.set_movie_values(tracking_type, global_cfg["fps"], global_cfg["mm_per_pixel"])
```

### 15. Pairwise tracker partner selection is ambiguous for more than two objects

- Location: `pytrackinganalysis/Arena.py:257`, `pytrackinganalysis/Arena.py:259`, `pytrackinganalysis/Arena.py:261`, `pytrackinganalysis/PairwiseInteractionTracker.py:14`
- Severity: medium
- Confidence: high
- Trigger: a tracking region has three or more objects and `tracking_type=PAIRWISEINTERACTIONTRACKER`.
- Incorrect behavior: the nested loop calls `tracker.set_neighbor(tracker2)` for every same-region tracker, and the last one wins. The chosen partner depends on sorted dictionary order, not a declared pair.
- Suggested fix: validate exactly two objects per pairwise tracking region, or introduce a partner-selection Interface that computes nearest neighbor per frame intentionally.

```python
same_region = [t for t in self.trackers.values() if t.tracking_region_id == region]
if len(same_region) != 2:
    raise ValueError(f"{region}: pairwise tracker requires exactly two objects")
```

### 16. Pairwise preprocessing can misalign or mis-size `ClosestNeighbor`

- Location: `pytrackinganalysis/Arena.py:303`, `pytrackinganalysis/Arena.py:309`, `pytrackinganalysis/Arena.py:321`, `pytrackinganalysis/Arena.py:323`, `pytrackinganalysis/Arena.py:327`
- Severity: medium
- Confidence: medium
- Trigger: raw data is not sorted by `Frame, TrackingRegion`, or a grouped frame has length other than two but `NObjects.sum() == 2`.
- Incorrect behavior: distances are appended in group iteration order and assigned back as one list. If raw row order differs from group order, distances can attach to the wrong rows. In the `NObjects.sum() == 2` branch, exactly two values are appended even if the group length is not two, which can cause assignment length mismatch.
- Suggested fix: write by index instead of by appended list.

```python
rawdata["ClosestNeighbor"] = np.nan
for (_, _), group in rawdata.groupby(["Frame", "TrackingRegion"], sort=False):
    if len(group) == 2 and (group["DataQuality"] == "High").all():
        distance = np.hypot(group["X"].iloc[1] - group["X"].iloc[0],
                            group["Y"].iloc[1] - group["Y"].iloc[0])
        rawdata.loc[group.index, "ClosestNeighbor"] = distance
```

### 17. `get_data_subset()` returns views and detects full range with `sum(range_minutes) == 0`

- Location: `pytrackinganalysis/Tracker.py:184`, `pytrackinganalysis/Tracker.py:186`, `pytrackinganalysis/Tracker.py:187`, `pytrackinganalysis/Counter.py:59`, `pytrackinganalysis/TwoChoiceTracker.py:16`, `pytrackinganalysis/TwoChoiceCounter.py:16`
- Severity: medium
- Confidence: high
- Trigger: filtered pandas slices and unusual ranges such as `(-5, 5)`.
- Incorrect behavior: resetting the index in-place on a filtered slice can trigger `SettingWithCopyWarning` and makes mutation semantics unclear. `sum(range_minutes) == 0` treats `(-5, 5)` as "full recording."
- Suggested fix: use explicit tuple equality and always return copies.

```python
if tuple(range_minutes) == (0, 0):
    return self.rawdata.copy()
return self.rawdata.loc[mask].copy().reset_index(drop=True)
```

### 18. Broad exception swallowing can hide corrupt scientific inputs

- Location: `pytrackinganalysis/TwoChoiceTracker.py:268`, `pytrackinganalysis/TwoChoiceTracker.py:272`, `pytrackinganalysis/TwoChoiceTracker.py:276`, `pytrackinganalysis/TwoChoiceTracker.py:282`, `pytrackinganalysis/Experiment.py:598`, `pytrackinganalysis/Experiment.py:989`
- Severity: medium
- Confidence: high
- Trigger: missing columns, empty windows, invalid design mappings, or zero-duration windows inside summary/plot paths.
- Incorrect behavior: `TwoChoiceTracker.summarize()` catches bare exceptions and emits `pd.NA`, making a broken data path look like a legitimate missing value. Experiment plot code prints warnings but continues, which is fine for reports only if the warning includes enough context.
- Suggested fix: catch expected exceptions narrowly and attach tracker name, range, and input column context.

```python
try:
    final_pi = self.get_final_pi(range_minutes)
except IndexError as err:
    raise ValueError(f"{self.name}: no PI rows for range {range_minutes}") from err
```

### 19. Colosseum calibration differs between generic and pairwise-specific setters

- Location: `pytrackinganalysis/Parameters.py:105`, `pytrackinganalysis/Parameters.py:132`, `pytrackinganalysis/Parameters.py:153`
- Severity: medium
- Confidence: medium
- Trigger: notebook user calls pairwise-specific colosseum setters directly instead of going through `tracking_rig: colosseum`.
- Incorrect behavior: generic colosseum uses `mm_per_pixel=0.108`; pairwise-specific colosseum methods use `0.1106`. That is a 2.4% distance-scale difference.
- Suggested fix: define one rig calibration table and let every setter read from it.

## UI And Robustness Issues

### 20. QC Viewer loads full experiments on the Qt main thread

- Location: `pytrackinganalysis/apps/qc_viewer.py:226`, `pytrackinganalysis/apps/qc_viewer.py:233`, `pytrackinganalysis/apps/qc_viewer.py:242`
- Severity: medium
- Confidence: high
- Trigger: open QC Viewer on a large project.
- Incorrect behavior: `Experiment(...)` reads config/data and constructs trackers synchronously in the UI thread, so the window can freeze during load.
- Suggested fix: reuse `TaskWorker` from `apps/common.py`, disable controls while loading, then populate the table from the worker result.

### 21. Selecting trackers in QC Viewer keeps adding plot tabs

- Location: `pytrackinganalysis/apps/qc_viewer.py:365`, `pytrackinganalysis/apps/qc_viewer.py:386`, `pytrackinganalysis/apps/qc_viewer.py:398`, `pytrackinganalysis/apps/qc_viewer.py:413`, `pytrackinganalysis/apps/qc_viewer.py:429`
- Severity: medium
- Confidence: high
- Trigger: click through many trackers in one QC Viewer session.
- Incorrect behavior: four new plot tabs are added for every selection. Figures are converted and closed by `PlotDock`, but the tabs and pixmaps accumulate until the user manually closes them.
- Suggested fix: replace existing per-tracker diagnostic tabs, or group them under one reusable tracker-detail view.

### 22. Global `sys.stdout` and `plt.show` mutation is fragile in threaded UI runs

- Location: `pytrackinganalysis/apps/common.py:66`, `pytrackinganalysis/apps/common.py:101`, `pytrackinganalysis/Experiment.py:710`, `pytrackinganalysis/Experiment.py:640`, `pytrackinganalysis/script_editor/actions.py:329`
- Severity: medium
- Confidence: medium
- Trigger: overlapping analysis tasks, notebook code running while the UI worker is active, or an exception before restoration.
- Incorrect behavior: stdout/stderr and pyplot show are process-global. The Hub mostly prevents concurrent tasks, but the library helpers are still fragile when reused outside that single-task assumption.
- Suggested fix: move library code toward explicit `Figure` returns and `logging` callbacks; keep stdout/plt interception as a UI Adapter only.

### 23. Hub YAML validation only checks syntax

- Location: `pytrackinganalysis/apps/hub.py:1182`, `pytrackinganalysis/apps/hub.py:1190`
- Severity: medium
- Confidence: high
- Trigger: user clicks "Validate YAML" with an unknown rig, missing tracking regions, malformed aliases, or invalid movie calibration.
- Incorrect behavior: the tool reports "parses cleanly" even when the config will fail or silently fall back during analysis.
- Suggested fix: call the same config validation Interface proposed below, not just `yaml.safe_load()`.

### 24. Main Config Editor silently drops invalid numeric fields

- Location: `pytrackinganalysis/apps/_config_tabs.py:340`, `pytrackinganalysis/apps/_config_tabs.py:345`, `pytrackinganalysis/apps/_config_tabs.py:363`, `pytrackinganalysis/apps/_config_tabs.py:365`, `pytrackinganalysis/apps/_config_tabs.py:376`
- Severity: medium
- Confidence: high
- Trigger: user types an invalid cutoff, micromove range, or interaction-distance list and saves.
- Incorrect behavior: `ValueError` is caught with `pass`, so the bad value disappears from the saved config without an inline error.
- Suggested fix: validate tab data before write and block save with field-specific messages.

### 25. Data table sorting is advertised by views but the model does not sort

- Location: `pytrackinganalysis/ui/table_model.py:16`, `pytrackinganalysis/ui/table_model.py:33`
- Severity: low
- Confidence: high
- Trigger: user clicks table headers in views that call `setSortingEnabled(True)`.
- Incorrect behavior: the model has no `sort()` implementation, so sorting either does nothing or depends on view behavior.
- Suggested fix: implement `sort(column, order)` by sorting `self._df` and resetting the model.

### 26. Subapp processes are launched without lifecycle tracking

- Location: `pytrackinganalysis/apps/hub.py:1432`, `pytrackinganalysis/apps/hub.py:1438`
- Severity: low
- Confidence: high
- Trigger: launch Config Editor or QC Viewer from Hub, then close Hub.
- Incorrect behavior: subprocesses are intentionally independent, but the Hub cannot surface later launch/runtime failures or clean them up.
- Suggested fix: if independent child apps are desired, document it in a tooltip. If not, store `Popen` handles and terminate or warn on Hub close.

## Enhancements

### Input validation at config load

The code currently validates `tracking_type` well, but it leaves several important mistakes until late analysis or silently falls back. Add a `ConfigModel` Module that parses and validates `tracking_config.yaml` once, then is reused by `Experiment`, `Arena`, Hub validation, Config Editor, and Script Editor. It should check: known rig names, movie `fps`/`mm_per_pixel`, nonempty `tracking_regions`, exactly two `counting_regions` for two-choice types, nonempty aliases, increasing numeric `facet_cutoffs`, multiplier values restricted to `-1` or `1`, and allowed script action keys/params.

### Logging instead of library `print()`

The analysis core prints progress, warnings, and stats directly. That is convenient in notebooks but hard to test and brittle in threaded UI. Use `logging.getLogger(__name__)` in library Modules and let notebooks enable a console handler. The UI can attach a log-handler Adapter that streams messages to the Output tab.

### Type hints and small data models

`tracking_regions_design`, `counting_regions_design`, action params, and summary rows are passed around as dicts/DataFrames with implicit columns. Add dataclasses or typed dictionaries at the edges, especially for config and summary rows. This will make line-level bugs such as alias overwrites and missing `get_data_quality()` visible earlier.

### Performance improvements with scientific leverage

The pairwise preprocessing loop iterates group-by-group and prints every 1000 groups. Rewriting it to assign by index will also improve correctness. Repeated summary calls currently cache only by time range; after fixing invalidation, consider caching raw CSV loads or preprocessing results by source file timestamp. Plotting functions should return explicit `Figure` objects, which will remove much of the current `plt.show` interception.

### Documentation alignment

The Sphinx `source/*.rst` files still use top-level module names such as `.. automodule:: Arena`; package-relative docs should use `pytrackinganalysis.Arena`. `source/PairwiseInteractionCounter Backup.rst` uses an invalid module name with a space. The user guide also needs to match the actual stats tests or the stats code needs to match the guide.

## Refactoring Plan

1. Add a `windowing` Module for time ranges and trajectory deltas. Files touched: `Tracker.py`, `Counter.py`, `TwoChoiceTracker.py`, `TwoChoiceCounter.py`, `PairwiseInteractionTracker.py`, `Arena.py`. New Interface: `window = tracker.window(range_minutes, include_end=True)` returning a copy with consistent `Minutes`, `Dist_mm`, and `DeltaSec`. Value: fixes the biggest scientific bug and removes duplicated subset code. Risk: medium because many summaries and plots depend on it; test first.

2. Add a `ConfigModel` Module and make UI tabs adapters to it. Files touched: `ExperimentalDesign.py`, `Experiment.py`, `Arena.py`, `apps/config_editor.py`, `apps/_config_tabs.py`, `script_editor/runner.py`, `script_editor/actions.py`, `apps/hub.py`. Value: prevents key loss, makes validation shared, and gives Hub "Validate YAML" real meaning. Risk: medium; keep YAML output stable and preserve unknown keys.

3. Replace plot dispatch chains with a plot registry and explicit Figure returns. Files touched: `Arena.py`, `Experiment.py`, `apps/hub.py`, `apps/qc_viewer.py`, `script_editor/actions.py`. New Interface: `PlotRegistry.available(tracking_type)` and `PlotRenderer.render(plot_key, facet=None) -> list[Figure]`. Value: fixes X-choice total-distance mismatch, reduces facet/non-facet boilerplate, and removes `plt.show` interception. Risk: medium-high because notebook users call many public plot methods; keep wrapper methods as deprecating adapters.

4. Split `Experiment.py` into `ProjectLoader`, `AnalysisPipeline`, `ReportBuilder`, and `BatchRunner` Modules. Keep `Experiment` as the public facade used by notebooks. Value: the current top-level class mixes config loading, artifact paths, QC, stats, plots, PDF pages, and batch helpers. Risk: medium; preserve method names like `run_analysis`, `save_summary`, and `create_report`.

5. Split pairwise interaction logic into its own Module. Files touched: `PairwiseInteractionTracker.py`, `PairwiseInteractionCounter.py`, `Arena.py`. New Interface: `PairwiseDistances.compute(rawdata, mode)` and `PairingPolicy.validate(region_objects)`. Value: fixes partner selection and distance preprocessing in one place. Risk: medium; use synthetic two-object and three-object fixtures.

6. Split `Arena.py` by Depth: `ArenaDataLoader`, `TrackerFactory`, `SummaryEngine`, `StatsEngine`, and plotting adapters. Keep `Arena` as a shallow facade. Value: lower cognitive load in the largest core file and makes summary/stat tests independent of matplotlib and file I/O. Risk: high if done all at once; do this after the windowing and config Interfaces exist.

7. Split `apps/hub.py` into project-state, task orchestration, plot dock integration, and batch-tools Modules. Value: UI changes become safer and the worker/log behavior becomes reusable by QC Viewer. Risk: low-medium if it follows the existing helper patterns.

## Testing Recommendation

Start with `pytest` and pure synthetic DataFrames. The first suite should avoid PyQt and file dialogs; it should exercise the numerical core directly.

1. `test_tracker_movie_fps_uses_frame_index_or_column`: build a three-row tracker with `Frame`, `RelX`, `RelY`, and `fps=30`; assert no `KeyError` and expected minutes.

2. `test_tracker_windowed_distance_recomputes_inside_range`: synthetic minutes `0, 1, 2`, positions `0, 10, 20`; assert `(1, 2)` total distance is `10`, not `20`.

3. `test_summarize_facet_uses_half_open_windows`: same fixture; assert phase distances do not double-count the shared cutoff row.

4. `test_two_choice_counter_sums_aliases`: raw rows with `Light`, `LL`, and `L` aliases in the same minute; assert canonical `Light` equals the sum of all aliases.

5. `test_pairwise_quality_requires_both_high`: one row `NotFound` and one row `High`, `NObjects=1+1`, finite distance; assert `IsNeighborValid` is false.

6. `test_counter_empty_window_returns_na_or_clear_error`: call `Counter.summarize((999, 1000))`; assert the chosen behavior is stable and documented.

7. `test_experiment_run_analysis_counter_skips_qc_table`: construct or monkeypatch a counter experiment and assert `run_analysis()` reaches summaries instead of crashing in `qc()`.

8. `test_script_filter_by_quality_extracts_scalar`: monkeypatch a tracker returning `pd.DataFrame({"HighQuality": [0.95]})`; assert the action keeps it and clears summary cache.

9. `test_config_editor_round_trip_preserves_scripts`: load YAML with `scripts:` and an unknown top-level key through the serializer; assert both survive save.

10. `test_special_function_defaults_match_arena`: introspect wrapper signatures in `SpecialFunctions.py` against target Arena methods, especially `analyze_distance_by_light_facet`.

Fixture sketch:

```python
def tracker_raw(minutes=(0, 1, 2), xs=(0, 10, 20)):
    return pd.DataFrame({
        "Frame": range(len(minutes)),
        "MSec": [m * 60_000 for m in minutes],
        "RelX": xs,
        "RelY": [0] * len(minutes),
        "X": xs,
        "Y": [0] * len(minutes),
        "DataQuality": ["High"] * len(minutes),
        "NObjects": [1] * len(minutes),
        "CountingRegion": ["None"] * len(minutes),
        "Indicator": [0] * len(minutes),
        "Time": ["00:00:00"] * len(minutes),
        "Millisec": [0] * len(minutes),
    })
```

Add CI after the first few tests exist. The current workflows do not run pytest.

## Appendix: Files Reviewed

- `README.md`: current project overview, UI/API promises, entry points, and docs links.
- `REVIEW.md`: stale prior review; used only to avoid re-reporting already-fixed issues.
- `CODE_REVIEW_PROMPT.md`: duplicate of the attached audit prompt; used to confirm requested scope.
- `pyproject.toml`: dependencies, Python version, package metadata, and console scripts.
- `tracking_config.yaml`: root example config and intended config schema.
- `doc/guide.md`: user-guide intent spec, config reference, output expectations, API examples.
- `doc/scripts_guide.md`: script storage, action behavior, validation promises, and YAML round-trip promises.
- `pytrackinganalysis/Parameters.py`: tracking enums, rig presets, calibration values.
- `pytrackinganalysis/ExperimentalDesign.py`: YAML parsing and design validation.
- `pytrackinganalysis/Tracker.py`: tracker initialization, time conversion, distance/speed, summary, QC, plots.
- `pytrackinganalysis/Counter.py`: counter initialization, time conversion, summary, plots.
- `pytrackinganalysis/TwoChoiceTracker.py`: PI/percentage/transitions, summaries, plotting, broad exception paths.
- `pytrackinganalysis/XChoiceTracker.py`: adjusted X-position summaries and plotting.
- `pytrackinganalysis/PairwiseInteractionTracker.py`: pairwise distance, validity mask, interactions, summaries.
- `pytrackinganalysis/TwoChoiceCounter.py`: event-count aggregation, aliases, PI/percentage, plotting.
- `pytrackinganalysis/PairwiseInteractionCounter.py`: pseudo-trackers for two-object counter interactions.
- `pytrackinganalysis/Arena.py`: tracker factory, preprocessing/postprocessing, summaries, plotting dispatch, special analyses, stats.
- `pytrackinganalysis/Experiment.py`: public project API, parameter building, QC, summaries, stats, plots, reports, batch helpers.
- `pytrackinganalysis/SpecialFunctions.py`: backward-compatible wrappers and summary stacking helpers.
- `pytrackinganalysis/__init__.py`: package exports and lazy import behavior.
- `pytrackinganalysis/__main__.py`: CLI/app dispatch.
- `pytrackinganalysis/install_desktop.py`: Linux desktop launcher installation.
- `pytrackinganalysis/apps/common.py`: worker, stdout/stderr capture, matplotlib figure capture.
- `pytrackinganalysis/apps/hub.py`: main desktop app, tasks, scripts, plot dock, batch tools, subapp launching.
- `pytrackinganalysis/apps/config_editor.py`: YAML load/save, dirty state, Script Editor launch.
- `pytrackinganalysis/apps/_config_tabs.py`: Global, Tracking Regions, and Counting Regions tab serializers.
- `pytrackinganalysis/apps/qc_viewer.py`: QC app loading, table, tracker diagnostic plots, export actions.
- `pytrackinganalysis/apps/__init__.py`: app package marker.
- `pytrackinganalysis/ui/widgets.py`: shared cards, buttons, logs, plot dock.
- `pytrackinganalysis/ui/zoom.py`: zoomable image/plot view.
- `pytrackinganalysis/ui/table_model.py`: DataFrame to Qt table model.
- `pytrackinganalysis/ui/theme.py`: light/dark palette and stylesheet.
- `pytrackinganalysis/ui/icons.py`: icon drawing and caching.
- `pytrackinganalysis/ui/settings.py`: JSON user settings and recent projects.
- `pytrackinganalysis/ui/__init__.py`: UI helper exports.
- `pytrackinganalysis/script_editor/actions.py`: action registry, validators, executors, plot capture.
- `pytrackinganalysis/script_editor/runner.py`: script loading, saving, validation, execution.
- `pytrackinganalysis/script_editor/window.py`: Script Editor window and YAML persistence.
- `pytrackinganalysis/script_editor/inspector.py`: parameter editor widgets.
- `pytrackinganalysis/script_editor/canvas.py`: ordered step cards.
- `pytrackinganalysis/script_editor/palette.py`: action palette and tracking-type filtering.
- `pytrackinganalysis/script_editor/preview.py`: YAML preview.
- `pytrackinganalysis/script_editor/__init__.py`: script editor package marker.
- `source/conf.py`: Sphinx config.
- `source/index.rst`: docs index.
- `source/modules.rst`: Sphinx module list.
- `source/Arena.rst`: stale top-level automodule reference.
- `source/Counter.rst`: stale top-level automodule reference.
- `source/ExperimentalDesign.rst`: stale top-level automodule reference.
- `source/Parameters.rst`: stale top-level automodule reference.
- `source/PairwiseInteractionTracker.rst`: stale top-level automodule reference.
- `source/PairwiseInteractionCounter.rst`: stale top-level automodule reference.
- `source/PairwiseInteractionCounter Backup.rst`: invalid module name with a space.
- `source/Tracker.rst`: stale top-level automodule reference.
- `source/TwoChoiceTracker.rst`: stale top-level automodule reference.
- `source/TwoChoiceCounter.rst`: stale top-level automodule reference.
- `source/XChoiceTracker.rst`: stale top-level automodule reference.
- `.github/workflows/claude.yml`: workflow checked; no pytest job.
- `.github/workflows/daily_docs.yaml`: workflow checked; docs automation only.
- `Makefile`: Sphinx build wrapper.
- `make.bat`: Windows Sphinx build wrapper.
- `.gitignore`: generated artifacts and local files.
- `.python-version`: Python version pin.
- `Testing/TestProject/tracking_config.yaml`: sample project config.
- `Testing/TestProject/Data/MaxIRSetup_Data_1.csv`: sampled real DTrack schema, quality labels, MSec start, counting regions.
- `Testing/TestProject/analysis/MaxIRSetup_Summary.csv`: sampled existing output, start/end minute semantics.
- `Testing/TestProject/analysis/MaxIRSetup_Summary_Facet.csv`: sampled faceted output shape.
- `Testing/TestProject/analysis/MaxIRSetup_Stats.txt`: sampled stats artifact naming/content.
- `Testing/TestProject/qc/MaxIRSetup_data_quality.csv`: sampled QC output.
- `Testing/Tatyana/*/tracking_config.yaml`: inspected as sample config family by inventory/search, not full semantic audit.
- `Notebooks/SimpleTracker.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/ColloseumTwoChoiceCounter.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/ColloseumTwoChoiceCounterTrimmed.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/ExampleMaxExperiment_Design.txt`: inspected as legacy design context by inventory/search.
- `Notebooks/ToBeUpdated/Example_Design_Colloseum.txt`: inspected as legacy design context by inventory/search.
- `Notebooks/ToBeUpdated/PariwiseInteractinTrackerMaxTemplate.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/PariwiseInteractionCounter.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/PariwiseInteractionTracker.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/SimpleCounter.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/TwoChoiceCounter.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/TwoChoiceTracker.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/ValenceOnColloseum.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/ValenceOnMaxTemplate.ipynb`: searched for public API usage patterns.
- `Notebooks/ToBeUpdated/XChoiceTracker.ipynb`: searched for public API usage patterns.
- `PyTrackingTesting.ipynb`: searched for public API usage patterns.
