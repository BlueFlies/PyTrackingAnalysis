"""Experiment Directory layout: what a run can use, and filing what it cannot (ADR-0011).

An Experiment Directory is loadable when its DTrack export sits in ``data/``.
Recordings do not arrive that way — they arrive as loose files someone has to
move — so a directory can be perfectly well-intentioned and still unusable.
This module names those states and repairs the one that is repairable:

* :func:`classify` — what a directory is, and why a run cannot use it.
* :func:`plan_filing` / :func:`file_recording` — move an **Unfiled Recording**
  into ``data/``, everything else loose into ``extra_files/``, and never a
  ``.yaml``: at an experiment root YAML is configuration or declaration, never
  data. ``tracking_config.yaml`` moved is an Experiment Directory un-made, and
  ``removed_regions.yaml`` moved silently returns removed flies to the
  analysis (ADR-0010).

"Loadable" is decided with the loader's own test — the same ``glob('*.xlsx')``
and the same ``~$``/dot filter :class:`Experiment` uses — rather than a
lookalike. A classifier that says "healthy" where the loader says "no .xlsx
file found" is worse than no classifier: it moves the failure from the
preflight, where someone is looking, into hour three of an unattended run.

Nothing here overwrites and nothing here guesses: a destination that already
exists is skipped, and an ambiguous directory (two workbooks, so "which one is
the experiment?") refuses to file at all. ``Experiment`` picks the first of
several ``data/*.xlsx`` with only a log line, so a one-click fix that can
silently change which recording an analysis is of is worse than a directory
that stays blocked.
"""

from __future__ import annotations

import glob
import os
import shutil
from dataclasses import dataclass, field

from .project import CONFIG_FILENAME

#: Where a recording belongs, and where everything else loose is parked.
DATA_DIRNAME = "data"
EXTRA_DIRNAME = "extra_files"

#: The recording itself: ``<name>.xlsx`` plus its ``<name>_Data_*.csv``
#: companions — exactly what ``Arena`` loads out of ``data/``.
RECORDING_SUFFIXES = (".xlsx", ".csv")

#: Never moved. At an experiment root a YAML file is the design spec or a
#: declaration sidecar; both are read from the root by definition.
KEEP_SUFFIXES = (".yaml", ".yml")

#: Excel writes ``~$Book.xlsx`` beside an open workbook. It is not a recording,
#: and its presence means someone has that workbook open right now.
_IGNORED_PREFIXES = ("~$", ".")

#: Subdirectories of a Project that are never replicates. Without this a
#: Project's own ``data/`` (one that also holds a recording, or a stray copy)
#: reads as an Unfiled Recording, and filing it would nest ``data/data/``.
_NOT_REPLICATES = {DATA_DIRNAME, EXTRA_DIRNAME, "analysis", "qc", "figures",
                   "__pycache__"}

# Status values. The empty string is "not experiment-shaped at all", which is
# not a problem to report — most subdirectories of anything are not.
NOT_AN_EXPERIMENT = ""
OK = "ok"
UNFILED = "unfiled recording"
NO_CONFIG = "no config"
NO_RECORDING = "no recording"
AMBIGUOUS = "ambiguous"
UNREADABLE = "unreadable"

#: Which action clears each status. ``None`` means no button can fix it.
_FIX = {UNFILED: "file", NO_CONFIG: "config"}


@dataclass(frozen=True)
class ExperimentLayout:
    """What one directory is, from its layout alone — no config parsing."""

    directory: str
    name: str
    status: str
    detail: str = ""
    #: Loose recording files that filing would move into ``data/``.
    loose: tuple[str, ...] = ()
    #: Whether ``tracking_config.yaml`` is present — the Project's own
    #: membership test, which is not the same question as "can it run".
    configured: bool = False

    @property
    def blocked(self) -> bool:
        """A run cannot use this directory as it stands."""
        return self.status not in (OK, NOT_AN_EXPERIMENT)

    @property
    def usable(self) -> bool:
        return self.status == OK

    @property
    def fix(self) -> str | None:
        """``"file"``, ``"config"``, or None when nothing can repair it."""
        return _FIX.get(self.status)

    def describe(self) -> str:
        return f"{self.name}: {self.status}" + (f" — {self.detail}" if self.detail else "")


