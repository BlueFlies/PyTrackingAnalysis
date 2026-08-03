# PyTrackingAnalysis — Full Codebase Audit

*Reviewed 2026-08-01 against the working tree at commit `55b1522` ("Agent bug search and correct v1"). 13,715 lines of Python across 45 files. Every finding below was reproduced by executing code against the real sample data in `Testing/` or against synthetic fixtures; nothing is reported from reading alone unless explicitly marked.*

---

## 0. Corrections to the brief

Four premises in the review request are out of date. They matter because two of them would have sent the audit hunting for bugs that do not exist.

- **"There is no automated test suite."** There is. `tests/` holds **86 tests that all pass in 1.18 s**, plus `.github/workflows/tests.yml` running them on every push and PR under `QT_QPA_PLATFORM=offscreen`. The suite is fully **hermetic** — it depends on nothing in `Testing/` (which is gitignored and 2.3 GB), synthesising complete projects under `tmp_path`. `pytest>=9.1.1` is declared in `[dependency-groups] dev`. This is genuinely good work and the strongest structural quality in the repo. What is missing is *coverage*, not infrastructure — see §7.
- **"`_Data_<N>.csv` is a per-tracker CSV, one per tracking region; `N` is matched to region `T_N-1`."** No such mapping exists anywhere in the codebase. The `_Data_<N>.csv` files are sequential **time chunks**: `MaxIRSetup_Data_1.csv` holds frames 3–2781 for *all 36* regions, `_Data_2.csv` holds 2782–5559, and so on. Region identity comes from the `TrackingRegion` string column. `Arena.read_all_data` correctly uses `natsorted`, so the classic `_Data_10` before `_Data_2` ordering bug is **not** present — I checked this first and it is handled.
- **The repo map is stale.** `pytrackinganalysis/windowing.py` (208 lines) and `config_validation.py` (187 lines) now exist and are central; `Arena.py` is 1738 lines, `hub.py` 1693, `Experiment.py` 1550.
- **`REVIEW.md` is entirely superseded.** It is dated 2026-04-25 and reviews the initial commit. Every issue it raises has since been fixed — I verified the two it calls CRITICAL (`PairwiseInteractionCounter` now uses `object_ids[:2]`; `SpecialFunctions` now imports `os` and `glob`). It should be deleted or archived, because it currently reads as a live bug list.

---

## 1. Summary

The analysis core is in substantially better shape than the UI layer, and better than the previous review round left it. The time-windowing rework is genuinely excellent: `windowing.py` gives one half-open `[start, end)` rule with correct step-attribution across cutoffs, and I confirmed on 36 real trackers that faceted `TotalDistance` sums to the flat total to within floating-point epsilon (max relative difference 2.7e-16). A full real-data run produces **zero** pandas or numpy warnings — no `SettingWithCopyWarning`, no chained assignment, no view-vs-copy defects. The boolean quality mask in `PairwiseInteractionTracker` is correctly `A & B & ~C & ~D` and carries a comment recording the earlier `|` bug. I went looking for the classic pandas/NumPy type confusions the brief asks about and found essentially none in the core.

The most important thing to fix is not in the analysis core at all: **the Config Editor and Script Editor destroy user configuration files.** Three independent verified paths silently discard data while telling the user "Saved" — saving in the Config Editor deletes every script the Script Editor wrote; a fractional facet cutoff like `10.5` is validated as acceptable and then silently dropped, so every subsequent analysis runs flat with no indication; and emptying the regions table writes the *old* regions straight back, so a scientist re-plating an arena unknowingly analyses the previous plate's design. Compounding this, every save is a truncate-then-write with no atomic replace, so an interrupted save leaves an unparseable YAML file and the original is unrecoverable. `tracking_config.yaml` is the single source of truth for the entire pipeline; corrupting it silently corrupts everything downstream.

Within the analysis core the sharpest issue is that `Arena.analyze_rle_data` compares raw region labels against *group* names, so any lab whose DTrack labels differ from their config group keys — precisely the case the documented `alias:` feature exists to support — gets zeros for one treatment and wrong run lengths for the other, with no warning. Two further items degrade published numbers quietly: `analyze_distance_by_light` builds object-dtype columns via `np.where` on scalars, so one degenerate tracker turns an entire genotype's mean speed into `NaN`; and the statistics output reports no group sizes while `dropna()` silently shrinks them — I produced a `p=0.00013` from a group that had quietly fallen from 18 observations to 8.

**Can a scientist trust the numbers today?** For distance, speed, PI, percentage and transitions under the standard pipeline: broadly yes, with two documented caveats — `TotalDistance` includes frames where tracking was lost (0–19 % inflation per animal, strongly predicted by tracking quality, r = −0.92), and QC silently passes any tracker with no data in the window. For the RLE/event-duration and distance-by-light analyses: no, not without checking whether your region labels match your group keys. For anything that passed through the Config Editor after a Script Editor session: verify the YAML on disk first. The p-values in `*_Stats.txt` should not be reported without independently confirming each group's N.

---

## 2. Critical bugs

Ranked by severity × confidence. All are confirmed by execution.

### C1 — Config Editor "Save" silently deletes every saved script
`pytrackinganalysis/apps/config_editor.py:251` · **Severity: critical · Confidence: high**

**Trigger.** Open `tracking_config.yaml` → open the Script Editor from the toolbar → build and save a script → return to the Config Editor → Save.

**Behavior.** `_dump_config` seeds its output from `self._loaded_config`, a snapshot taken at load time and never refreshed. `ScriptEditorWindow` defines a `scriptsSaved` signal (`window.py:44`, emitted at `:238`) that **is connected nowhere in the codebase**. The Config Editor therefore rewrites the file from a snapshot predating the `scripts:` key. Observed:

```
scripts on disk after Script Editor save: [{'name': 'nightly', 'steps': [...]}]
scripts on disk after Config Editor save: []
```

The dirty indicator stays blank and the user gets a "Saved" confirmation. In batch mode this silently removes the `batch` script every sub-folder depends on.

**Fix.**
```python
# config_editor.py, _launch_script_editor
editor.scriptsSaved.connect(self._reload_external_changes)

def _reload_external_changes(self, _path: str) -> None:
    """Re-read the sections this window does not own after a child wrote the file."""
    with open(self._current_path, encoding="utf-8") as f:
        fresh = yaml.safe_load(f) or {}
    for key, value in fresh.items():
        if key not in ("global", "tracking_regions", "counting_regions"):
            self._loaded_config[key] = value
```

### C2 — A fractional facet cutoff is accepted, then silently deleted
`pytrackinganalysis/apps/_config_tabs.py:431` · **Severity: critical · Confidence: high**

