"""The Batch level (ADR-0009): many sibling Projects run unattended.

A Batch is structural — a directory whose immediate subdirectories holding a
``project.yaml`` are its Projects. Nothing marks one: ``batch.yaml`` at its
root appears only once batch-level scripting is authored, because unlike a
Project a Batch has no authority to declare. A Batch Run executes one
designated Project Script in every Project (continue-on-error, per-Project
log prefixes) and its only product is the per-Project run summary — a Batch
never pools results across Projects.

There is no third script level: the thing a Batch Run runs IS a Project
Script, resolved per Project as batch.yaml ``project_scripts:`` → the
Project's own ``scripts:`` → the built-ins (Report Pipeline, Standard
Pipeline). With no designation at all each Project runs its OWN default
script — every ``project.yaml`` is created with one, so nothing is
silently substituted for a Project that has none.
"""

from __future__ import annotations

import os

import yaml

from . import project as prj

#: The lazy Batch file: the ``script:`` designation plus centrally-held
#: Project Scripts (the ``experiment_scripts:`` idea one level up).
BATCH_FILENAME = "batch.yaml"


def batch_project_names(path) -> list[str]:
    """Immediate subdirectories of *path* that are Projects, sorted by name —
    the order a Batch Run visits them in."""
    root = str(path)
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return []
    return [entry for entry in entries
            if os.path.isdir(os.path.join(root, entry))
            and prj.is_project_dir(os.path.join(root, entry))]


def is_batch_dir(path) -> bool:
    """A Batch is structural: at least one immediate subdirectory is a
    Project. A Project is never also a Batch — its subdirectories are its
    Experiments, so a nested ``project.yaml`` does not turn it into one."""
    if prj.is_project_dir(path):
        return False
    return bool(batch_project_names(path))