def _entries(directory) -> list[str]:
    try:
        return sorted(os.listdir(directory))
    except OSError:
        return []


def _readable(directory) -> bool:
    try:
        os.listdir(directory)
    except OSError:
        return False
    return True


def data_dir(directory) -> str:
    """The directory's ``data/`` folder, matched the way the loader matches it.

    ``Experiment._find_subdir`` takes the first case-insensitive match in
    ``os.listdir`` order; matching exactly here would call a ``Data/``
    replicate unfiled and then file a *second* ``data/`` beside it. Where both
    spellings exist the loader's own order wins, so the classifier and the
    loader cannot end up reading different directories.
    """
    try:
        entries = os.listdir(directory)
    except OSError:
        return os.path.join(str(directory), DATA_DIRNAME)
    for entry in entries:                        # loader order, not sorted
        if entry.lower() == DATA_DIRNAME and os.path.isdir(
                os.path.join(str(directory), entry)):
            return os.path.join(str(directory), entry)
    return os.path.join(str(directory), DATA_DIRNAME)


def _loadable_workbooks(directory) -> list[str]:
    """Workbooks the loader would actually find in *directory*.

    ``glob.escape`` because a ``[`` anywhere in the path turns the pattern
    into a character class and silently matches nothing — and lab folders are
    full of ``Trial [2].xlsx``.
    """
    pattern = os.path.join(glob.escape(str(directory)), "*.xlsx")
    return sorted(
        os.path.basename(path) for path in glob.glob(pattern)
        ## isfile: glob matches a DIRECTORY named Trial.xlsx too, and that
        ## counted as the filed recording. _is_sidecar: a Removal Sheet saved
        ## as removed_regions.xlsx is a declaration, not a workbook — counting
        ## it made a healthy experiment read "ambiguous".
        if os.path.isfile(path)
        and not os.path.basename(path).startswith(_IGNORED_PREFIXES)
        and not _is_sidecar(os.path.basename(path)))


def _workbook_lookalikes(directory) -> list[str]:
    """Files that read as workbooks to a human but not to the loader's glob —
    ``Trial.XLSX`` on a case-sensitive filesystem."""
    loadable = set(_loadable_workbooks(directory))
    return [name for name in _entries(directory)
            if name.lower().endswith(".xlsx")
            and not name.startswith(_IGNORED_PREFIXES)
            and name not in loadable
            and os.path.isfile(os.path.join(str(directory), name))]


def _lock_files(directory) -> list[str]:
    return [name for name in _entries(directory) if name.startswith("~$")]


def workbooks(directory) -> list[str]:
    """Loadable ``.xlsx`` names directly in *directory*."""
    return _loadable_workbooks(directory)


def has_config(directory) -> bool:
    """``tracking_config.yaml`` at the root — the Experiment membership test.

    Deliberately the same exact-case test as :func:`project.is_experiment_dir`:
    a directory this says has no config is one the Project genuinely cannot
    see, which is what makes "scaffold a config" the right offer.
    """
    return os.path.isfile(os.path.join(str(directory), CONFIG_FILENAME))


def _loose_recording_files(directory) -> tuple[str, ...]:
    return tuple(
        name for name in _entries(directory)
        if name.lower().endswith(RECORDING_SUFFIXES)
        and not name.startswith(_IGNORED_PREFIXES)
        and not _is_sidecar(name)
        and os.path.isfile(os.path.join(str(directory), name)))


