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

    def __init__(self):
        self.calls: list = []
        self.project_directory = "/nowhere"
        self.experiment_names = ["Rep1", "Rep2"]
        self.scripts = []
        self.experiment_scripts = []

    def run_all(self, make_reports=True, skip_analyzed=False, log=print):
        self.calls.append(("run_all", make_reports, skip_analyzed))
        return []

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
    assert sorted(pa.PROJECT_ACTIONS) == [
        "build_combined_analysis", "generate_ai_narrative", "project_report",
        "render_publication_figures", "run_all_analyses",
        "run_in_experiments", "validate_design"]
    assert pa.project_validation_issues(pa.STANDARD_PIPELINE["steps"]) == []
    # Unknown / invalid steps are caught before any side-effect.
    issues = pa.project_validation_issues(
        [{"action": "load_experiment", "params": {}}])
    assert issues and "Unknown project action" in issues[0][1]


def test_runner_executes_project_steps_in_order():
    fake = _FakeProject()
    script = {"name": "s", "steps": [
        {"action": "run_all_analyses",
         "params": {"reports": False, "skip_analyzed": True}},
        {"action": "build_combined_analysis", "params": {}},
        {"action": "render_publication_figures", "params": {"format": "both"}},
        {"action": "project_report", "params": {}},
    ]}
    logs: list[str] = []
    pa.run_project_script(script, fake, log_cb=logs.append)
    assert fake.calls == [("run_all", False, True), ("combined",),
                          ("figures", ("svg", "pdf")), ("report",)]
    assert any("complete" in line for line in logs)


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
                   "steps": [{"action": "build_combined_analysis",
                              "params": {}}]}], key="scripts")
    win = hub_mod.HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()
    combo = win._project_script_combo
    items = [(combo.itemText(i), combo.itemData(i))
             for i in range(combo.count())]
    assert items[0] == ("Standard pipeline (built-in)", None)
    assert ("mine", "mine") in items

    ran: list = []
    monkeypatch.setattr(hub_mod.HubWindow, "_spawn_task",
                        lambda self, name, fn: ran.append((name, fn)))
    combo.setCurrentIndex(1)                 # 'mine'
    win._project_run_script()
    assert ran and "mine" in ran[0][0]
    win.close()
