"""Project-level script actions (ADR-0006).

Project Scripts share the experiment-script language — ``{name,
steps:[{action, params}]}`` in ``project.yaml`` ``scripts:`` — but dispatch
through this separate registry with a :class:`ProjectRunContext`, so levels
cannot mix. The only bridge to experiment level is ``run_in_experiments``,
which runs a named Experiment Script in every replicate (the Project's
central ``experiment_scripts:`` first, each replicate's own
``tracking_config.yaml`` as fallback — which also absorbs the legacy
``batch`` convention), continue-on-error with a failure summary.

Every other action is a thin wrapper over an existing ``Project`` method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..ui import Category
from .actions import Action, ParamSpec


@dataclass
class ProjectRunContext:
    """State threaded through a Project Script run."""

    project: Any = None  # pytrackinganalysis.project.Project
    log: Callable[[str], None] = lambda _msg: None
    figure: Callable[[str, Any], None] = lambda _title, _fig: None
    #: Failures collected by continue-on-error steps; reported at the end.
    failures: list = field(default_factory=list)


class ProjectScriptError(RuntimeError):
    """A Project Script cannot execute (unknown action, bad params, or a
    step's hard failure)."""


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def _exec_validate_design(_params: dict, ctx: ProjectRunContext) -> None:
    """Re-validate every replicate against the design (a fresh load, so a
    config edited since the run started is still caught)."""
    from ..project import Project

    project = Project(ctx.project.project_directory)  # raises on mismatch
    ctx.log(f"Design OK: {len(project.experiment_names)} replicate(s) "
            f"({', '.join(project.experiment_names) or 'none yet'}).")
    for warning in project.warnings:
        ctx.log(f"Note: {warning}")


def _exec_run_in_experiments(params: dict, ctx: ProjectRunContext) -> None:
    """The bridge: run an Experiment Script in every replicate."""
    from .runner import load_scripts, run_script

    project = ctx.project
    name = str(params.get("script", "")).strip()
    script = project.find_experiment_script(name)
    source = "project" if script is not None else None

    ran, failures = 0, []
    for exp_name in project.experiment_names:
        exp_dir = project.experiment_dir(exp_name)
        replicate_script = script
        if replicate_script is None:
            ## Fallback: the replicate's own script of that name — this is
            ## also how a legacy 'batch' parent keeps running unchanged.
            import os
            own = load_scripts(os.path.join(exp_dir, "tracking_config.yaml"))
            replicate_script = next(
                (s for s in own if s.get("name") == name), None)
        if replicate_script is None:
            failures.append(f"{exp_name}: no script named '{name}' "
                            f"(neither in project.yaml experiment_scripts "
                            f"nor in its tracking_config.yaml)")
            ctx.log(f"[{exp_name}] SKIPPED — no script named '{name}'")
            continue
        where = source or "replicate config"
        ctx.log(f"[{exp_name}] running '{name}' (from {where})…")
        try:
            exp = project.load_experiment(exp_name)
            run_script(
                replicate_script, project_dir=exp_dir,
                log_cb=lambda msg, _n=exp_name: ctx.log(f"[{_n}] {msg}"),
                figure_cb=lambda title, fig, _n=exp_name:
                    ctx.figure(f"{_n}: {title}", fig),
                exp=exp,
            )
            ran += 1
        except Exception as err:  # noqa: BLE001
            failures.append(f"{exp_name}: {err}")
            ctx.log(f"[{exp_name}] FAILED: {err}")
    ctx.log(f"run_in_experiments('{name}'): {ran} succeeded, "
            f"{len(failures)} failed.")
    ctx.failures.extend(failures)


def _exec_run_all_analyses(params: dict, ctx: ProjectRunContext) -> None:
    failures = ctx.project.run_all(
        make_reports=bool(params.get("reports", True)),
        skip_analyzed=bool(params.get("skip_analyzed", False)),
        log=ctx.log,
    )
    ctx.failures.extend(failures)


def _exec_build_combined(_params: dict, ctx: ProjectRunContext) -> None:
    result = ctx.project.build_combined_analysis()
    ctx.log(f"Combined analysis written ({len(result['written'])} files).")
    if result["missing"]:
        ctx.log("Not yet analyzed (omitted): "
                + ", ".join(result["missing"]))


def _exec_render_figures(params: dict, ctx: ProjectRunContext) -> None:
    choice = str(params.get("format", "svg"))
    formats = ("svg", "pdf") if choice == "both" else (choice,)
    written = ctx.project.render_figures(formats=formats)
    ctx.log(f"Wrote {len(written)} publication figure file(s) to figures/.")


def _exec_project_report(_params: dict, ctx: ProjectRunContext) -> None:
    path = ctx.project.create_report()
    ctx.log(f"Project report: {path}")


def _exec_ai_narrative(params: dict, ctx: ProjectRunContext) -> None:
    provider = str(params.get("provider", "anthropic"))
    soft = bool(params.get("soft_fail", True))
    try:
        ctx.project.generate_ai_summary(provider)
        ctx.log("AI narrative saved — the next Project report embeds it.")
    except Exception as err:  # noqa: BLE001
        if not soft:
            raise
        ## A provider hiccup must not kill a pipeline (ADR-0006).
        ctx.log(f"AI narrative skipped ({err}).")


def _validate_run_in_experiments(params: dict, _t: str | None) -> list[str]:
    if not str(params.get("script", "")).strip():
        return ["'Experiment script name' is required"]
    return []


def _build_project_actions() -> dict[str, Action]:
    actions = [
        Action(
            key="validate_design",
            title="Validate design",
            description="Re-check every replicate against the project design; "
                        "fails the script on any mismatch.",
            category=Category.TOOLS,
            icon_name="lint",
            params=(),
            execute_fn=_exec_validate_design,
        ),
        Action(
            key="run_in_experiments",
            title="Run in experiments",
            description="Run a named Experiment Script in every replicate — "
                        "the project's experiment_scripts first, each "
                        "replicate's own config as fallback. Continues on "
                        "error; failures are summarized at the end.",
            category=Category.ANALYZE,
            icon_name="batch",
            params=(
                ParamSpec("script", "string", "Experiment script name",
                          default="", help="Name resolved in project.yaml "
                          "experiment_scripts, then in each replicate's "
                          "tracking_config.yaml scripts."),
            ),
            validate_fn=_validate_run_in_experiments,
            execute_fn=_exec_run_in_experiments,
        ),
        Action(
            key="run_all_analyses",
            title="Run all analyses",
            description="Full analysis (and report) for every replicate — "
                        "the Project card's Run-all as a step.",
            category=Category.ANALYZE,
            icon_name="basic",
            params=(
                ParamSpec("reports", "bool", "Create per-replicate reports",
                          default=True),
                ParamSpec("skip_analyzed", "bool", "Skip analyzed replicates",
                          default=False),
            ),
            execute_fn=_exec_run_all_analyses,
        ),
        Action(
            key="build_combined_analysis",
            title="Build combined analysis",
            description="Stack the replicates' filtered summaries into the "
                        "project analysis/ with pooled + mixed statistics.",
            category=Category.ANALYZE,
            icon_name="csv",
            params=(),
            execute_fn=_exec_build_combined,
        ),
        Action(
            key="render_publication_figures",
            title="Render publication figures",
            description="Write the pooled publication figures to figures/ "
                        "from plot_specs.yaml (the Plot Editor's saves, "
                        "headless).",
            category=Category.PLOTS,
            icon_name="plots",
            params=(
                ParamSpec("format", "choice", "Format", default="svg",
                          choices=("svg", "pdf", "both")),
            ),
            execute_fn=_exec_render_figures,
        ),
        Action(
            key="project_report",
            title="Project report",
            description="Build <project>_report.pdf: pooled figures, pooled "
                        "+ mixed statistics, replicate table, and any saved "
                        "AI narrative.",
            category=Category.ANALYZE,
            icon_name="report",
            params=(),
            execute_fn=_exec_project_report,
        ),
        Action(
            key="generate_ai_narrative",
            title="Generate AI narrative",
            description="Ask an AI provider to write the project narrative "
                        "from the Combined Analysis. Soft-fails by default: "
                        "a provider error logs and the script continues.",
            category=Category.AI,
            icon_name="ai",
            params=(
                ParamSpec("provider", "choice", "Provider",
                          default="anthropic",
                          choices=("anthropic", "openai")),
                ParamSpec("soft_fail", "bool", "Continue on provider error",
                          default=True),
            ),
            execute_fn=_exec_ai_narrative,
        ),
    ]
    return {a.key: a for a in actions}


PROJECT_ACTIONS: dict[str, Action] = _build_project_actions()

#: The built-in Project Script (never written to project.yaml, so it always
#: tracks the shipped default). Zero authoring gets a complete run.
STANDARD_PIPELINE: dict = {
    "name": "Standard pipeline",
    "steps": [
        {"action": "validate_design", "params": {}},
        {"action": "run_all_analyses", "params": {}},
        {"action": "build_combined_analysis", "params": {}},
        {"action": "render_publication_figures", "params": {"format": "svg"}},
        {"action": "project_report", "params": {}},
    ],
}


def project_validation_issues(steps: list[dict],
                              experiment_type: str | None = None) -> list[tuple[int, str]]:
    """Per-step validation problems, mirroring ``actions.validation_issues``
    (same signature so the Script Editor can treat both levels uniformly)."""
    del experiment_type  # project actions are type-agnostic
    issues: list[tuple[int, str]] = []
    for i, step in enumerate(steps):
        key = step.get("action", "")
        action = PROJECT_ACTIONS.get(key)
        if action is None:
            issues.append((i, f"Unknown project action '{key}'"))
            continue
        for err in action.validate(step.get("params", {})):
            issues.append((i, err))
    return issues


def run_project_script(script: dict, project,
                       log_cb: Callable[[str], None],
                       figure_cb: Callable[[str, Any], None] = lambda *_: None,
                       ) -> ProjectRunContext:
    """Execute a Project Script and return the context.

    Validation runs before any side-effect. Bridge/replicate failures are
    collected continue-on-error style and raised as one summary at the end,
    so a pipeline finishes its independent work before reporting what broke.
    """
    steps = script.get("steps", [])
    if not steps:
        raise ProjectScriptError("Script has no steps")
    issues = project_validation_issues(steps)
    if issues:
        lines = [f"Step {i + 1}: {err}" for i, err in issues]
        raise ProjectScriptError("Script validation failed:\n"
                                 + "\n".join(lines))

    ctx = ProjectRunContext(project=project, log=log_cb, figure=figure_cb)
    for i, step in enumerate(steps):
        action = PROJECT_ACTIONS[step.get("action", "")]
        ctx.log(f"── Step {i + 1}/{len(steps)}: {action.title}")
        action.execute(step.get("params", {}), ctx)
    if ctx.failures:
        raise ProjectScriptError(
            f"Script finished with {len(ctx.failures)} replicate "
            "failure(s):\n  - " + "\n  - ".join(ctx.failures))
    ctx.log("✓ Project script complete.")
    return ctx
