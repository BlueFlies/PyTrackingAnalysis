"""Execute a saved script against an Experiment.

Called from the Hub's Scripts card.  Each step is dispatched through the
action registry in :mod:`.actions`.  Validation errors are raised before
any side-effects; runtime errors propagate up so the Hub's worker can
surface them in the OutputLog.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .actions import ACTIONS, RunContext, validation_issues


class ScriptError(RuntimeError):
    """Raised when a script cannot execute (unknown action or bad params)."""


def run_script(
    script: dict,
    *,
    project_dir: str | Path,
    log_cb: Callable[[str], None],
    figure_cb: Callable[[str, Any], None],
    exp: Any = None,
) -> RunContext:
    """Execute *script* and return the updated :class:`RunContext`.

    Parameters
    ----------
    script
        ``{"name": str, "steps": [{"action": str, "params": {...}}, ...]}``.
    project_dir
        Default location for ``load_experiment`` steps that use ``path: "."``.
    log_cb, figure_cb
        Callbacks for text output and matplotlib figures, typically
        ``OutputLog.append_line`` and ``PlotDock.add_figure``.
    exp
        Optional pre-loaded Experiment (avoids re-reading data when the
        script doesn't start with ``load_experiment``).
    """
    steps = script.get("steps", [])
    if not steps:
        raise ScriptError("Script has no steps")

    # Pre-flight validation against the currently-loaded experiment type if any.
    exp_type = None
    if exp is not None:
        try:
            exp_type = exp.parameters.get_tracking_type().name
        except Exception:  # noqa: BLE001
            exp_type = None
    issues = validation_issues(steps, experiment_type=exp_type)
    if issues:
        lines = [f"Step {i+1}: {err}" for i, err in issues]
        raise ScriptError("Script validation failed:\n" + "\n".join(lines))

    ctx = RunContext(project_dir=Path(project_dir), exp=exp, log=log_cb, figure=figure_cb)
    for i, step in enumerate(steps):
        key = step.get("action", "")
        action = ACTIONS[key]
        ctx.log(f"── Step {i+1}/{len(steps)}: {action.title}")
        action.execute(step.get("params", {}), ctx)
    ctx.log("✓ Script complete.")
    return ctx


def _sanitise_scripts(raw: Any) -> list[dict]:
    """Validate the shape of a ``scripts:`` block, or raise :class:`ScriptError`.

    A hand-edited, merged or older-version config can carry a ``scripts:``
    block that is a mapping instead of a list, or whose ``steps:`` are bare
    strings instead of ``{action, params}`` mappings.  The widgets downstream
    call ``.setdefault()`` and ``dict()`` on those entries, and because they
    are built inside a Qt slot PyQt6 escalates the resulting ``TypeError`` to
    ``qFatal()`` — the whole application dies.  Fail here instead, naming the
    offending value, so the caller can show a dialog and stay alive.
    """
    if isinstance(raw, dict):
        raise ScriptError(
            "'scripts:' is a mapping but must be a list of {name, steps} entries. "
            f"Found keys: {', '.join(str(k) for k in raw)}"
        )
    if not isinstance(raw, list):
        raise ScriptError(
            f"'scripts:' must be a list of {{name, steps}} entries, not {type(raw).__name__}"
        )

    clean: list[dict] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ScriptError(
                f"'scripts:' entry {i + 1} is not a mapping: {entry!r}. "
                "Each entry needs a 'name:' and a 'steps:' list."
            )
        name = entry.get("name", "Untitled")
        steps_raw = entry.get("steps") or []
        if isinstance(steps_raw, dict) or not isinstance(steps_raw, list):
            raise ScriptError(
                f"script {str(name)!r}: 'steps:' must be a list of "
                f"{{action, params}} mappings, not {type(steps_raw).__name__}"
            )
        steps: list[dict] = []
        for j, step in enumerate(steps_raw):
            if not isinstance(step, dict):
                raise ScriptError(
                    f"script {str(name)!r} step {j + 1} is not a mapping: {step!r}. "
                    "Each step needs an 'action:' key (and optionally 'params:')."
                )
            params = step.get("params") or {}
            if not isinstance(params, dict):
                raise ScriptError(
                    f"script {str(name)!r} step {j + 1}: 'params:' must be a "
                    f"mapping, not {type(params).__name__}"
                )
            steps.append({**step, "params": dict(params)})
        clean.append({**entry, "name": str(name), "steps": steps})
    return clean


def load_scripts(yaml_path: str | Path) -> list[dict]:
    """Return the ``scripts:`` list from a tracking_config.yaml (empty if absent).

    Raises :class:`ScriptError` if the block is present but malformed.
    """
    import yaml

    p = Path(yaml_path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ScriptError(f"{p.name} is not a YAML mapping — cannot read 'scripts:'")
    return _sanitise_scripts(data.get("scripts") or [])


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

# A top-level ``scripts:`` key, i.e. one with no leading indentation.
_SCRIPTS_KEY_RE = re.compile(r"^scripts\s*:")


def _dump_scripts_block(scripts: list[dict]) -> str:
    import yaml

    return yaml.safe_dump(
        {"scripts": scripts}, default_flow_style=False, sort_keys=False,
        allow_unicode=True,
    )


def _splice_scripts_block(text: str, scripts: list[dict]) -> str:
    """Return *text* with only its top-level ``scripts:`` block replaced.

    Rewriting the whole document through ``yaml.safe_dump`` would discard every
    comment in the user's tracking_config.yaml — 45 lines of inline
    documentation in the shipped config — as a side-effect of editing scripts,
    which the user has no reason to expect.  So the block is spliced textually
    and everything around it is left byte-for-byte intact.

    The caller must verify the result round-trips (see :func:`save_scripts`);
    this function makes no attempt to be a general YAML editor.
    """
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if _SCRIPTS_KEY_RE.match(ln)), None
    )

    if start is None:
        block = _dump_scripts_block(scripts) if scripts else ""
        if not block:
            return text
        prefix = text if text.endswith("\n") or not text else text + "\n"
        return prefix + block

    # The block runs until the next line that starts a new top-level construct.
    # PyYAML writes sequence items under a mapping key without indentation, so
    # a leading "-" continues the block; a column-0 comment ends it (comments
    # there belong to whatever follows).
    end = start + 1
    while end < len(lines):
        ln = lines[end]
        if ln.strip() and not (ln[0].isspace() or ln.startswith("-")):
            break
        end += 1
    block_lines = _dump_scripts_block(scripts).splitlines() if scripts else []
    if block_lines:
        # Blank lines at the tail separate this block from the next section;
        # keep them. When the block is being deleted outright they go with it.
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1

    return "\n".join(lines[:start] + block_lines + lines[end:]) + "\n"


def save_scripts(yaml_path: str | Path, scripts: list[dict]) -> None:
    """Overwrite the ``scripts:`` list in a tracking_config.yaml.

    The write is atomic (temp file + ``os.replace``) so an interruption can
    never leave the user with a truncated config, and only the ``scripts:``
    block is touched so surrounding comments survive.  If the surgical splice
    does not reproduce exactly the document we intend, we fall back to a full
    ``yaml.safe_dump`` — correct content beats preserved comments.
    """
    import yaml

    from ..io_utils import atomic_write_text

    p = Path(yaml_path)
    original = p.read_text(encoding="utf-8") if p.exists() else ""
    data = yaml.safe_load(original) if original.strip() else {}
    data = data or {}
    if not isinstance(data, dict):
        raise ScriptError(f"{p.name} is not a YAML mapping — refusing to overwrite it")

    expected = dict(data)
    if scripts:
        expected["scripts"] = scripts
    else:
        expected.pop("scripts", None)

    text = _splice_scripts_block(original, scripts)
    try:
        spliced_ok = (yaml.safe_load(text) or {}) == expected
    except yaml.YAMLError:
        spliced_ok = False
    if not spliced_ok:
        text = yaml.safe_dump(
            expected, default_flow_style=False, sort_keys=False, allow_unicode=True,
        )

    atomic_write_text(p, lambda f: f.write(text))
