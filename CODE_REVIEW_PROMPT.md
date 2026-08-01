# Code Analysis Prompt — PyTrackingAnalysis

*Paste everything below the line into a fresh code-analysis agent session rooted at
`/home/scott/GithubLocal/PyTrackingAnalysis`.*

---

## Your task

Perform a full-codebase audit of **PyTrackingAnalysis**, a Python 3.13 scientific
analysis package that ingests insect-tracking data exported from DTrack hardware and
produces summary CSVs, statistics, plots, and PDF reports. It ships both a library API
(used from Jupyter notebooks) and a three-app PyQt6 desktop UI.

I want a prioritized, evidence-backed report covering **bugs, correctness risks,
enhancements, and refactoring opportunities**. Read the actual code — do not review from
filenames, docstrings, or the existing `README.md`/`REVIEW.md`, both of which describe a
*previous* review round and may be stale or wrong about the current state of the tree.

## Repository map

Total ≈11,800 lines of Python. Roughly half is analysis logic, half is UI.

**Analysis core** (`pytrackinganalysis/`)
| File | Lines | Role |
|---|---|---|
| `Arena.py` | 1699 | Largest module. Plotting + analysis dispatch across tracking types; writes CSVs |
| `Experiment.py` | 1510 | Top-level user-facing API; orchestrates arenas, reports, batch runs |
| `Tracker.py` | 557 | Base class: per-object trajectory data, quality filtering, `summarize()` |
| `TwoChoiceTracker.py` / `XChoiceTracker.py` / `PairwiseInteractionTracker.py` | 293 / 65 / 218 | `Tracker` subclasses per experiment paradigm |
| `Counter.py` + `TwoChoiceCounter.py` + `PairwiseInteractionCounter.py` | 146 / 266 / 56 | Parallel `Counter` hierarchy for event-count data |
| `Parameters.py` | 210 | `TrackingType`/`TrackingClass` enums, rig presets, `Parameters` dataclass |
| `ExperimentalDesign.py` | 115 | Parses `tracking_config.yaml` into a design object |
| `SpecialFunctions.py` | 156 | Thin backward-compat wrappers delegating to `Arena` |
| `install_desktop.py` | 85 | Untracked/new: writes desktop launcher entries |

**UI layer**
- `apps/hub.py` (1666) — Analysis Hub, the main app; loads experiments, runs analyses, tabbed plot dock
- `apps/config_editor.py` (313) + `apps/_config_tabs.py` (657) — YAML config authoring
- `apps/qc_viewer.py` (501) — per-tracker QC tables and diagnostic plots
- `apps/common.py` (105) — shared app bootstrap, subprocess launching
- `ui/` — `widgets.py` (422), `zoom.py` (222), `theme.py` (163), `icons.py` (144), `table_model.py` (92), `settings.py` (67)
- `script_editor/` — visual node/recipe editor: `actions.py` (592), `window.py` (396), `inspector.py` (333), `canvas.py` (301), `palette.py` (163), `runner.py` (98), `preview.py` (22)