def _is_sidecar(name: str) -> bool:
    """A Removal Sheet at an experiment root is a declaration, not data.

    ``removed_regions.csv`` matches the recording allowlist by extension, so
    without this filing would sweep the sheet into ``data/`` and disarm it —
    the ADR-0010 failure the YAML exemption exists to prevent, reached through
    the one extension the allowlist actively moves.
    """
    from .removals import SHEET_STEM

    stem, _dot, _suffix = name.lower().partition(".")
    return stem == SHEET_STEM.lower()


def classify(directory) -> ExperimentLayout:
    """What *directory* is: healthy replicate, Blocked Experiment, or neither.

    Layout only — no YAML is parsed and no data is read, so this stays cheap
    enough to run over every subdirectory of every Project in a Batch.
    """
    directory = str(directory)
    name = os.path.basename(os.path.normpath(directory))
    if not os.path.isdir(directory):
        return ExperimentLayout(directory, name, NOT_AN_EXPERIMENT)
    if not _readable(directory):
        ## Unknown is not the same as absent: a directory nobody can list may
        ## hold a replicate, and silently dropping it would overstate the
        ## Member's coverage in both the preflight and the run summary.
        return ExperimentLayout(directory, name, UNREADABLE,
                                "cannot be listed (permissions?)")

    configured = has_config(directory)
    data = data_dir(directory)
    filed = _loadable_workbooks(data)
    loose_books = _loadable_workbooks(directory)

    def _blocked(status, detail, loose=()):
        return ExperimentLayout(directory, name, status, detail, loose,
                                configured)

    if os.path.exists(data) and not os.path.isdir(data):
        return _blocked(AMBIGUOUS,
                        f"{DATA_DIRNAME} is a file, not a directory")

    if len(filed) > 1:
        ## Experiment logs "Multiple .xlsx files; using X" and carries on, so
        ## this would otherwise decide which recording the analysis is of.
        return _blocked(AMBIGUOUS,
                        f"{len(filed)} workbooks in {DATA_DIRNAME}/ "
                        f"({', '.join(filed[:3])}) — which is the experiment?")
    if filed and loose_books:
        return _blocked(AMBIGUOUS,
                        f"{loose_books[0]} at the root and {filed[0]} already "
                        f"in {DATA_DIRNAME}/ — which is the experiment?")
    if len(loose_books) > 1:
        return _blocked(AMBIGUOUS,
                        f"{len(loose_books)} workbooks at the root "
                        f"({', '.join(loose_books[:3])}) — which is the "
                        "experiment?")

    if filed:
        if configured:
            return ExperimentLayout(directory, name, OK, configured=True)
        return _blocked(NO_CONFIG, f"holds {filed[0]} but no {CONFIG_FILENAME}")

    if loose_books:
        detail = f"{loose_books[0]} sits at the root, not in {DATA_DIRNAME}/"
        if not configured:
            detail += f"; no {CONFIG_FILENAME} either"
        return _blocked(UNFILED, detail, _loose_recording_files(directory))

    ## No workbook the loader would find. A lookalike is worth saying out
    ## loud: "no .xlsx here" is baffling when one is plainly visible.
    lookalikes = _workbook_lookalikes(data) or _workbook_lookalikes(directory)
    if lookalikes and configured:
        return _blocked(
            NO_RECORDING,
            f"{lookalikes[0]} is not loadable — the loader looks for a "
            "lower-case .xlsx extension")

    if configured:
        return _blocked(NO_RECORDING,
                        f"{CONFIG_FILENAME} but no .xlsx in {DATA_DIRNAME}/")
    return ExperimentLayout(directory, name, NOT_AN_EXPERIMENT)


