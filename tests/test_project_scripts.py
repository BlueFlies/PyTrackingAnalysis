"""Tests for two-level scripting (ADR-0006): the project-action registry and
runner, the run_in_experiments bridge with its resolution order, the
generalized yaml script IO, the level-aware Script Editor, and the Hub's
script picker."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml

from pytrackinganalysis import project as prj
from pytrackinganalysis.script_editor import project_actions as pa
from pytrackinganalysis.script_editor.runner import load_scripts, save_scripts

from test_project import _make_project, qapp  # noqa: F401  (fixture reuse)


class _FakeProject:
    """Duck-typed Project recording which methods a script invoked."""

    def __init__(self, project_directory="/nowhere"):
        self.calls: list = []
        self.project_directory = str(project_directory)
        #: What run_all() reports back, so a partial run can be exercised.
        self.run_all_failures: list = []
        self.experiment_names = ["Rep1", "Rep2"]
        self.scripts = []
        self.experiment_scripts = []

    def run_all(self, make_reports=True, skip_analyzed=False, log=print):
        self.calls.append(("run_all", make_reports, skip_analyzed))
        return list(self.run_all_failures)

    def build_combined_analysis(self):
        self.calls.append(("combined",))
        return {"written": ["a", "b"], "missing": []}

    def render_figures(self, formats=("svg",)):
        self.calls.append(("figures", tuple(formats)))
        return [f"x.{f}" for f in formats]

    def create_report(self):
        self.calls.append(("report",))
        return "/nowhere/P_report.pdf"

    def generate_ai_summary(self, provider):
        self.calls.append(("ai", provider))
        raise RuntimeError("no key")

    def find_script(self, name):
        return next((s for s in self.scripts if s["name"] == name), None)

    def find_experiment_script(self, name):
        return next((s for s in self.experiment_scripts
                     if s["name"] == name), None)


# ---- registry & runner -----------------------------------------------------

def test_registry_roster_and_standard_pipeline():
    """A script action mirrors a Project-card button. There is no Run-all or
    Build-combined button, so there is no such action either — both are part
    of 'Create / update project report'."""
    assert sorted(pa.PROJECT_ACTIONS) == [
        "generate_ai_narrative", "project_report",
        "render_publication_figures", "run_in_experiments", "validate_design"]
    assert pa.project_validation_issues(pa.STANDARD_PIPELINE["steps"]) == []
    assert pa.project_validation_issues(pa.REPORT_PIPELINE["steps"]) == []
    # Unknown / invalid steps are caught before any side-effect.
    issues = pa.project_validation_issues(
        [{"action": "load_experiment", "params": {}}])
    assert issues and "Unknown project action" in issues[0][1]


def _figure_script() -> dict:
    return {"name": "s", "steps": [
        {"action": "project_report",
         "params": {"reports": False, "skip_analyzed": True}},
        {"action": "render_publication_figures", "params": {"format": "both"}},
    ]}


def test_project_report_step_is_the_whole_create_report_button(tmp_path):
    """The step makes the same three calls, in the same order, as the Hub's
    Create-report button: analyze every replicate, pool, then render."""
    (tmp_path / "plot_specs.yaml").write_text("plots: {}\n", encoding="utf-8")
    fake = _FakeProject(tmp_path)
    logs: list[str] = []
    pa.run_project_script(_figure_script(), fake, log_cb=logs.append)
    assert fake.calls == [("run_all", False, True), ("combined",),
                          ("report",), ("figures", ("svg", "pdf"))]
    assert any("complete" in line for line in logs)


def test_project_report_step_defaults_match_the_button(tmp_path):
    fake = _FakeProject(tmp_path)
    pa.run_project_script(
        {"name": "s", "steps": [{"action": "project_report", "params": {}}]},
        fake, log_cb=lambda _m: None)
    # make_reports=True, skip_analyzed=False — exactly hub._project_report.
    assert fake.calls == [("run_all", True, False), ("combined",), ("report",)]


def test_project_report_step_refuses_to_pool_a_partial_run(tmp_path):
    """Like the button, a replicate failure stops the step before pooling —
    a report over half-regenerated replicates is worse than none."""
    fake = _FakeProject(tmp_path)
    fake.run_all_failures = ["Rep2: boom"]
    with pytest.raises(pa.ProjectScriptError, match="Rep2: boom"):
        pa.run_project_script(
            {"name": "s",
             "steps": [{"action": "project_report", "params": {}}]},
            fake, log_cb=lambda _m: None)
    assert fake.calls == [("run_all", True, False)]     # no pool, no report


def test_figure_step_skips_itself_without_curated_specs(tmp_path):
    """The 'no plot_specs.yaml' condition lives in the ACTION, not only in
    the built-in pipeline (ADR-0009 amendment): the default script every
    project.yaml carries must not invent default-spec figures either."""
    fake = _FakeProject(tmp_path)          # no plot_specs.yaml
    logs: list[str] = []
    pa.run_project_script(_figure_script(), fake, log_cb=logs.append)
    assert ("figures", ("svg", "pdf")) not in fake.calls
    assert fake.calls == [("run_all", False, True), ("combined",), ("report",)]
    assert any("plot_specs.yaml" in line and "skipped" in line
               for line in logs)


# ---- retired actions -------------------------------------------------------

def test_a_saved_script_naming_a_retired_action_still_runs(tmp_path):
    """run_all_analyses / build_combined_analysis were folded into
    project_report. Scripts saved before that must not fail as 'unknown'."""
    fake = _FakeProject(tmp_path)
    logs: list[str] = []
    pa.run_project_script(
        {"name": "old", "steps": [
            {"action": "run_all_analyses", "params": {}},
            {"action": "build_combined_analysis", "params": {}},
            {"action": "project_report", "params": {}},
        ]}, fake, log_cb=logs.append)
    # The work happens once, not three times: both retired steps are dropped
    # because project_report already does what they did.
    assert fake.calls == [("run_all", True, False), ("combined",), ("report",)]
    assert sum("is now part of" in line for line in logs) == 2


def test_absorbing_never_turns_a_script_into_a_no_op(tmp_path):
    """An old 'just analyze everything' script has no project_report step —
    dropping its only step would silently do nothing, so the retired step
    becomes its replacement instead."""
    fake = _FakeProject(tmp_path)
    logs: list[str] = []
    pa.run_project_script(
        {"name": "old", "steps": [
            {"action": "run_all_analyses", "params": {}}]},
        fake, log_cb=logs.append)
    assert fake.calls == [("run_all", True, False), ("combined",), ("report",)]
    assert any("has been replaced by" in line for line in logs)


def test_absorbing_keeps_the_replacement_where_the_work_used_to_happen(
        tmp_path):
    """The old default ran analyses, pooled, rendered figures, then reported.
    Absorbing must not leave the figure step ahead of project_report — it
    would render from replicates nothing had analyzed yet."""
    (tmp_path / "plot_specs.yaml").write_text("plots: {}\n", encoding="utf-8")
    fake = _FakeProject(tmp_path)
    logs: list[str] = []
    pa.run_project_script(
        {"name": "old", "steps": [
            {"action": "run_all_analyses", "params": {}},
            {"action": "build_combined_analysis", "params": {}},
            {"action": "render_publication_figures", "params": {}},
            {"action": "project_report", "params": {}},
        ]}, fake, log_cb=logs.append)
    assert fake.calls == [("run_all", True, False), ("combined",),
                          ("report",), ("figures", ("svg",))]
    assert any("moved to step 1" in line for line in logs)

    steps, _ = pa.absorb_legacy_steps([
        {"action": "run_all_analyses", "params": {}},
        {"action": "render_publication_figures", "params": {}},
        {"action": "project_report", "params": {}},
    ])
    assert [s["action"] for s in steps] == [
        "project_report", "render_publication_figures"]


def test_absorbing_leaves_a_correctly_ordered_script_alone():
    """No gratuitous reordering: a script that already reports before it
    renders keeps its order."""
    steps, notes = pa.absorb_legacy_steps([
        {"action": "run_all_analyses", "params": {}},
        {"action": "project_report", "params": {}},
        {"action": "render_publication_figures", "params": {}},
    ])
    assert [s["action"] for s in steps] == [
        "project_report", "render_publication_figures"]
    assert not any("moved to step" in n for n in notes)


def test_the_editor_flags_a_retired_action_for_cleanup():
    """Not an 'unknown action' error — a named replacement the user can act
    on, while the run itself still absorbs the step."""
    issues = pa.project_validation_issues(
        [{"action": "build_combined_analysis", "params": {}}])
    assert len(issues) == 1
    assert "replaced by" in issues[0][1]
    assert "Create / update project report" in issues[0][1]


def test_ai_narrative_soft_fails_but_can_hard_fail():
    fake = _FakeProject()
    logs: list[str] = []
    pa.run_project_script(
        {"name": "s", "steps": [{"action": "generate_ai_narrative",
                                 "params": {"provider": "openai"}}]},
        fake, log_cb=logs.append)
    assert ("ai", "openai") in fake.calls
    assert any("skipped" in line for line in logs)     # soft-fail default
    with pytest.raises(RuntimeError, match="no key"):
        pa.run_project_script(
            {"name": "s", "steps": [{"action": "generate_ai_narrative",
                                     "params": {"provider": "openai",
                                                "soft_fail": False}}]},
            fake, log_cb=logs.append)


def test_validation_blocks_before_side_effects():
    fake = _FakeProject()
    with pytest.raises(pa.ProjectScriptError, match="validation failed"):
        pa.run_project_script(
            {"name": "s", "steps": [
                {"action": "project_report", "params": {}},
                {"action": "run_in_experiments", "params": {}},   # missing name
            ]}, fake, log_cb=lambda _m: None)
    assert fake.calls == []          # nothing ran


# ---- the bridge ------------------------------------------------------------

def test_run_in_experiments_resolution_and_failures(tmp_path, monkeypatch):
    p = _make_project(tmp_path)
    # Central definition wins; Rep2's own config also defines 'central' to
    # prove precedence. Rep-only script 'local' exercises the fallback.
    save_scripts(str(tmp_path / "project.yaml"),
                 [{"name": "central", "steps": [{"action": "run_qc",
                                                 "params": {}}]}],
                 key="experiment_scripts")
    save_scripts(str(tmp_path / "Rep2" / "tracking_config.yaml"),
                 [{"name": "central", "steps": [{"action": "nope"}]},
                  {"name": "local", "steps": [{"action": "run_qc",
                                               "params": {}}]}])
    p = prj.Project(str(tmp_path))
    ran: list = []

    def fake_run_script(script, *, project_dir, log_cb, figure_cb, exp):
        ran.append((os.path.basename(str(project_dir)), script["name"],
                    script["steps"][0]["action"]))

    monkeypatch.setattr("pytrackinganalysis.script_editor.runner.run_script",
                        fake_run_script)
    monkeypatch.setattr(prj.Project, "load_experiment",
                        lambda self, name: object())

    ctx = pa.ProjectRunContext(project=p, log=lambda _m: None)
    pa._exec_run_in_experiments({"script": "central"}, ctx)
    # The PROJECT's 'central' ran in both replicates — not Rep2's own broken one.
    assert ran == [("Rep1", "central", "run_qc"), ("Rep2", "central", "run_qc")]
    assert ctx.failures == []

    # Fallback: 'local' exists only in Rep2's config -> Rep1 is a recorded
    # failure, Rep2 runs; continue-on-error semantics.
    ran.clear()
    ctx = pa.ProjectRunContext(project=p, log=lambda _m: None)
    pa._exec_run_in_experiments({"script": "local"}, ctx)
    assert ran == [("Rep2", "local", "run_qc")]
    assert len(ctx.failures) == 1 and "Rep1" in ctx.failures[0]

    # The collected failures surface as one summary at the END of a run.
    with pytest.raises(pa.ProjectScriptError, match="Rep1"):
        pa.run_project_script(
            {"name": "s", "steps": [{"action": "run_in_experiments",
                                     "params": {"script": "local"}}]},
            p, log_cb=lambda _m: None)


# ---- yaml IO ---------------------------------------------------------------

def test_scripts_io_by_key_preserves_other_sections(tmp_path):
    path = tmp_path / "project.yaml"
    path.write_text("name: P\ndesign:\n  global:\n    experiment_type: "
                    "Valence\n", encoding="utf-8")
    save_scripts(str(path), [{"name": "a", "steps": []}], key="scripts")
    save_scripts(str(path), [{"name": "b", "steps": []}],
                 key="experiment_scripts")
    data = yaml.safe_load(path.read_text())
    assert data["name"] == "P"                       # untouched
    assert data["design"]["global"]["experiment_type"] == "Valence"
    assert [s["name"] for s in data["scripts"]] == ["a"]
    assert [s["name"] for s in data["experiment_scripts"]] == ["b"]
    assert load_scripts(str(path), key="experiment_scripts")[0]["name"] == "b"
    # Project parses both.
    (tmp_path / "Rep1").mkdir()
    (tmp_path / "Rep1" / "tracking_config.yaml").write_text(
        yaml.safe_dump({"global": {"experiment_type": "Valence"}}),
        encoding="utf-8")
    p = prj.Project(str(tmp_path))
    assert p.find_script("a") and p.find_experiment_script("b")


# ---- level-aware Script Editor --------------------------------------------

def test_script_editor_two_sections_and_save(qapp, tmp_path):  # noqa: F811
    from pytrackinganalysis.script_editor.window import ScriptEditorWindow

    _make_project(tmp_path)
    save_scripts(str(tmp_path / "project.yaml"),
                 [{"name": "pipeline",
                   "steps": [{"action": "project_report", "params": {}}]}],
                 key="scripts")
    win = ScriptEditorWindow(str(tmp_path / "project.yaml"))
    assert [s["label"] for s in win._sections] == \
        ["Project scripts", "Experiment scripts"]
    assert win._dirty is False
    # Project palette shows project actions; experiment section swaps it.
    keys = {t._action.key for t in win._palette._tiles}
    assert "project_report" in keys and "load_experiment" not in keys
    win._on_section_changed(1)
    keys = {t._action.key for t in win._palette._tiles}
    assert "load_experiment" in keys and "project_report" not in keys
    assert win._dirty is False               # switching edits nothing

    # Add an experiment script in section 2, save: both keys land on disk.
    win._new_script_named = None
    win._scripts.append({"name": "nightly",
                         "steps": [{"action": "run_qc", "params": {}}]})
    win._mark_dirty()
    win._save_silently = None
    # Bypass the modal in _save by saving directly through the runner path:
    from pytrackinganalysis.script_editor.runner import save_scripts as _ss
    for section in win._sections:
        _ss(win._config_path, section["scripts"], key=section["key"])
    data = yaml.safe_load((tmp_path / "project.yaml").read_text())
    assert [s["name"] for s in data["scripts"]] == ["pipeline"]
    assert [s["name"] for s in data["experiment_scripts"]] == ["nightly"]
    win.close()


def test_tracking_config_editor_unchanged(qapp, tmp_path):  # noqa: F811
    from pytrackinganalysis.script_editor.window import ScriptEditorWindow

    cfg = tmp_path / "tracking_config.yaml"
    cfg.write_text(yaml.safe_dump({
        "global": {"tracking_type": "TWOCHOICETRACKER"},
        "scripts": [{"name": "n", "steps": [{"action": "run_qc",
                                             "params": {}}]}],
    }), encoding="utf-8")
    win = ScriptEditorWindow(str(cfg))
    assert len(win._sections) == 1           # no level switcher for configs
    assert not hasattr(win, "_level_combo") or win._level_combo is None
    assert [s["name"] for s in win._scripts] == ["n"]
    assert win._experiment_type == "TWOCHOICETRACKER"
    win.close()


# ---- Hub picker ------------------------------------------------------------

def test_hub_script_picker_and_run(qapp, tmp_path, monkeypatch):  # noqa: F811
    from pytrackinganalysis.apps import hub as hub_mod

    _make_project(tmp_path)
    save_scripts(str(tmp_path / "project.yaml"),
                 [{"name": "mine",
                   "steps": [{"action": "validate_design",
                              "params": {}}]}], key="scripts")
    win = hub_mod.HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()
    combo = win._project_script_combo
    items = [(combo.itemText(i), combo.itemData(i))
             for i in range(combo.count())]
    # The project's OWN scripts come first and one is preselected (ADR-0009
    # amendment: every project.yaml carries a default script, so the picker
    # opens on a run the user can read in the Script Editor). The built-ins
    # stay below as explicit choices.
    assert items[0] == ("mine", "mine")
    assert combo.currentIndex() == 0
    assert ("Standard pipeline (built-in)", ("builtin", "standard")) in items
    assert ("Report pipeline (built-in)", ("builtin", "report")) in items

    ran: list = []
    monkeypatch.setattr(hub_mod.HubWindow, "_spawn_task",
                        lambda self, name, fn: ran.append((name, fn)))
    win._project_run_script()
    assert ran and "mine" in ran[0][0]
    win.close()


def test_hub_runs_report_pipeline_with_conditional_figures(
        qapp, tmp_path, monkeypatch):  # noqa: F811
    """The Report pipeline built-in runs the Create-report sequence; its
    figure step exists only when the Project has a plot_specs.yaml."""
    from pytrackinganalysis.apps import hub as hub_mod

    _make_project(tmp_path)
    win = hub_mod.HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()
    spawned: list = []
    monkeypatch.setattr(hub_mod.HubWindow, "_spawn_task",
                        lambda self, name, fn: spawned.append((name, fn())))
    seen: list = []
    monkeypatch.setattr(
        pa, "run_project_script",
        lambda script, project, log_cb, figure_cb=None:
        seen.append([s["action"] for s in script["steps"]]))

    combo = win._project_script_combo
    builtin = next(i for i in range(combo.count())
                   if combo.itemData(i) == ("builtin", "report"))
    combo.setCurrentIndex(builtin)
    win._project_run_script()
    assert spawned[0][0] == "Project script: Report pipeline"
    assert seen == [["project_report"]]            # no plot_specs.yaml

    (tmp_path / "plot_specs.yaml").write_text("plots: {}\n", encoding="utf-8")
    seen.clear()
    win._project_run_script()
    # Figures come after the report: project_report is what analyzes the
    # replicates the figure step then reads.
    assert seen == [["project_report", "render_publication_figures"]]
    win.close()


def test_new_project_yaml_carries_a_default_script(tmp_path, qapp,  # noqa: F811
                                                   monkeypatch):
    """Every project.yaml is created with a visible, editable default script
    (ADR-0009 amendment) — that is what replaces the built-in fallback."""
    from pytrackinganalysis.apps import hub as hub_mod

    _make_project(tmp_path)
    meta = yaml.safe_load((tmp_path / "project.yaml").read_text())
    script = meta["scripts"][0]
    # Named for the job it does, not the built-in it was seeded from: this
    # is the script a Batch Run executes in this Project.
    assert pa.DEFAULT_PROJECT_SCRIPT_NAME == "batch"
    assert script["name"] == "batch"
    # ...and distinct from the built-in, which stays separately resolvable.
    assert pa.REPORT_PIPELINE["name"] != pa.DEFAULT_PROJECT_SCRIPT_NAME
    assert [s["action"] for s in script["steps"]] == [
        "project_report", "render_publication_figures"]
    assert pa.project_validation_issues(script["steps"]) == []
    assert script["notes"]          # says where it came from and how to edit

    # An authored block is left alone — re-saving project info must not add
    # a second copy of the default or reorder what the user wrote.
    save_scripts(str(tmp_path / "project.yaml"),
                 [{"name": "mine", "steps": []}], key="scripts")
    prj.create_project_file(str(tmp_path), "Proj")
    meta = yaml.safe_load((tmp_path / "project.yaml").read_text())
    assert [s["name"] for s in meta["scripts"]] == ["mine"]

    # Emptying the block removes it (save_scripts drops an empty list), so
    # the next write seeds the default again — a project.yaml is never left
    # without a runnable script.
    save_scripts(str(tmp_path / "project.yaml"), [], key="scripts")
    assert "scripts" not in yaml.safe_load(
        (tmp_path / "project.yaml").read_text())
    prj.create_project_file(str(tmp_path), "Proj")
    meta = yaml.safe_load((tmp_path / "project.yaml").read_text())
    assert [s["name"] for s in meta["scripts"]] == [
        pa.DEFAULT_PROJECT_SCRIPT_NAME]

    # The Project card opens on that default, so the user sees it exists.
    win = hub_mod.HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()
    combo = win._project_script_combo
    assert combo.itemText(0) == pa.DEFAULT_PROJECT_SCRIPT_NAME
    assert combo.currentIndex() == 0
    win.close()


# ---- the only: param (targeted bridge) -------------------------------------

def test_run_in_experiments_only_targets_named_replicates(tmp_path,
                                                          monkeypatch):
    _make_project(tmp_path)
    save_scripts(str(tmp_path / "project.yaml"),
                 [{"name": "central", "steps": [{"action": "run_qc",
                                                 "params": {}}]}],
                 key="experiment_scripts")
    p = prj.Project(str(tmp_path))
    ran: list = []
    monkeypatch.setattr(
        "pytrackinganalysis.script_editor.runner.run_script",
        lambda script, *, project_dir, log_cb, figure_cb, exp:
        ran.append(os.path.basename(str(project_dir))))
    monkeypatch.setattr(prj.Project, "load_experiment",
                        lambda self, name: object())

    ctx = pa.ProjectRunContext(project=p, log=lambda _m: None)
    pa._exec_run_in_experiments({"script": "central", "only": ["Rep2"]}, ctx)
    assert ran == ["Rep2"]
    assert ctx.failures == []

    # A hand-edited comma string works; an unknown name is loud, not fatal:
    # recorded in the failure summary while the run continues (grill 2026-08).
    ran.clear()
    ctx = pa.ProjectRunContext(project=p, log=lambda _m: None)
    pa._exec_run_in_experiments({"script": "central",
                                 "only": "Rep1, Ghost"}, ctx)
    assert ran == ["Rep1"]
    assert len(ctx.failures) == 1 and "Ghost" in ctx.failures[0]


def test_only_param_validation_and_single_bridge():
    errs = pa._validate_run_in_experiments({"script": "s", "only": 7}, None)
    assert errs and "Only replicates" in errs[0]
    assert pa._validate_run_in_experiments(
        {"script": "s", "only": ["Rep1"]}, None) == []
    # only: is a param on the one bridge — never a second bridge action
    # (ADR-0006's "the only bridge" clause stays literally true).
    assert "run_in_experiment" not in pa.PROJECT_ACTIONS


def test_preflight_catches_typos_with_project_in_hand(tmp_path):
    _make_project(tmp_path)
    save_scripts(str(tmp_path / "project.yaml"),
                 [{"name": "central", "steps": []}], key="experiment_scripts")
    save_scripts(str(tmp_path / "Rep2" / "tracking_config.yaml"),
                 [{"name": "local", "steps": []}])
    p = prj.Project(str(tmp_path))

    def script_for(params):
        return {"name": "s", "steps": [
            {"action": "run_in_experiments", "params": params}]}

    # Clean: a central script targeted at a real replicate.
    assert pa.preflight_project_script_issues(
        script_for({"script": "central", "only": ["Rep1"]}), p) == []
    # Unknown replicate names are flagged before anything runs.
    issues = pa.preflight_project_script_issues(
        script_for({"script": "central", "only": ["Ghost"]}), p)
    assert issues and "Ghost" in issues[0]
    # Targeted: every named replicate must resolve the script.
    issues = pa.preflight_project_script_issues(
        script_for({"script": "local", "only": ["Rep1", "Rep2"]}), p)
    assert issues and "'Rep1'" in issues[0] and "'Rep2'" not in issues[0]
    # Broadcast: a partial spread is normal fallback territory, but a name
    # that resolves nowhere at all is a typo.
    assert pa.preflight_project_script_issues(
        script_for({"script": "local"}), p) == []
    issues = pa.preflight_project_script_issues(
        script_for({"script": "ghost"}), p)
    assert issues and "resolves nowhere" in issues[0]


def test_inspector_multilist_renders_replicate_checkboxes(qapp):  # noqa: F811
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLineEdit, QListWidget

    from pytrackinganalysis.script_editor.inspector import Inspector

    inspector = Inspector()
    action = pa.PROJECT_ACTIONS["run_in_experiments"]
    # Without live options the param degrades to a comma line edit.
    inspector.show_step(0, action, {"script": "qc", "only": ["Rep2"]})
    widget = inspector._widgets_by_name["only"]
    assert isinstance(widget, QLineEdit)
    assert "Rep2" in widget.text()
    # With options (the window scans the project.yaml's siblings) it becomes
    # a checkable list, and the saved selection round-trips.
    inspector.set_choices({"only": ["Rep1", "Rep2"]})
    widget = inspector._widgets_by_name["only"]
    assert isinstance(widget, QListWidget)
    states = {widget.item(i).text(): widget.item(i).checkState()
              for i in range(widget.count())}
    assert states["Rep2"] == Qt.CheckState.Checked
    assert states["Rep1"] == Qt.CheckState.Unchecked
    assert inspector._collect_params()["only"] == ["Rep2"]


def test_editor_feeds_replicate_names_to_only_param(qapp, tmp_path):  # noqa: F811
    from pytrackinganalysis.script_editor.window import ScriptEditorWindow

    _make_project(tmp_path)
    win = ScriptEditorWindow(str(tmp_path / "project.yaml"))
    assert win._inspector._choices.get("only") == ["Rep1", "Rep2"]
    win.close()


def test_editor_feeds_no_choices_for_a_tracking_config(qapp, tmp_path):  # noqa: F811
    from pytrackinganalysis.script_editor.window import ScriptEditorWindow

    cfg = tmp_path / "tracking_config.yaml"
    cfg.write_text(yaml.safe_dump(
        {"global": {"tracking_type": "TWOCHOICETRACKER"}}), encoding="utf-8")
    win = ScriptEditorWindow(str(cfg))
    assert win._inspector._choices == {}
    win.close()


def test_multilist_keeps_stale_saved_names_visible_and_checked(qapp):  # noqa: F811
    """A saved only: name whose replicate vanished must stay visible and
    checked — silently dropping it would rewrite the script on save."""
    from PyQt6.QtCore import Qt
    from pytrackinganalysis.script_editor.inspector import Inspector

    inspector = Inspector()
    inspector.set_choices({"only": ["Rep1"]})
    action = pa.PROJECT_ACTIONS["run_in_experiments"]
    inspector.show_step(0, action, {"script": "qc", "only": ["Gone"]})
    widget = inspector._widgets_by_name["only"]
    states = {widget.item(i).text(): widget.item(i).checkState()
              for i in range(widget.count())}
    assert states["Gone"] == Qt.CheckState.Checked
    assert states["Rep1"] == Qt.CheckState.Unchecked
    assert inspector._collect_params()["only"] == ["Gone"]


def test_preflight_survives_leniently_parsed_malformed_scripts(tmp_path):
    """The Hub calls preflight inside a Qt slot, where an uncaught exception
    is fatal — every shape the lenient parses can produce must be safe.
    Malformed steps fall through to run_project_script's validation."""
    _make_project(tmp_path)
    p = prj.Project(str(tmp_path))
    for script in (
        {"name": "draft", "steps": None},
        {"name": "draft", "steps": "run everything"},
        {"name": "draft", "steps": ["analyze"]},
        {"name": "draft", "steps": [{"action": "run_in_experiments",
                                     "params": "fast"}]},
        {"name": "draft"},
    ):
        assert pa.preflight_project_script_issues(script, p) == []