**Other context**
- Entry points defined in `pyproject.toml`: `pytrack`, `pytrack-hub`, `pytrack-config`, `pytrack-qc`, `pytrack-install-desktop`
- `tracking_config.yaml` — root example config; `doc/guide.md` — user guide (treat as intent spec)
- `Testing/TestProject` and `Testing/Tatyana` — sample data trees you may read to understand expected input schemas
- `Notebooks/`, `PyTrackingTesting.ipynb` — notebook usage patterns
- **There is no automated test suite.** No pytest, no CI test job. Note this in your report.
- There is uncommitted work in progress on `main` (Experiment, `__main__`, apps/*, ui/*, `install_desktop.py`). Review the working tree as it stands, not just committed code.

## What to look for

Weight your effort toward the analysis core — a silent numerical error there corrupts
published scientific results, which is far worse than a UI glitch.

**1. Correctness and data-integrity bugs (highest priority)**
- Pandas/NumPy type confusion: calling DataFrame/Series methods (`.index`, `.drop`,
  `.iloc`) on the ndarray returned by `.unique()`, `.values`, `.to_numpy()`
- Boolean-mask logic errors in quality filters — especially `|` vs `&` and misplaced
  `~`. Check every mask that combines "invalid" conditions; "neither A nor B" is
  `~A & ~B`, and an OR there silently admits corrupt frames
- Chained assignment / `SettingWithCopyWarning` and views-vs-copies: does a filtered
  subset write back to the parent frame, or silently not?
- Division by zero and empty-DataFrame paths: `total_frames == 0`, all-NaN groups,
  a tracker with zero valid observations, an arena with one object
- Off-by-one and inclusive/exclusive boundaries in time windowing (`range_minutes`,
  bin edges, frame→minute conversion). Verify a function that claims to respect a time
  range actually filters *before* aggregating rather than aggregating the full raw data
- Unit consistency: mm vs pixels vs arbitrary units; column names that encode units
  (`_mm`) versus the values actually stored in them; per-frame vs per-second rates and
  whether frame rate is read from config or hardcoded
- NaN handling: does `mean()`/`sum()` skip NaN where the science requires counting it as
  a gap? Are sentinel values (e.g. `-1` distances) filtered everywhere they appear, or
  only in some call paths?
- Mutable default arguments, and shared mutable state on class attributes
- Import errors: bare absolute imports inside the package (`from Parameters import X`
  instead of `from .Parameters import X`), and names used but never imported —
  grep for module usage vs the import block in every file
- Duplicate `def` of the same name in a class or module (the second silently wins)
- Silent exception swallowing: bare `except:` / `except Exception: pass` that turns a
  data error into a plausible-but-wrong number

**2. Consistency across the parallel class hierarchies**
`Tracker`/`Counter` and their subclasses implement overlapping concepts. Check whether
equivalent methods (`summarize`, quality filtering, time-range handling) behave
identically where they should, and flag places where a fix was applied to one branch but
not its sibling. `SpecialFunctions.py` allegedly delegates to `Arena` — verify each
wrapper's signature and semantics actually match its target, since a drifted wrapper is a
silent behavior change for notebook users.

**3. UI layer**
- Work performed on the Qt main thread that can block the GUI (file I/O, full analysis
  runs, plot rendering over large frames). Identify what should move to a worker
- Matplotlib figure lifecycle: figures created per plot and never closed leak memory
  across a long Hub session; check for `plt.figure` without a matching close, and
  whether the pyplot global state is used where an explicit `Figure` is safer
- Qt object lifetime: widgets/models kept alive only by a local, signals connected
  repeatedly on reload, dangling references after tab close
- Subprocess launching in `apps/common.py` and `apps/hub.py`: argument quoting, absolute
  vs `sys.executable`, orphaned children, error surfacing to the user
- Config editor round-tripping: does loading and re-saving `tracking_config.yaml`
  preserve every key, including ones the editor doesn't display? Silent key loss would
  destroy user configs
- `script_editor/runner.py` and `actions.py`: how are saved recipes executed, and can a
  recipe file cause arbitrary code execution or unbounded failure?
- Error paths: exceptions during an analysis run — does the user see a real message or a
  frozen window?

**4. Enhancements worth proposing**
- Test suite: propose a concrete starting point — which 5–10 pure functions in the
  analysis core carry the most scientific risk and would be cheapest to pin with unit
  tests using small synthetic DataFrames. Sketch the fixtures
- Input validation at config-load time so a malformed `tracking_config.yaml` fails
  loudly with a specific message rather than producing empty plots
- Logging: is `logging` used consistently, or are there `print()` calls in library code?
- Type hints and dataclass usage where dicts-of-strings are passed around
- Performance: per-row Python loops or `.iterrows()`/`.apply()` over frame-level data
  that should be vectorized; repeated re-reads of the same CSV; missing caching of
  expensive per-arena computations

**5. Refactoring opportunities**
- `Arena.py` (1699) and `Experiment.py` (1510) and `apps/hub.py` (1666) are the three
  giants. For each, propose a concrete decomposition — name the seams (e.g. plotting vs
  computation vs file I/O), what moves where, and what the import graph becomes. Do not
  propose a vague "split this up"
- Repeated boilerplate: rig-preset methods, near-identical plotting functions that differ
  only in column name or title, facet vs non-facet variants that could share a core
- Hardcoded paths (`./Data/`, output directories) that should derive from config
- The `_facet` / non-facet method pairs throughout `Arena` and `Experiment` — is there a
  parameterization that collapses them without breaking the public API?
- Public API surface: what do notebooks actually call? Anything not in that set is free
  to move; anything in it needs a deprecation path

## Method

1. Start by reading `doc/guide.md` and `tracking_config.yaml` to understand intended
   behavior, then read the analysis core in dependency order: `Parameters` →
   `ExperimentalDesign` → `Tracker`/`Counter` → subclasses → `Arena` → `Experiment`.
2. Read every file end to end. For the three giant files, read them in sections but cover
   all of them.
3. Cross-check the UI layer against the core API it calls — a mismatch in argument names
   or expected return types is a real crash even though neither file is wrong alone.
4. Where a data-flow question can be settled empirically, settle it: inspect the sample
   data under `Testing/` to confirm real column names, dtypes, and sentinel values rather
   than assuming.
5. **Verify before reporting.** For each candidate bug, construct the specific input or
   state that triggers it and state the resulting wrong behavior. If you cannot construct
   one, either mark it explicitly as unverified/speculative or drop it. I would rather
   have 12 confirmed findings than 40 plausible ones.

## Output format

Write the report to `CODE_ANALYSIS.md` in the repo root, structured as:

1. **Summary** — 5–10 sentences: overall health, the single most important thing to fix,
   and whether the codebase is in a state where a scientist could trust its numbers.
2. **Critical bugs** — anything that crashes or silently produces wrong scientific
   results. For each: file and line as `path/to/file.py:123`, severity, confidence
   (high/medium/low), the triggering condition, the incorrect behavior, and a concrete
   suggested fix with a code snippet.
3. **Correctness risks** — same format, for things that are wrong under conditions you
   could not fully confirm.
4. **UI and robustness issues** — same format.
5. **Enhancements** — grouped, each with a rationale tied to a real cost the current code
   imposes.
6. **Refactoring plan** — ordered by value-to-effort ratio, each item naming the specific
   files, the proposed structure, and the risk of the change.
7. **Testing recommendation** — the concrete first test suite, with fixture sketches.
8. **Appendix: files reviewed** — every file with a one-line note, so I can see coverage
   and spot anything you skipped.

Rank everything by severity × confidence, not by file order. Be direct about
uncertainty — say "I could not verify this" rather than hedging with vague language. Do
not modify any source file; this is a read-and-report task only.