def load_batch_file(path) -> dict:
    """The parsed ``batch.yaml`` of Batch *path* as
    ``{"script": str | None, "project_scripts": list[dict]}``.

    Lenient like ``Project.__init__``'s scripts parse: a missing file, a
    malformed document, or a bad block yields empty sections rather than an
    exception — one bad block must not take down a whole Batch Run.
    """
    result: dict = {"script": None, "project_scripts": []}
    file_path = os.path.join(str(path), BATCH_FILENAME)
    if not os.path.isfile(file_path):
        return result
    try:
        with open(file_path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:  # noqa: BLE001
        return result
    if not isinstance(data, dict):
        return result
    name = data.get("script")
    if isinstance(name, str) and name.strip():
        result["script"] = name.strip()
    raw = data.get("project_scripts") or []
    if isinstance(raw, list):
        result["project_scripts"] = [
            dict(item) for item in raw
            if isinstance(item, dict) and item.get("name")]
    return result


def save_batch_designation(path, script_name: str | None) -> None:
    """Persist the designated Project Script name in ``batch.yaml``.

    The lazy-marker rule: ``None`` (the shipped default, the Report
    Pipeline) never CREATES the file — it only clears the ``script:`` key of
    an existing one. Unknown keys are preserved; the write is atomic.
    """
    from .io_utils import atomic_write_text

    file_path = os.path.join(str(path), BATCH_FILENAME)
    exists = os.path.isfile(file_path)
    if script_name is None and not exists:
        return
    payload: dict = {}
    if exists:
        try:
            with open(file_path, encoding="utf-8") as handle:
                payload = yaml.safe_load(handle) or {}
        except Exception:  # noqa: BLE001
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
    if script_name is None:
        payload.pop("script", None)
    else:
        payload["script"] = script_name
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    atomic_write_text(file_path, lambda f: f.write(text))


def resolve_designated_script(name: str | None, central_scripts: list[dict],
                              project) -> tuple[dict | None, str, str | None]:
    """Resolve the designated Project Script *name* for *project*.

    Order (ADR-0009): the Batch's central ``project_scripts:``, then the
    Project's own ``scripts:``, then the built-ins. Returns
    ``(script, source, note)`` where *note* explains a conditionally dropped
    step; ``(None, "", None)`` when the name resolves nowhere.

    ``None`` means "no designation": each Project runs its OWN default
    script (ADR-0009 amendment). Every ``project.yaml`` is created with one,
    so there is no built-in fallback here — a Project whose ``scripts:`` is
    empty does not run, and says so.
    """
    from .script_editor.project_actions import (
        DEFAULT_PROJECT_SCRIPT_NAME,
        REPORT_PIPELINE,
        STANDARD_PIPELINE,
        report_pipeline_for,
    )

    if not name:
        ## The seeded default by name, else the first authored script — a
        ## Project whose default was renamed still runs its own pipeline.
        own = project.find_script(DEFAULT_PROJECT_SCRIPT_NAME)
        if own is None:
            own = project.scripts[0] if project.scripts else None
        if own is None:
            return None, "", None
        return own, "project.yaml scripts", None
    for script in central_scripts:
        if str(script.get("name", "")).strip() == name:
            return script, "batch.yaml project_scripts", None
    own = project.find_script(name)
    if own is not None:
        return own, "project.yaml scripts", None
    if name == REPORT_PIPELINE["name"]:
        script, note = report_pipeline_for(project)
        return script, "built-in", note
    if name == STANDARD_PIPELINE["name"]:
        return STANDARD_PIPELINE, "built-in", None
    return None, "", None


def run_batch(batch_dir, script_name: str | None = None,
              project_names: list[str] | None = None,
              log=print) -> dict:
    """One Batch Run: the designated Project Script in every Project of
    *batch_dir* — continue-on-error, per-Project log prefixes.

    Returns ``{project_name: 'ok' | error message}``. A Batch Run never
    creates or upgrades a ``project.yaml``; children that are not Projects
    are skipped with a log line. *script_name* ``None`` falls back to the
    ``batch.yaml`` designation, and with no designation each Project runs
    its own default script. *project_names* restricts the run to that
    (checked) subset.
    """
    from .script_editor.project_actions import run_project_script

    root = os.path.abspath(str(batch_dir))
    meta = load_batch_file(root)
    if script_name is None:
        script_name = meta["script"]

    all_projects = batch_project_names(root)
    project_set = set(all_projects)
    try:
        children = sorted(os.listdir(root))
    except OSError:
        children = []
    for entry in children:
        if os.path.isdir(os.path.join(root, entry)) \
                and entry not in project_set:
            log(f"[{entry}] skipped — not a Project "
                f"(no {prj.PROJECT_FILENAME})")

    if project_names is None:
        targets = all_projects
    else:
        wanted = set(project_names)
        targets = [n for n in all_projects if n in wanted]
        for missing in sorted(wanted - set(all_projects)):
            ## An API caller's stale name must not vanish silently — the Hub
            ## table only offers real Projects, so this is for scripts.
            log(f"[{missing}] not a Project in this Batch — ignored")

    results: dict[str, str] = {}
    if not targets:
        log(f"No Projects to run in {root}")
        return results

    log(f"Batch Run: {len(targets)} Project(s) in {root}")
    for i, name in enumerate(targets, 1):
        project_dir = os.path.join(root, name)

        def plog(msg, _n=name):
            log(f"[{_n}] {msg}")

        log(f"[{i}/{len(targets)}] {name}")
        try:
            project = prj.Project(project_dir)
        except Exception as err:  # noqa: BLE001
            ## A raising constructor (design mismatch, empty designless
            ## Project) is that Project's failure, never the run's.
            results[name] = f"{type(err).__name__}: {err}"
            plog(f"FAILED to load: {err}")
            continue
        script, source, note = resolve_designated_script(
            script_name, meta["project_scripts"], project)
        if script is None:
            results[name] = (
                f"no Project Script named '{script_name}' (batch.yaml "
                f"project_scripts, project.yaml scripts, or built-ins)"
                if script_name else
                "project.yaml defines no Project Script — add one in the "
                "Script Editor (new Projects are created with a default "
                "one)")
            plog(f"SKIPPED — {results[name]}")
            continue
        if note:
            plog(note)
        plog(f"running '{script.get('name')}' (from {source})…")
        try:
            run_project_script(script, project, log_cb=plog)
            results[name] = "ok"
        except Exception as err:  # noqa: BLE001
            ## str() of a bare exception can be empty — keep the type name so
            ## the summary always has something to say.
            results[name] = str(err) or type(err).__name__
            plog(f"FAILED: {results[name]}")

    ok = sum(1 for v in results.values() if v == "ok")
    log(f"Batch Run complete: {ok}/{len(targets)} Project(s) succeeded.")
    if ok < len(targets):
        log("Failed:")
        for name, msg in results.items():
            if msg != "ok":
                headline = msg.splitlines()[0] if msg else "<no message>"
                log(f"  {name}: {headline}")
    return results