def experiments_in(project_dir) -> list[ExperimentLayout]:
    """Classify every immediate subdirectory of *project_dir* that could be a
    replicate, in name order.

    Symlinked directories are followed here — :attr:`Project.experiment_names`
    counts them, so refusing to would make a Project of symlinked replicates
    look empty — while the Batch walk never follows one. Output directories
    (``data/``, ``analysis/``, ``qc/``, ``figures/``) are excluded by name:
    they are the one thing that is reliably not a replicate, and a Project
    root that is also an Experiment Directory would otherwise have its own
    ``data/`` listed as an unfiled replicate.
    """
    found = []
    #: Real paths already taken: a symlinked copy of a replicate must not be
    #: counted (and analyzed, and pooled) twice — the same rule the Batch walk
    #: enforces one level up, and the one Project.__init__ now applies.
    seen: set[str] = set()
    for name in _entries(project_dir):
        if name.startswith("."):
            continue
        path = os.path.join(str(project_dir), name)
        if not os.path.isdir(path):
            continue
        ## Output directories are excluded by name — but only while they have
        ## no config of their own. A replicate someone named "data" is a
        ## replicate: Project.experiment_names counts it, and discovery
        ## disagreeing with the Project about its own membership is worse than
        ## the odd name.
        if name.lower() in _NOT_REPLICATES and not has_config(path):
            continue
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        item = classify(path)
        if item.status != NOT_AN_EXPERIMENT:
            found.append(item)
    return found


def initializable_dirs(project_dir) -> list[ExperimentLayout]:
    """Immediate subdirectories of *project_dir* that have no config yet.

    The candidates for "initialize this existing directory as a replicate":
    :func:`experiments_in` answers "what is already experiment-shaped", which
    is a narrower question — a folder someone made and dropped loose files
    into (or has not filled yet) is exactly the one that needs initializing,
    and it must not be invisible because it is not experiment-shaped *yet*.

    Output directories are excluded by name, as there; a directory that
    already has a ``tracking_config.yaml`` is a replicate and has nothing to
    initialize.
    """
    found = []
    seen = set()
    for name in _entries(project_dir):
        path = os.path.join(str(project_dir), name)
        if not os.path.isdir(path):
            continue
        if name.lower() in _NOT_REPLICATES:
            continue
        if has_config(path):
            continue
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        found.append(classify(path))
    return found


# ---------------------------------------------------------------------------
# Filing an Unfiled Recording
# ---------------------------------------------------------------------------


@dataclass
class FilingPlan:
    """What filing *would* do — computed before anything moves, so the same
    plan can be shown to the user and then executed."""

    directory: str
    moves: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    refused: str = ""

    @property
    def possible(self) -> bool:
        return not self.refused and bool(self.moves)

    def describe(self) -> str:
        if self.refused:
            return f"cannot file: {self.refused}"
        if not self.moves:
            return "nothing to file"
        into_data = sum(1 for _s, d in self.moves
                        if os.path.basename(os.path.dirname(d)).lower() == DATA_DIRNAME)
        parts = [f"{into_data} file(s) → {DATA_DIRNAME}/"]
        extra = len(self.moves) - into_data
        if extra:
            parts.append(f"{extra} → {EXTRA_DIRNAME}/")
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped")
        return ", ".join(parts)


def _target_problem(directory, target) -> str:
    """Why *target* cannot receive files, or ``""``."""
    name = os.path.basename(target)
    if os.path.exists(target) and not os.path.isdir(target):
        return f"{name} exists as a file, not a directory"
    if os.path.islink(target):
        ## Following it would move the recording out of the Project tree, and
        ## two replicates pointing at one target would contaminate each other.
        return f"{name} is a symlink"
    if not os.access(directory, os.W_OK):
        return "the experiment directory is not writable"
    return ""