**Trigger.** Type `10.5, 70` into the Facet cutoffs field and Save.

**Behavior.** `validation_errors:383` parses cutoffs with `float()`, so `10.5` passes and the save proceeds. `dump:429` then reparses with `int()`, which raises `ValueError`, caught by `except ValueError: pass`. The key is absent from `dump()`, and because `facet_cutoffs` is in `_OWNED_KEYS`, `_dump_config:262` reads its absence as "the user cleared this field" and drops it. Observed:

```
validation_errors: []
dialogs: {'information': 1, 'warning': 0, 'critical': 0}
saved global: {'tracking_type': 'TRACKER', 'tracking_rig': 'small_arena'}   # facet_cutoffs gone
```

The user sees "Saved", the previously configured `facet_cutoffs: [10, 70]` is gone from disk, and every later faceted analysis silently runs flat. This is a bare `except: pass` in a save path converting a validation gap into permanent data loss.

**Fix.** Make the two parsers agree and never swallow:
```python
# validation_errors(), replacing the float() parse:
try:
    values = [int(x.strip()) for x in text.split(",") if x.strip()]
except ValueError:
    errors.append(f"Facet cutoffs: '{text}' must be whole minutes, comma-separated")

# dump() — validation has already guaranteed this parses; no bare pass:
if self.use_facets.isChecked() and self.facet_cutoffs.text().strip():
    g["facet_cutoffs"] = [int(x.strip()) for x in self.facet_cutoffs.text().split(",") if x.strip()]
```

### C3 — Deleting every region in the UI is silently reverted on save
`pytrackinganalysis/apps/_config_tabs.py:684`, `:743`; `apps/config_editor.py:267` · **Severity: critical · Confidence: high**

**Trigger.** Remove all rows from the Tracking regions (or Counting regions) tab, then Save.

**Behavior.** Both `dump()` methods return `{}` when their table is empty, and `config.update({})` is a no-op, so the *old* regions from `_loaded_config` are written back. Observed:

```
UI rows: 0 0
saved tracking_regions: {'T_1': {...}, 'T_2': {...}}
saved counting_regions: {'Light': {...}, 'NoLight': {...}}
```

Because the dumped output is byte-identical to what is on disk, the dirty indicator also stays blank. A scientist re-plating an arena sees an empty table, clicks Save, gets "Saved", and every subsequent analysis silently applies the previous plate's treatment assignments — the worst possible failure mode, because the numbers look entirely plausible.

**Fix.** Distinguish "empty" from "this tab has nothing to say":
```python
# both tabs — always emit the key
def dump(self) -> dict:
    return {"tracking_regions": regions}

# config_editor._dump_config — an absent section must not be resurrected
for section in (self._tracking_tab.dump(), self._counting_tab.dump()):
    for key, value in section.items():
        if value:
            config[key] = value
        else:
            config.pop(key, None)
```

### C4 — A malformed `scripts:` block kills the whole application (SIGABRT)
`pytrackinganalysis/script_editor/canvas.py:193`, `window.py:197` · **Severity: critical · Confidence: high**

**Trigger.** Any `tracking_config.yaml` whose `scripts:` block is shaped wrong — hand-edited, from an older version, or a merge artifact. Two confirmed shapes: `steps:` as a list of strings, and `scripts:` as a mapping rather than a list.

**Behavior.** `load_scripts:80` returns `list(raw)` with no shape check. `window._load_from_disk:197` then calls `s.setdefault(...)` on a `str`; `canvas.load_steps:193` calls `dict(s)` on a `str`. Both fire inside `ScriptEditorWindow.__init__`, called from a Qt slot, and `_launch_script_editor`'s `try` wraps only the *import*, not the construction. PyQt6 escalates an unhandled slot exception to `qFatal()`. Verified end to end:

```
ValueError: dictionary update sequence element #0 has length 1; 2 is required
EXIT=134            # SIGABRT — whole app killed, unsaved config edits lost
```

**Fix.** Sanitise at the boundary and widen the guard:
```python
# runner.load_scripts
if not isinstance(raw, list):
    raise ValueError("'scripts:' must be a list of {name, steps} mappings")
clean = []
for entry in raw:
    if not isinstance(entry, dict):
        raise ValueError(f"'scripts:' entry is not a mapping: {entry!r}")
    clean.append({**entry, "steps": [s for s in (entry.get("steps") or []) if isinstance(s, dict)]})
return clean

# config_editor._launch_script_editor — construct inside the guard
try:
    from ..script_editor.window import ScriptEditorWindow
    editor = ScriptEditorWindow(self._current_path, parent=self)
except Exception as err:  # noqa: BLE001
    QMessageBox.critical(self, "Script Editor", f"Could not open:\n{err}")
    return
```

### C5 — Every config write is a truncate-then-write with no atomic replace
`pytrackinganalysis/apps/config_editor.py:232`, `script_editor/runner.py:97`, `ui/settings.py:41` · **Severity: critical · Confidence: high**

**Trigger.** Any interruption during serialisation — full disk, power loss, an exception inside `yaml.dump`, `KeyboardInterrupt`.

**Behavior.** `open(path, "w")` truncates the target before the first byte is written. There is no temp file, no `os.replace`, no `fsync`. Verified by injecting a mid-write failure:

```
size before: 1509      size after: 1934
still parses as valid YAML: NO -> ScannerError
leftover temp files: ['tracking_config.yaml']
```

