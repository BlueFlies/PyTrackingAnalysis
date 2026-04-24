"""Execute a saved script against an Experiment.

Called from the Hub's Scripts card.  Each step is dispatched through the
action registry in :mod:`.actions`.  Validation errors are raised before
any side-effects; runtime errors propagate up so the Hub's worker can
surface them in the OutputLog.
"""

from __future__ import annotations

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


def load_scripts(yaml_path: str | Path) -> list[dict]:
    """Return the ``scripts:`` list from a tracking_config.yaml (empty if absent)."""
    import yaml

    p = Path(yaml_path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("scripts") or []
    return list(raw)


def save_scripts(yaml_path: str | Path, scripts: list[dict]) -> None:
    """Overwrite the ``scripts:`` list in a tracking_config.yaml."""
    import yaml

    p = Path(yaml_path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    if scripts:
        data["scripts"] = scripts
    elif "scripts" in data:
        del data["scripts"]
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