def test_parse_only_drops_null_items():
    assert pa._parse_only(["Rep1", None, " "]) == ["Rep1"]


def test_bridge_records_a_malformed_replicate_config_and_continues(
        tmp_path, monkeypatch):
    """A replicate whose scripts: block cannot be read is that replicate's
    failure — the broadcast continues instead of aborting the step."""
    _make_project(tmp_path)
    cfg_path = tmp_path / "Rep1" / "tracking_config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["scripts"] = ["oops"]            # load_scripts raises on this
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    save_scripts(str(tmp_path / "Rep2" / "tracking_config.yaml"),
                 [{"name": "local", "steps": [{"action": "run_qc",
                                               "params": {}}]}])
    p = prj.Project(str(tmp_path))
    ran: list = []
    monkeypatch.setattr(
        "pytrackinganalysis.script_editor.runner.run_script",
        lambda script, *, project_dir, log_cb, figure_cb, exp:
        ran.append(os.path.basename(str(project_dir))))
    monkeypatch.setattr(prj.Project, "load_experiment",
                        lambda self, name: object())
    ctx = pa.ProjectRunContext(project=p, log=lambda _m: None)
    pa._exec_run_in_experiments({"script": "local"}, ctx)
    assert ran == ["Rep2"]
    assert len(ctx.failures) == 1 and "Rep1" in ctx.failures[0]