The user's only copy of the experiment definition is gone. `ui/settings.py` has the same defect: an interrupted write left `'{"theme": "da'` on disk and the next load silently returned bare defaults, losing the theme and all eight recent projects.

**Fix.** One helper, applied at all three sites:
```python
def _atomic_write(path: Path, render) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            render(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
```

### C6 — RLE event-duration analysis silently returns zeros when region labels differ from group names
`pytrackinganalysis/Arena.py:1446` · **Severity: critical · Confidence: high**

**Trigger.** `analyze_rle_data` / `analyze_rle_data_facet` on any experiment whose raw `CountingRegion` values are *aliases* rather than the group key. The config format explicitly supports this and the shipped example uses it: `Light: {alias: "Light, LL, L"}`.

**Behavior.** `rle_data['values']` holds raw `CountingRegion` cells (the aliases `L`, `LL`, `N`), while `t1_name`/`t2_name` are `list(counting_regions_design.keys())` — the *group* names. The equality test at 1447-1448 compares aliases against group names and never matches. With `change_none_to_light=True` (the default) line 1431 rewrites `"None"` to the group name, so the only runs that ever match `t1_name` are the out-of-region runs. The sibling `analyze_distance_by_light` gets this right with `.isin(light_vals)`, which is what makes it a bug rather than a convention. Verified on real data, window `(0,10)`:

| | Treatment1_Rows | Treatment2_Rows | Treatment1_MeanLength |
|---|---|---|---|
| labels == group names (correct) | 5 | 6 | 178.6 |
| labels are aliases `L`/`N` (bug) | 9 | **0** | **3.78** |

No exception, no warning; the wrong numbers are written to `*_EventDuration_Summary_Facet.csv`.

**Caveat, stated precisely:** the shipped `Testing/` data emits only `Light`/`NoLight`/`None`, which happen to equal the group keys, so this dataset is unaffected. The bug fires for any lab whose DTrack labels use the alias forms the feature was built for.

**Fix.** Map through the alias table before any comparison:
```python
region_to_group = {alias: group
                   for group, aliases in tracker.counting_regions_design.items()
                   for alias in aliases}
rle_data['group'] = rle_data['values'].map(region_to_group)   # unmapped ("None") -> NaN
if change_none_to_light:
    rle_data['group'] = rle_data['group'].fillna(counting_names[0])
    changes = rle_data['group'].ne(rle_data['group'].shift()).cumsum()
    rle_data = rle_data.groupby(changes, as_index=False).agg({'lengths': 'sum', 'group': 'first'})
rle_filtered = rle_data[rle_data['group'].notna()]
t1_data = rle_filtered[rle_filtered['group'] == t1_name]
t2_data = rle_filtered[rle_filtered['group'] == t2_name]
```
(`counting_names`/`t1_name` must be hoisted above the `change_none_to_light` block.)

### C7 — Closing a plot tab then re-running the same task aborts the Hub (SIGABRT)
`pytrackinganalysis/apps/hub.py:1128` · **Severity: critical · Confidence: high**

**Trigger.** Run any task that prints `Saved: <path>` → an artifact tab appears → close that tab or click "Clear plots" → run the same task again.

**Behavior.** `_on_close`/`clear_figures` call `deleteLater()`, destroying the C++ object, but `self._artifact_tabs[key]` still holds the dead Python wrapper. The next `Saved:` line reaches `_add_artifact_tab`, takes the `cached is not None` branch and calls `indexOf` on a deleted object:

```
RuntimeError: wrapped C/C++ object of type ZoomableTextView has been deleted
  hub.py:1128 in _add_artifact_tab  <- hub.py:1119 in _on_worker_log
EXIT=134 (SIGABRT)
```

Because `_on_worker_log` is a queued slot, PyQt6 escalates to `qFatal()`. The whole Hub disappears and the running analysis is lost. The comment at :1132 shows the author intended to handle this, but `indexOf` raises before it can return `-1`.

**Fix.**
```python
cached = self._artifact_tabs.get(key)
if cached is not None:
    try:
        idx = self._plot_dock.indexOf(cached)
    except RuntimeError:      # C++ side already deleted
        idx = -1
    if idx >= 0:
        self._plot_dock.setCurrentIndex(idx)
        return
    del self._artifact_tabs[key]
```
Better: have `PlotDock` own the mapping and prune it via `widget.destroyed`.

### C8 — Statistics report no group sizes while `dropna()` silently shrinks them
`pytrackinganalysis/Arena.py:1619-1627`, `:1663-1672` · **Severity: critical · Confidence: high**

**Trigger.** Any metric with missing values — `FinalPI` and `Transitions` return `pd.NA` for any window in which an animal never entered a counting region, which is routine in early facets.

**Behavior.** `pd.to_numeric(..., errors='coerce').dropna()` silently discards NA rows, then the printed output reports only `T` and `p`. No N appears anywhere in `*_Stats.txt`. Verified by splitting 36 real trackers into two arms and blanking `FinalPI` for 10 of them:

```
true group sizes: control=18  chr=18   (chr has 10 NA FinalPI -> effective n=8)

############# T-Test #############
Column = FinalPI, Range Minutes = (0.00 , 0.00)
control vs. chr: T=4.55, p=0.00013
```

A reader of that file cannot tell whether the comparison rests on 18 animals or 8. This is the number that goes into a paper. Two aggravating factors: `ttest_ind` uses scipy's default `equal_var=True` (Student's, documented in the guide, but Welch's is the safer default for unbalanced groups), and `run_pairwise_comparisons_facet` applies no multiplicity correction across facets — three facets × three metrics is nine uncorrected tests at α=0.05.

**Fix.**
```python
n1, n2 = len(group1), len(group2)
t_stat, p_value = ttest_ind(group1, group2, equal_var=False)   # Welch's
print(f"{treatments[0]} (n={n1}) vs. {treatments[1]} (n={n2}): T={t_stat:.2f}, p={p_value:.5f}")
dropped = len(summary) - n1 - n2
if dropped:
    print(f"  note: {dropped} tracker(s) excluded — no numeric {metric} in this window.")
```

---

## 3. Correctness risks

Real defects whose scientific impact depends on data or configuration I could not fully pin down.

### R1 — `TotalDistance` includes frames where the animal was not found
`pytrackinganalysis/Tracker.py:246` (and every call path) · **Severity: high · Confidence: high (mechanism); medium (impact on group comparisons)**

`Tracker.summarize` sums `Dist_mm` over every row in the window. `DataQuality` is used only to *report* a fraction (`PercHighQuality`); no frame is ever excluded on quality grounds. The `filter_by_quality` script action drops whole *trackers* below a threshold — it never removes bad *frames* — so the contamination survives every code path including `run_analysis`.

On real data (`Line68284`, 36 animals) the `NotFound` fraction ranges from 0.04 % to 30 % per animal, and lost-tracking frames carry real coordinate jumps rather than NaN:

```
Inflation of TotalDistance from lost-tracking frames, across 36 animals:
  mean 5.01 %   median 1.85 %   max 18.92 %
corr(PercHighQuality, inflation) = -0.924
```

The inflation is almost perfectly determined by tracking quality. **What I could not verify:** whether this biases a *group* comparison, because every shipped sample project has a single treatment level. In this dataset `corr(PercHighQuality, TotalDistance)` is −0.057 (p=0.74), i.e. no detectable effect on the reported total. The risk is real but conditional: if tracking quality correlates with treatment — a darker genotype, a sicker cohort — the distance difference between arms is partly a tracking artifact. Mitigating factor: `PercHighQuality` *is* reported per tracker, so a careful user can see it.

**Fix.** Make the policy explicit rather than implicit:
```python
def summarize(self, range_minutes=(0,0), quality_filter=True):
    data_subset = self.get_data_subset(range_minutes)
    if quality_filter:
        bad = data_subset['DataQuality'] != 'High'
        # A step *arriving at* or *departing from* a lost frame is not a measurement.
        data_subset = data_subset.loc[~(bad | bad.shift(1, fill_value=False))]
```
and emit both `TotalDistance` and `TotalDistance_HighQualityOnly` for one release so users can see the size of the correction on their own data.

### R2 — `np.where` on scalars yields object-dtype columns, poisoning group means with NaN
`pytrackinganalysis/Arena.py:1553-1554` · **Severity: high · Confidence: high**

`np.where(cond, a, b)` with scalar arguments returns a **0-d ndarray**, not a float. Stored in a dict and passed to `pd.DataFrame`, the column infers `dtype('O')`, which defeats pandas' `skipna`. Any tracker with zero time in one region — real and common (`T_8_0` in the shipped fixture) — turns that whole treatment's mean into `NaN`. Verified, `range_minutes=(0,10)`:

```
dtypes: Light_Distance_mm_sec: object, NoLight_Distance_mm_sec: object
as shipped (object):   chr  Light 3.219507   NoLight  NaN      <-- wrong
same data as float64:  chr  Light 3.219507   NoLight  3.591760
```

`pd.to_numeric()` on the exported column also raises `TypeError: len() of unsized object`, so the CSV cannot be re-read numerically without a manual `.map(float)`.

**Fix.**
```python
row[f'{light_group}_Distance_mm_sec']   = float(light_dist / light_time) if light_time > 0 else np.nan
row[f'{nolight_group}_Distance_mm_sec'] = float(nolight_dist / nolight_time) if nolight_time > 0 else np.nan
```

### R3 — QC silently passes any tracker with no data in the window
`pytrackinganalysis/Arena.py:461` · **Severity: high · Confidence: high**

`Tracker.get_data_quality` deliberately returns `pd.NA` for an empty window. The QC mask `data_quality[data_quality['HighQuality'] < cutoff]` evaluates `NA < 0.9` → `NA`, which boolean indexing treats as False, so the row is excluded from the warning set. Verified by taking the worst real tracker and blanking its score:

```
target tracker 'T_0_0' baseline HighQuality=0.6975   (flagged: 9 trackers)
after setting it to NA -> is it in the warning set? False
total flagged now: 8
```

A tracker that contributed **zero frames** is reported as passing — a false negative in exactly the situation QC exists to catch: a dead animal, a truncated recording, or a mis-set facet cutoff.

**Fix.**
```python
hq = pd.to_numeric(data_quality['HighQuality'], errors='coerce')
warning_data = data_quality[hq.isna() | (hq < cutoff)]
if len(warning_data) > 0:
    print(f"Warning: quality below {cutoff}, or no data in range, for some trackers!")
```

### R4 — A blank `experimental_factors` becomes a third treatment arm, switching the test
`pytrackinganalysis/Experiment.py:749-767`, root cause `Arena.py:1612`/`:1657` · **Severity: high · Confidence: high**

One region left with `experimental_factors: ''` — a one-character slip the Config Editor makes easy — is carried through `summary['Treatment'].unique()` as a legitimate level. Verified by blanking `T_5` only:

```
Treatment levels: ['chr', '', 'control']   counts: chr 14 | control 13 | (blank) 1

Multiple Comparison of Means - Tukey HSD, FWER=0.05
group1  group2 meandiff p-adj   lower  upper  reject
           chr   0.1492 0.8507 -0.5345 0.8328  False
       control   0.1038 0.9248 -0.5816 0.7892  False
   chr control  -0.0454 0.8974 -0.2997  0.209  False
```

The intended two-arm design silently became three-arm: the test changed from t-test to Tukey HSD, the multiplicity family grew from 1 to 3, the `chr` vs `control` interval widened accordingly, and an n=1 nameless arm is reported as a treatment. The correct analysis prints `chr vs. control: T=0.36, p=0.72375`. `_design_summary_lines:411` already renders these as `(unassigned)` — the code sees them and neither warns nor excludes them.

**Fix.** Filter and warn in `Experiment.stats()` before delegating, plus a guard in both Arena comparison methods:
```python
summary = summary[summary['Treatment'].astype(str).str.strip() != '']
```

### R5 — `save_plots` facets at a hardcoded 10/70 min when the config declares no facets
`pytrackinganalysis/Experiment.py:237`, `:1023-1026` · **Severity: high · Confidence: high**

`_plot_methods()` injects `cutoffs` only when `self.facet_cutoffs is not None`, and `save_plots` then calls `getattr(self.arena, method_name)(**kwargs)` directly. Every Arena `_facet` signature carries the literal default `cutoffs=(10,70)`, so the plots silently fall back to it. Observed with cutoffs removed from the config:

```
config facet_cutoffs : None
  Arena.plot_pi_facet CALLED WITH cutoffs=(10, 70)   <-- Arena's hardcoded default
Meanwhile Experiment.stats():
(No facet_cutoffs configured — running flat pairwise comparisons.)
```

One PDF then contains whole-recording p-values next to plots split at 10 and 70 minutes, with nothing marking the discrepancy. `plot_totaldistance_facet` and `_save_qc_facet_plot` both guard correctly; `save_plots` is the sole unguarded path.

**Fix.** Skip facet plots when cutoffs are unset, and change all ten Arena `_facet` signatures to `cutoffs=None` with an explicit `raise ValueError` — a one-line-per-signature change that makes this class of bug impossible to reintroduce.

### R6 — A tracking region present in the data but missing from the config aborts the whole pipeline
`pytrackinganalysis/Experiment.py:330-331` · **Severity: high · Confidence: high**

`ExperimentalDesign.get_tracking_region` returns an **empty DataFrame**, never `None`, so the `is not None` guard passes and `.iat[0]` raises:

```
design for T_1_0 -> type: DataFrame  is None? False  empty? True
IndexError: index 0 is out of bounds for axis 0 with size 0
```

`run_analysis` calls `experiment_summary` first, so the entire analysis dies before QC, summaries, stats or plots — and under `batch_analyze` the failure is recorded as a bare `IndexError` naming neither the region nor the config file. The same missing guard at `:850-863` is swallowed by `except Exception`, yielding four blank "(error)" panels. `_save_qc_xy_grid:594` already has the correct `not d.empty` guard — the fix was applied in one of three places.

**Fix.** One shared `_design_field(tracker, column, default)` helper used at all three sites.

### R7 — Frames with undefined speed are silently counted as resting
`pytrackinganalysis/Tracker.py:113-118` · **Severity: medium · Confidence: high**

`IsResting` is initialised `True` for every row and only cleared where `IsWalking` or `IsMicroMove` is True. NaN comparisons yield False, so any frame whose speed is undefined — duplicate or stalled timestamps giving `DeltaSec == 0`, or the leading rows of the rolling window — is reported as resting rather than as missing. Verified on a constructed tracker with a stalled clock:

```
DeltaSec : [0.0, 60.0, 0.0, 0.0]
Speed    : [nan, 0.0, nan, nan]
IsResting: [True, True, True, True]
PercResting=1.0 PercWalking=0.0
```

Three of four frames were unmeasurable, yet the summary reports 100 % resting. Because the four activity fractions always sum to 1, a reader cannot distinguish "the animal rested" from "we could not tell". On the real sample data the effect is negligible (6 rows of 37,286 per tracker, from the rolling-window lead-in), so this matters only for low-frame-rate or timestamp-degraded recordings.

**Fix.** Track an explicit `IsUnmeasurable` mask, exclude those rows from the denominators, and emit `PercUnmeasurable` so the fractions remain interpretable.

### R8 — `summarize()` hands out its cache object, which `summarize_facet()` then mutates
`pytrackinganalysis/Arena.py:537`, `:438` · **Severity: medium · Confidence: high**

`summarize` stores `all_summaries` in `self.computed_summaries[cache_key]` and returns that same object with no `.copy()`; `summarize_facet` then writes `tmp['FacetRange'] = [window]*len(tmp)` into the returned reference. Verified:

```
cols before facet: FacetRange present = False
returns the cached object itself: True
cols AFTER facet call: FacetRange present = True   -> leaked into the cached flat summary
```

Consequence: `summarize(range_minutes=(0,10), write_to_csvfile=True)` emits a stray `FacetRange` column after any faceted call, and any caller that mutates the returned frame corrupts every later read. `(0,0)` is safe by luck — `facet_windows` never produces it — which is why the standard pipeline has not tripped on it.

**Fix.** `.copy()` on both store and return.

### R9 — `plt.cm.get_cmap` was removed in matplotlib ≥ 3.9; both `one_plot=True` paths crash
`pytrackinganalysis/Arena.py:720`, `:754` · **Severity: medium · Confidence: high**

Verified: `a.plot_trackers_x(range_minutes=(0,1), one_plot=True)` → `AttributeError: module 'matplotlib.cm' has no attribute 'get_cmap'`. Installed matplotlib is 3.11.1; the commented example at `Arena.py:1723` is exactly this call, so it worked under an older pin. Fix: `plt.get_cmap('tab10').resampled(...)`. Note the denominator is also wrong — `idx` runs over all trackers while only matching-treatment ones are drawn.

### R10 — `plot_trackers_x_hist` is defined twice; the survivor silently does nothing for most tracking types
`pytrackinganalysis/Arena.py:693` shadowed by `:781` · **Severity: medium · Confidence: high**

Mechanically confirmed — these are the only genuine class-level duplicates in the package (all other `uniq -d` hits are nested closures in separate scopes):

```
effective signature: (self, bins=30, range_minutes=(0, 0))
source line: 781
```

The definition at 693 (guards against COUNTING, loops all trackers) is dead. The survivor's body is gated on `TrackingType.XCHOICETRACKER` with **no else**, so on a TWOCHOICETRACKER experiment `plot_trackers_x_hist()` creates zero figures and raises nothing. Second hazard: the two signatures order their parameters differently, so a notebook calling `plot_trackers_x_hist((0,10))` positionally binds the tuple to `bins`.

**Fix.** Delete 693-703; make the survivor raise for COUNTING and loop all trackers otherwise.

---

## 4. UI and robustness issues

### U1 — The Hub's "Config:" dropdown is ignored by Load experiment
`apps/hub.py:702` · **high · high.** `Experiment.__init__` hardcodes `config_path = os.path.join(project_directory, 'tracking_config.yaml')` (`Experiment.py:110`), so selecting `alt_config.yaml` silently loads the *other* file's tracking type, rig calibration and cutoffs. `_validate_yaml` validates the *selected* file, so the Hub can report "valid" for a config that is never used. Related: `_refresh_scripts()` is never reconnected when the dropdown changes (`hub.py:602`), so the Scripts list keeps showing the previous file's recipes.

### U2 — Plot rendering runs on the GUI thread and races the worker's `plt.show` hook
`apps/hub.py:790-819` · **high · high.** `_render_plot` calls `fn(**kwargs)` directly in the `clicked` handler — the only non-trivial workload in the Hub not dispatched through `TaskWorker`. Worse, `_set_busy` does not disable the Plots card, so a plot click during a running analysis has both threads monkeypatching the module-global `matplotlib.pyplot.show`. Forcing the interleaving:

```
PNGs written by save_plots : []          <-- artifact silently lost
figures stolen into the Hub's capture list: 1
plt.show after everything  : _save_and_close   <-- permanently corrupted
```

The worker's figure is swallowed, no PNG is written, and `create_report` builds a PDF with missing sections — with no error anywhere.

### U3 — Interactive figures are never closed
`ui/widgets.py:395-413` · **high · high.** The non-interactive branch calls `plt.close(figure)`; the interactive branch never does. Verified: `fignums == [1, 2, 3]` after closing all three tabs *and* after `clear_figures()`. Each retains its full RGBA buffer plus the source dataframes. `Arena.py` contains ~20 figure-creating sites and **zero** `plt.close` — `plot_trackers_pis` alone leaves 28 open figures on the sample data.

### U4 — QC Viewer reload duplicates every artifact tab
`apps/qc_viewer.py:287` · **high · high.** `_add_png_tab` uses `addTab` unconditionally, unlike the per-tracker plots which pass `replace_existing=True`. Measured: tabs 5 → 8 → 11 over three reloads; ten reloads gave **36 tabs and 895 MB → 1065 MB RSS**, each tab holding a full-resolution `QPixmap`.

### U5 — Closing the QC Viewer mid-load aborts the process
`apps/qc_viewer.py:263` · **high · high.** No `closeEvent`, and nothing anywhere in the package calls `QThread.wait()`. The `QThread` is destroyed while still running → `abort()`, reproduced as exit 134. Real projects take seconds to load, so the window is closable during the whole vulnerable period.

### U6 — Script Editor writes invalid recipes; Config Editor rig change wipes calibration
`script_editor/window.py:230`, `apps/_config_tabs.py:235` · **medium · high.** `Inspector._validate_and_emit` shows the error banner and then emits `paramsChanged` anyway, and `window._save` has no `validation_issues` gate (unlike `config_editor._write`, which does) — an out-of-range `min_high_quality: 99.0` reaches disk with a "Saved" dialog. Separately, `_on_rig_changed` calls `.clear()` on the fps/mm-per-pixel fields for every non-movie rig, so changing the dropdown silently erases a legitimate re-calibration (`mm_per_pixel: 0.0605` → `''` → key dropped on save).

### U7 — Config round-trip drops per-region keys, undeclared factor tokens, and all comments
`apps/_config_tabs.py:679`, `:740`; `script_editor/runner.py:97` · **high · high.** Top-level and `global:` unknown keys *are* preserved (and pinned by `tests/test_ui.py`), but one level down they are not: the region dumps rebuild each entry from scratch.

| Key | Before | After |
|---|---|---|
| `tracking_regions.T_0.notes` | `'broken tube'` | **lost** |
| `counting_regions.Light.color` | `'yellow'` | **lost** |
| `experimental_factors` | `'Starved, Female, Batch1'` | `'Starved, Female'` |
| comments | 47 lines | **0** |

Saving from the *Script* Editor destroys the shipped config's entire inline documentation (45 comment lines → 0) — an action the user has no reason to associate with the `global:` block.

### U8 — Script Editor card/step index desynchronisation
`script_editor/canvas.py:247` · **high · high.** An unknown action key is skipped without removing the step, so `_cards` and `_steps` fall out of alignment. With `[run_qc, totally_bogus, summarize]`: selecting the Summarize card opens the *bogus* step, and clicking its Remove deletes the bogus step while destroying the Summarize card — leaving a step that still executes but can never be edited.

### U9 — Smaller confirmed items
- **`apps/hub.py:1455`** — child app processes become zombies; the `Popen` handle is polled exactly once, 2 s after launch, and a QC viewer is spawned on *every* successful load.
- **`apps/hub.py:1155`** — analysis failures produce no dialog, only an Errors-tab badge; the user cannot distinguish a completed run from a failed one. `_load_experiment` *does* show a `QMessageBox`, so the inconsistency is within one file.
- **`apps/common.py:66`** — `redirect_stdout` in `TaskWorker.run` rebinds *process-global* `sys.stdout` from a background thread; main-thread `print()` output vanishes into the Hub log for the duration.
- **`Experiment.py:1310-1327`** — the PDF report tints the **best** trackers red: a `HighQuality` of exactly `1.0` takes the `else` branch, becomes `0.01`, and lands in the `< 0.80` bucket. Four of 28 real trackers — the four cleanest recordings — are flagged as worst in the delivered PDF.
- **`Experiment.py:119`** — `glob` for the workbook is unsorted and unfiltered, so an Excel lock file `~$MaxIRSetup.xlsx` is picked up and the experiment dies with `Excel file format cannot be determined`.
- **`Experiment.py:1113`** — `create_report` globs the output directories, so a `_Summary_Facet.csv` left over from a previous configuration is embedded as a current result with no provenance marker.
- **`Experiment.py:212`** — `COUNTER`, `CENTROPHOBISMTRACKER` and `DDROPTRACKER` are absent from both policy tables, so they produce a **zero-byte** `Stats.txt` and no plots while `run_analysis` prints `=== Done. ===` and `batch_analyze` records `'ok'`.
- **`ui/table_model.py:52`** — `rowCount`/`columnCount` ignore the `parent` argument, so every cell claims `len(df)` children; a `QSortFilterProxyModel` with recursive filtering returned 2 rows instead of 1.
- **`ui/zoom.py:94`** — `max(1.0, self._zoom)` clamps the *denominator*, breaking cursor anchoring below 100 % zoom (measured 428 px off at fit-to-window).
- **`apps/qc_viewer.py:81`** — hardcoded 0.90/0.80 thresholds diverge from the core's configurable `qc_cutoff`; the module docstring claims otherwise. The *formula* is correctly delegated to the core — only the threshold differs, which is the more insidious kind of divergence because both numbers are defensible.
- **`install_desktop.py:61`** — unquoted `Exec=` breaks for any venv path containing a space.

### Security: clean
`script_editor` recipes **cannot** cause arbitrary code execution. `runner.run_script:55` calls `validation_issues`, which does `ACTIONS.get(key)` and raises `ScriptError` on any unknown key, strictly *before* the dispatch loop. There is no `eval`/`exec` anywhere, `yaml.safe_load` is used at all four load sites, and the only `getattr` on a computed name builds its target from an internal table, never from YAML. I looked for this specifically and found nothing to report.

---

## 5. Enhancements

**Observability.** `Experiment.py` defines `logger` at line 16 and never calls it once, alongside **64 `print()` calls**; the package total is 112 across eight library modules. A notebook user cannot silence progress chatter, the GUI has to scrape stdout, and `stats()` rebinds `sys.stdout` globally so any concurrent print from another thread lands in the statistics file. Route diagnostics through `logger`, keeping `print` only for deliberately human-facing tables. This also removes the need for the stdout hijack and for `capture_figures`' `plt.show` monkeypatch, which is the root of U2.

**Report N and effect sizes.** Beyond C8, `*_Stats.txt` should carry group sizes, means, SDs, and a multiplicity note. As it stands the file is not sufficient to reproduce or sanity-check the analysis.

**Make the quality policy explicit.** R1 and R3 are both symptoms of `DataQuality` being reported but never acted on. A single documented policy — which frames enter which statistic — plus a `PercUnmeasurable` column would resolve R1, R3 and R7 together.

**Config validation is already good; wire it in harder.** `config_validation.py` is the best-tested module in the package (78 % line coverage, 19 tests) and catches unknown rigs, missing movie calibration, bad multipliers and cutoff ordering. It is not called on the `Experiment(...)` path — only from the Hub button and the editor. Calling it at load time would turn several of the findings above into loud, specific errors.

**Performance.** Two measured items rather than speculative ones: the QC Viewer renders four figures synchronously on the GUI thread per row click (1.04 s at 37 k rows, **5.48 s at 500 k**), which decimation to ~50 k points plus a worker would fix; and `Arena.summarize` is already cached per window, but the cache hands out its own object (R8). I found no `.iterrows()` over frame-level data in the analysis core — the vectorisation is generally sound. The `pyproject.toml` runtime dependencies include `notebook`, `ipykernel`, `pip` and `pickleshare`, which are inappropriate as hard runtime requirements and slow every CI sync.

**Types.** `ExperimentalDesign.tracking_regions` is a DataFrame used purely as a keyed record lookup, and `counting_regions` is a bare `dict[str, list[str]]` passed through five layers. A small frozen dataclass pair would let the empty-DataFrame trap of R6 fail at construction instead of at `.iat[0]`.

---

## 6. Refactoring plan

Ordered by value-to-effort ratio.

**1. Change ten `_facet` signatures from `cutoffs=(10,70)` to `cutoffs=None`.** *Files:* `Arena.py` (10 signatures). *Effort:* minutes. *Value:* eliminates R5 by construction and removes the last magic default from the analysis core. *Risk:* low — any caller relying on the implicit default was already getting a silently wrong window.

**2. Extract the PDF report subsystem.** *Files:* `Experiment.py:1040-1374` (~335 lines, 9 methods) → `report_pdf.py`. It touches only `analysis_path`, `qc_path`, `config`, `parameters` and three `arena` accessors — zero coupling to loading, stats or plotting. *Value:* removes a fifth of `Experiment.py` and makes the quality-tint bug testable. *Risk:* very low; it is already an island.

**3. Collapse the plot backends behind a spec table.** *Files:* `Arena.py:550-1400`. All eight backend pairs share one body — `summarize → _abbrev_df → sns.stripplot → red mean hlines → optional region labels → limits` — differing only in `(metric, hue, ylabel, ylim, region_labels, sharey, remove_partners)`:

```python
@dataclass(frozen=True)
class PlotSpec:
    metric: str; ylabel: str; hue: str | None = None
    ylim: tuple | None = None; region_labels: bool = False
    sharey: bool = True; remove_partners: bool = False
```
with `_strip_panel(data, spec, ax)` (~25 lines) plus `plot_metric` / `plot_metric_facet` returning explicit `Figure` objects. Estimated **~540 lines → ~120**, and the 6 dispatcher pairs (~180 lines) become a lookup. *Value:* highest in the package — it also fixes U3 (figures become caller-owned), the label-at-`y=-1` bug present only in the non-facet twin, and the multi-figure/one-filename overwrite. *Risk:* medium; the red mean-marker alignment depends on `_abbrev_df` producing str dtype so seaborn preserves order-of-appearance. Pin that with a test before starting.

**4. Collapse the four non-plot `_facet` twins.** Each is literally the same loop:
```python
def _over_facets(self, fn, cutoffs, **kwargs):
    frames = []
    for window in windowing.facet_windows(cutoffs):
        tmp = fn(range_minutes=window, **kwargs).copy()   # .copy() also fixes R8
        tmp['FacetRange'] = [window] * len(tmp)
        frames.append(tmp)
    return pd.concat(frames, ignore_index=True)
```
*Risk:* low.

**5. Extract the Hub's task engine and batch runner.** *Files:* `hub.py:1074-1179` → `apps/task_host.py` (owns `_worker`, `_artifact_tabs`, `_progress`; C7, U2 and the missing-dialog bug all live here); `hub.py:965-1072` → `apps/batch_runner.py` and `:1221-1437` → `apps/subdir_ops.py`, both **Qt-free** and therefore unit-testable. *Value:* `tests/test_ui.py` currently pins nothing in `hub.py`, which is why every Hub finding above survived the suite. *Risk:* low for the Qt-free extractions.

**6. Unify the two `_build_parameters` copies.** `Arena.py:93-130` and `Experiment.py:164-210` are near-verbatim duplicates that will drift. Delete Arena's (nothing sets `self.config` there) and delegate. *Risk:* low.

**7. One output-path policy.** `Arena` writes `_Summary.csv`, `_Summary_Facet_NA.csv` (note the stray `_NA`), `_EventDuration_Summary_Facet.csv` and `_DistanceByLight_Facet.csv` into `data_path/` — the *raw data* directory — while `Experiment` writes the same artifacts into `analysis/`. All are built by `self.data_path + self.experiment_name` string concatenation, which assumes a trailing separator while neighbouring lines use `os.path.join`. Route every write through one helper. *Risk:* low, but it changes output locations, so announce it.

**Public API constraint.** Notebooks call `Experiment(...)`, `experiment_summary`, `qc`, `save_summary`, `stats`, `run_analysis`, `create_report`, `batch_analyze`, and on `arena`: `summarize`, `summarize_facet`, `get_tracker`, `run_pairwise_comparisons_facet`, `print_short_data_quality_report`, and the `plot_*` family. Everything else is free to move. Note `Experiment.__getattr__` forwards *any* unknown attribute to `arena`, so a typo will not fail fast — worth narrowing to an explicit allowlist during the refactor.

---

## 7. Testing recommendation

The infrastructure is already right; the gap is coverage. Measured with the stdlib `trace` module (`pytest-cov` is not installed and I did not add it): **33 % overall**, but the distribution is what matters — `windowing.py` 84 %, `config_validation.py` 78 %, `Parameters.py` 76 %, versus **`Arena.py` 22 %** and **`Experiment.py` 20 %**. The best-tested modules are the newest ones; the two giants that produce the published numbers are barely touched.

The highest-risk functions with **zero** executed lines are, in order: `Arena.run_pairwise_comparisons` and `_facet` (the p-value itself), `TwoChoiceTracker.get_transitions` and `rle` (a primary two-choice outcome), `Arena.analyze_distance_by_light` and `analyze_rle_data` (where C6 and R2 live), and `Arena.calculate_distances_for_pairwise_tracker`. Note also that **every shipped sample project has a single treatment level**, so the statistics path is exercised by neither the tests nor the sample data.

Concrete next tests, in priority order:

1. **`test_ttest_and_tukey_are_selected_by_treatment_count`** — extend `write_project` with a `regions=("T_1".."T_4")` variant and two configs yielding 2 and 3 distinct treatments. Capture with `capsys`; assert the `T-Test` header for two levels and the Tukey header for three, plus the "Not applicable" string for one. Add the C8 assertion: the printed line must contain each group's N.
2. **`test_blank_experimental_factors_is_not_a_treatment_arm`** — pins R4. One region blanked; assert the level count stays 2 and a warning is emitted.
3. **`test_transitions_counts_alternations_between_groups`** — `counting_region=("Light","Light","NoLight","NoLight","Light","Light")` → `2`; all-one-region → `0`; empty window → `pd.isna`. Kills the `sum(changes)-1` off-by-one. Add a `("Light","None","Light")` case to pin the documented intent that a `None` gap does not break a run (it currently yields `0`, which I believe is correct but is nowhere written down).
4. **`test_rle_uses_aliases_not_group_names`** — pins C6 directly. Config `Light: {alias: "L, LL"}` with raw values `L`; assert non-zero `Treatment1_Rows` and a plausible mean length.
5. **`test_distance_by_light_columns_are_numeric`** — pins R2. One tracker with zero time in a region; assert `float64` dtype and that the group mean is not `NaN`.
6. **`test_distances_scale_with_mm_per_pixel`** — every existing fixture sets `mm_per_pixel = 1.0`, so all distance assertions are currently identity operations and a dropped multiplication would pass the whole suite. Rebuild with `0.05` and assert `TotalDistance == approx(1.0)`.
7. **`test_a_tracker_with_no_data_fails_qc`** — pins R3.
8. **`test_summarize_does_not_hand_out_its_cache`** — pins R8; three lines.
9. **`test_config_round_trip_preserves_unknown_region_keys`** — pins U7 at the region level, extending the existing top-level round-trip test.
10. **`test_speed_uses_the_rolling_window_at_a_realistic_frame_rate`** — the synthetic fixtures sample once per minute, so `window_size = round(1/60) = 0` and **the production rolling branch never executes in any test**. Use `minutes = [i/1800 for i in range(60)]` (30 fps) with constant velocity.

Fixtures need only small extensions to `tests/conftest.py`: parameterise `FakeDesign.__init__` with `x_mult`/`y_mult` (default 1, so existing callers are unaffected), and give `write_project` optional `regions`, `treatments`, `n_files` and `counting_regions` arguments. Also add `pytest-cov` to the dev group and a `--cov=pytrackinganalysis --cov-report=term-missing` step to `tests.yml`, so the 33 % is visible and these gaps cannot silently reopen.

---

## 8. Appendix: files reviewed

Every file below was read in full.

**Analysis core**

| File | Lines | Note |
|---|---|---|
| `Arena.py` | 1738 | C6, R2, R3, R8, R9, R10; ~20 figure sites and zero `plt.close`; dead+broken `__main__` |
| `Experiment.py` | 1550 | R4, R5, R6; PDF quality-tint inversion; unused `logger` beside 64 `print`s; stale-artifact globbing |
| `Tracker.py` | 595 | R1, R7; windowing correctly delegated; `import time` unused |
| `TwoChoiceTracker.py` | 308 | `get_transitions` semantics sound but wholly untested; PI formula differs from the counter's |
| `TwoChoiceCounter.py` | 275 | Alias summing and shadow-rename are correct and pinned |
| `PairwiseInteractionTracker.py` | 228 | Quality mask correctly `A & B & ~C & ~D`; the one place the brief's mask worry applies, and it is right |
| `PairwiseInteractionCounter.py` | 56 | Previously-reported ndarray bug is fixed (`object_ids[:2]`); `.unique()` order makes "first two" arbitrary |
| `XChoiceTracker.py` | 68 | Correct; `XDist_mm` windowing consistent with `Dist_mm` |
| `Counter.py` | 155 | Mutates the caller's frame in place, but callers pass groupby copies, so no defect; `import time` unused |
| `Parameters.py` | 226 | Clean. Single source of truth for rig calibration; the 0.1106/0.108 divergence is resolved |
| `ExperimentalDesign.py` | 115 | `get_tracking_region` returns an empty frame, not `None` — the root of R6; silently coerces bad multipliers to 1 |
| `windowing.py` | 208 | **Best module in the package.** Half-open windows verified to sum exactly on real data |
| `config_validation.py` | 187 | Thorough and well-tested; not wired into the `Experiment` load path |
| `SpecialFunctions.py` | 161 | Wrappers verified to match their Arena targets; hardcoded `./Data/` and `['Cap','Flav','Ver']` prefixes |
| `__init__.py` | 49 | Lazy PEP-562 submodule loading; correct and well-motivated |
| `__main__.py` | 39 | Clean |
| `install_desktop.py` | 85 | Unquoted `Exec=` field |

**UI layer**

| File | Lines | Note |
|---|---|---|
| `apps/hub.py` | 1693 | C7, U1, U2, U9; every core call site cross-checked — all arities correct |
| `apps/_config_tabs.py` | 743 | C2, C3, U6, U7 — the densest concentration of data-loss bugs in the repo |
| `apps/config_editor.py` | 349 | C1, C3, C5; duplicate Script Editor windows, last writer wins |
| `apps/qc_viewer.py` | 559 | U4, U5; blocking renders; QC *formula* correctly delegated, *threshold* hardcoded |
| `apps/common.py` | 105 | Process-global stdout redirect from a worker thread |
| `ui/widgets.py` | 448 | U3; `savefig` failure leaks the figure |
| `ui/zoom.py` | 222 | Cursor-anchoring bug below 100 % zoom |
| `ui/table_model.py` | 110 | `parent`-ignoring counts; empty and all-NaN frames handled correctly |
| `ui/settings.py` | 67 | Non-atomic write; corrupt-read handling is correct |
| `ui/theme.py` / `ui/icons.py` / `ui/__init__.py` | 163 / 144 / 30 | No findings |
| `script_editor/actions.py` | 605 | Whitelist-validated dispatch — no RCE; `filter_by_region` `IndexError` on keys without `_` |
| `script_editor/canvas.py` | 301 | C4, U8 |
| `script_editor/window.py` | 396 | C4, U6; `scriptsSaved` signal emitted but connected nowhere |
| `script_editor/runner.py` | 98 | C5, U7; no shape validation on load |
| `script_editor/inspector.py` | 333 | Validation warns but does not block |
| `script_editor/palette.py` / `preview.py` | 163 / 22 | No findings |

**Tests, config and docs**

| File | Note |
|---|---|
| `tests/` (6 files, 86 tests) | All pass in 1.18 s; hermetic; windowing and config validation well covered, Arena/Experiment barely |
| `tests/conftest.py` | Synthetic, no file or Qt dependencies; `mm_per_pixel = 1.0` makes distance assertions vacuous |
| `pyproject.toml` | Entry points verified; `pytest` in the dev group; inappropriate runtime deps (`notebook`, `pip`, `pickleshare`) |
| `.github/workflows/tests.yml` | Correct headless CI; no coverage step, no version matrix |
| `tracking_config.yaml` | Valid; exercises the alias feature that C6 breaks |
| `doc/guide.md`, `doc/scripts_guide.md` | Accurate and detailed; the windowing section matches the implementation exactly |
| `README.md` | Does not mention the test suite |
| `REVIEW.md` | **Fully stale** — reviews the initial commit; every issue fixed. Delete or archive |
| `Testing/TestProject`, `Testing/Tatyana` | Used to confirm real column names, dtypes and sentinels; gitignored, 2.3 GB, single-treatment only |
| `Notebooks/`, `PyTrackingTesting.ipynb` | Read to establish the public API surface in §6 |