def plan_filing(directory) -> FilingPlan:
    """Plan the moves that would make *directory* loadable.

    ``.xlsx``/``.csv`` go to ``data/``; every other loose file goes to
    ``extra_files/``; ``.yaml``/``.yml``, a Removal Sheet, hidden files, Excel
    lock files, symlinks, and every subdirectory stay exactly where they are. A
    destination that already exists is never overwritten — it is skipped and
    reported.
    """
    directory = str(directory)
    plan = FilingPlan(directory)
    item = classify(directory)
    if item.status != UNFILED:
        plan.refused = ("already filed" if item.status == OK else
                        item.detail or item.status or "not an experiment")
        return plan

    data = data_dir(directory)
    extra = os.path.join(directory, EXTRA_DIRNAME)
    problem = _target_problem(directory, data)
    if problem:
        plan.refused = problem
        return plan

    linked = [name for name in _loose_recording_files(directory)
              if os.path.islink(os.path.join(directory, name))]
    if linked:
        ## Filing the .csv companions while refusing the symlinked workbook
        ## would leave the directory in a worse state than it started.
        plan.refused = (f"{linked[0]} is a symlink — file this experiment by "
                        "hand")
        return plan

    locks = _lock_files(directory)
    if locks:
        ## The workbook is open in Excel right now. Windows would fail the
        ## move; every other platform would succeed and confuse the editor.
        plan.refused = (f"{locks[0]} — the workbook is open; close it first")
        return plan

    for name in _entries(directory):
        source = os.path.join(directory, name)
        if not os.path.isfile(source):
            continue
        lower = name.lower()
        if os.path.islink(source):
            plan.skipped.append((name, "symlink — left where it is"))
            continue
        if name.startswith(_IGNORED_PREFIXES):
            continue
        if lower.endswith(KEEP_SUFFIXES) or _is_sidecar(name):
            continue
        recording = lower.endswith(RECORDING_SUFFIXES)
        if not recording:
            ## Checked lazily: a stray file named extra_files/ must not refuse
            ## a filing whose only job is moving the recording.
            problem = _target_problem(directory, extra)
            if problem:
                plan.skipped.append((name, problem))
                continue
        target = data if recording else extra
        destination = os.path.join(target, name)
        if os.path.exists(destination):
            plan.skipped.append(
                (name, f"{os.path.basename(target)}/{name} already exists"))
            continue
        plan.moves.append((source, destination))

    if not plan.moves and not plan.refused:
        plan.refused = "nothing here can be moved"
    return plan


def file_recording(directory, log=None) -> FilingPlan:
    """Execute :func:`plan_filing` for *directory*; returns the plan as run.

    Moves are attempted one at a time and a failure is recorded against that
    file rather than raised: a half-filed directory that says which half is
    recoverable, and one unwritable file must not strand the rest. A move that
    leaves the source behind (a cross-filesystem copy that failed partway) is
    reported as such rather than counted as done — that state reads as
    "ambiguous" afterwards, and silently converting a one-click fix into a
    permanent block is the worst outcome available.
    """
    plan = plan_filing(directory)
    if not plan.possible:
        if log and plan.refused:
            log(f"[file] {os.path.basename(str(directory))}: {plan.refused}")
        return plan

    done: list[tuple[str, str]] = []
    for source, destination in plan.moves:
        parent = os.path.dirname(destination)
        name = os.path.basename(source)
        try:
            os.makedirs(parent, exist_ok=True)
            ## Re-check under the directory we just made: between planning and
            ## here, the destination may have appeared.
            if os.path.exists(destination):
                plan.skipped.append((name, "already exists — not overwritten"))
                continue
            shutil.move(source, destination)
        except OSError as err:
            plan.skipped.append((name, str(err)))
            continue
        if os.path.exists(source):
            plan.skipped.append(
                (name, "copied but the original is still here — move it by "
                       "hand before running"))
            continue
        done.append((source, destination))
        if log:
            log(f"[file] {name} → {os.path.basename(parent)}/")
    if not done and plan.skipped:
        ## Otherwise describe() reports "nothing to file" for a directory
        ## where every single move was refused by the filesystem.
        plan.refused = f"nothing could be moved ({plan.skipped[0][1]})"
    plan.moves = done
    return plan
