"""Project-level script actions (ADR-0006).

Project Scripts share the experiment-script language — ``{name,
steps:[{action, params}]}`` in ``project.yaml`` ``scripts:`` — but dispatch
through this separate registry with a :class:`ProjectRunContext`, so levels
cannot mix. The only bridge to experiment level is ``run_in_experiments``,
which runs a named Experiment Script in every replicate — or, with its
optional ``only:`` list of replicate directory names, in just those — (the
Project's central ``experiment_scripts:`` first, each replicate's own
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


def _parse_only(value) -> list[str]:
    """The ``only`` param as a list of replicate names. The inspector saves a
    real list; a hand-edited yaml may hold a comma-separated string. A null
    item (yaml ``~``) is dropped rather than becoming the name "None"."""
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value
                if v is not None and str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _exec_run_in_experiments(params: dict, ctx: ProjectRunContext) -> None:
    """The bridge: run an Experiment Script in every replicate — or, with
    ``only:``, in just the named ones."""
    from .runner import load_scripts, run_script

    project = ctx.project
    name = str(params.get("script", "")).strip()
    script = project.find_experiment_script(name)
    source = "project" if script is not None else None

    ran, failures = 0, []
    targets = list(project.experiment_names)
    only = _parse_only(params.get("only"))
    if only:
        known = set(project.experiment_names)
        for missing in [n for n in only if n not in known]:
            ## A targeted name that matches nothing is loud, never silent
            ## (grill 2026-08): recorded and summarized, run continues.
            failures.append(f"{missing}: no replicate of that name")
            ctx.log(f"[{missing}] SKIPPED — no replicate of that name")
        wanted = set(only)
        targets = [n for n in project.experiment_names if n in wanted]
    for exp_name in targets:
        exp_dir = project.experiment_dir(exp_name)
        replicate_script = script
        if replicate_script is None:
            ## Fallback: the replicate's own script of that name — this is
            ## also how a legacy 'batch' parent keeps running unchanged. A
            ## malformed config is that replicate's failure, never the
            ## step's (continue-on-error).
            import os
            try:
                own = load_scripts(
                    os.path.join(exp_dir, "tracking_config.yaml"))
            except Exception as err:  # noqa: BLE001
                failures.append(f"{exp_name}: unreadable scripts — {err}")
                ctx.log(f"[{exp_name}] FAILED to read scripts: {err}")
                continue
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
    errs: list[str] = []
    if not str(params.get("script", "")).strip():
        errs.append("'Experiment script name' is required")
    only = params.get("only", "")
    if only not in ("", None) and not isinstance(only, (list, tuple, str)):
        errs.append("'Only replicates' must be replicate names "
                    "(a list, or comma-separated)")
    return errs


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
                        "or only the ones named below — the project's "
                        "experiment_scripts first, each replicate's own "
                        "config as fallback. Continues on error; failures "
                        "are summarized at the end.",
            category=Category.ANALYZE,
            icon_name="batch",
            params=(
                ParamSpec("script", "string", "Experiment script name",
                          default="", help="Name resolved in project.yaml "
                          "experiment_scripts, then in each replicate's "
                          "tracking_config.yaml scripts."),
                ParamSpec("only", "multilist", "Only replicates",
                          default="", help="Optional replicate directory "
                          "names; blank = every replicate. A name matching "
                          "no replicate is reported in the failure summary "
                          "and the run continues."),
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

#: The report-button sequence as a built-in (ADR-0009) — the default Batch
#: designation. No validate_design gate (it would fail Projects
#: mid-migration), and the publication-figure step runs only from curated
#: specs: :func:`report_pipeline_for` applies that condition per Project, so
#: the conditionality never appears in yaml.
REPORT_PIPELINE: dict = {
    "name": "Report pipeline",
    "steps": [
        {"action": "run_all_analyses", "params": {}},
        {"action": "build_combined_analysis", "params": {}},
        {"action": "render_publication_figures", "params": {"format": "svg"}},
        {"action": "project_report", "params": {}},
    ],
}


def report_pipeline_for(project) -> tuple[dict, str | None]:
    """The Report Pipeline as it will actually run on *project*.

    The publication-figure step is dropped when the Project has no
    ``plot_specs.yaml`` — nobody curated figures, and an unattended run must
    not invent default-spec ones. Returns ``(script, note)``; *note* explains
    a dropped step, or is None.
    """
    import os

    from ..pubfigures import SPECS_FILENAME

    specs = os.path.join(str(project.project_directory), SPECS_FILENAME)
    if os.path.isfile(specs):
        return REPORT_PIPELINE, None
    steps = [dict(s) for s in REPORT_PIPELINE["steps"]
             if s.get("action") != "render_publication_figures"]
    return ({"name": REPORT_PIPELINE["name"], "steps": steps},
            f"no {SPECS_FILENAME} — publication-figure step skipped")


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


def preflight_project_script_issues(script: dict, project) -> list[str]:
    """Project-in-hand checks the static validator cannot do, run by the Hub
    before spawning a script so a typo never reaches a run (grill 2026-08):
    unknown ``only:`` replicate names, and an experiment-script name that
    resolves nowhere it is asked to run.

    For a targeted step every named replicate must resolve the script
    (centrally or in its own config); for a broadcast step only a name that
    resolves *nowhere at all* is an issue — a partial spread is normal
    fallback territory and stays a loud runtime summary, not a block.
    """
    import os

    from .runner import load_scripts

    issues: list[str] = []
    known = list(getattr(project, "experiment_names", []))

    def _own_has(rep: str, name: str) -> bool:
        cfg = os.path.join(project.experiment_dir(rep),
                           "tracking_config.yaml")
        try:
            own = load_scripts(cfg)
        except Exception:  # noqa: BLE001
            return False
        return any(s.get("name") == name for s in own)

    ## Scripts arrive through the LENIENT parses (Project.__init__,
    ## load_batch_file), so steps may be None/non-list and a step or its
    ## params any type. This runs in a Qt slot, where an uncaught exception
    ## is fatal — malformed shapes are skipped here and reported by
    ## run_project_script's validation instead.
    raw_steps = script.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) \
                or step.get("action") != "run_in_experiments":
            continue
        params = step.get("params")
        if not isinstance(params, dict):
            continue
        name = str(params.get("script", "")).strip()
        only = _parse_only(params.get("only"))
        unknown = [n for n in only if n not in known]
        if unknown:
            issues.append(f"Step {i}: no replicate named "
                          + ", ".join(f"'{n}'" for n in unknown))
        if not name or project.find_experiment_script(name) is not None:
            continue
        if only:
            unresolved = [n for n in only
                          if n in known and not _own_has(n, name)]
            if unresolved:
                issues.append(
                    f"Step {i}: script '{name}' resolves nowhere for "
                    + ", ".join(f"'{n}'" for n in unresolved)
                    + " (not in project.yaml experiment_scripts nor in "
                    "their tracking_config.yaml)")
        elif known and not any(_own_has(n, name) for n in known):
            issues.append(
                f"Step {i}: script '{name}' resolves nowhere — not in "
                "project.yaml experiment_scripts nor in any replicate's "
                "tracking_config.yaml")
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
