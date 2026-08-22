"""Tests for the Batch level (ADR-0009): structural detection, the lazy
batch.yaml, designation resolution (central → project's own → built-ins),
the Report Pipeline's conditional figure step, and the continue-on-error
Batch Run executor."""

from __future__ import annotations

import os

import pytest
import yaml

from pytrackinganalysis import batch as batch_mod
from pytrackinganalysis import project as prj
from pytrackinganalysis.script_editor import project_actions as pa

from test_project import _make_project


def _make_batch(tmp_path, names=("P1", "P2")):
    for name in names:
        (tmp_path / name).mkdir()
        _make_project(tmp_path / name)
    return tmp_path


# ---- structural detection --------------------------------------------------

def test_batch_is_structural(tmp_path):
    assert not batch_mod.is_batch_dir(tmp_path)          # empty folder
    _make_batch(tmp_path)
    (tmp_path / "notes").mkdir()
    assert batch_mod.is_batch_dir(tmp_path)
    assert batch_mod.batch_project_names(tmp_path) == ["P1", "P2"]
    # A Project is never also a Batch, whatever its subdirectories hold.
    assert not batch_mod.is_batch_dir(tmp_path / "P1")
    prj.create_project_file(str(tmp_path))
    assert not batch_mod.is_batch_dir(tmp_path)


# ---- batch.yaml ------------------------------------------------------------

def test_load_batch_file_missing_and_lenient(tmp_path):
    assert batch_mod.load_batch_file(tmp_path) == {
        "script": None, "project_scripts": []}
    # A malformed document yields empty sections, never an exception — one
    # bad block must not take down a whole Batch Run.
    (tmp_path / "batch.yaml").write_text("- not a mapping\n",
                                         encoding="utf-8")
    assert batch_mod.load_batch_file(tmp_path)["project_scripts"] == []
    (tmp_path / "batch.yaml").write_text(
        yaml.safe_dump({"script": " Night run ",
                        "project_scripts": [
                            {"name": "Night run", "steps": []},
                            "garbage",
                            {"steps": []},           # nameless: dropped
                        ]}), encoding="utf-8")
    meta = batch_mod.load_batch_file(tmp_path)
    assert meta["script"] == "Night run"
    assert [s["name"] for s in meta["project_scripts"]] == ["Night run"]


def test_save_designation_is_lazy_and_preserves_keys(tmp_path):
    # The default (None) never CREATES the file — the lazy-marker rule.
    batch_mod.save_batch_designation(tmp_path, None)
    assert not (tmp_path / "batch.yaml").exists()

    batch_mod.save_batch_designation(tmp_path, "Standard pipeline")
    data = yaml.safe_load((tmp_path / "batch.yaml").read_text())
    assert data == {"script": "Standard pipeline"}

    # Unknown keys survive a rewrite; None clears the key, keeps the file.
    (tmp_path / "batch.yaml").write_text(
        "script: Standard pipeline\nproject_scripts: []\ncustom: 1\n",
        encoding="utf-8")
    batch_mod.save_batch_designation(tmp_path, "Night run")
    data = yaml.safe_load((tmp_path / "batch.yaml").read_text())
    assert data["script"] == "Night run" and data["custom"] == 1
    batch_mod.save_batch_designation(tmp_path, None)
    data = yaml.safe_load((tmp_path / "batch.yaml").read_text())
    assert "script" not in data and data["custom"] == 1


# ---- designation resolution ------------------------------------------------

def test_resolution_order_central_then_own_then_builtin(tmp_path):
    _make_batch(tmp_path, names=("P1",))
    project = prj.Project(str(tmp_path / "P1"))
    central = [{"name": "Report pipeline", "steps": [
        {"action": "project_report", "params": {}}]}]
    # Central wins, even over a built-in's name.
    script, source, _ = batch_mod.resolve_designated_script(
        "Report pipeline", central, project)
    assert source == "batch.yaml project_scripts"
    assert script is central[0]
    # The project's own scripts: are the second tier.
    project.scripts = [{"name": "mine", "steps": []}]
    script, source, _ = batch_mod.resolve_designated_script(
        "mine", [], project)
    assert source == "project.yaml scripts"
    # Built-ins are last; an unknown name resolves nowhere.
    script, source, _ = batch_mod.resolve_designated_script(
        "Standard pipeline", [], project)
    assert script is pa.STANDARD_PIPELINE and source == "built-in"
    script, _, _ = batch_mod.resolve_designated_script("nope", [], project)
    assert script is None


def test_no_designation_runs_each_projects_own_script(tmp_path):
    """No designation means each Project's OWN default script — every
    project.yaml is created with one, so nothing is silently substituted
    (ADR-0009 amendment)."""
    _make_batch(tmp_path, names=("P1",))
    project = prj.Project(str(tmp_path / "P1"))
    script, source, note = batch_mod.resolve_designated_script(
        None, [], project)
    assert source == "project.yaml scripts"
    assert script["name"] == pa.DEFAULT_PROJECT_SCRIPT_NAME
    assert script is project.scripts[0]
    assert note is None
    # The figure step stays in the script and skips itself at run time when
    # the Project has no plot_specs.yaml (the guard is in the action now).
    assert "render_publication_figures" in [s["action"] for s in
                                            script["steps"]]

    # A renamed default still runs: the first authored script is used.
    project.scripts = [{"name": "Nightly", "steps": []}]
    script, source, _ = batch_mod.resolve_designated_script(None, [], project)
    assert script["name"] == "Nightly" and source == "project.yaml scripts"


def test_no_script_at_all_fails_that_project(tmp_path):
    """The replacement for the old built-in fallback: a Project with no
    Project Script does not run, and says why."""
    _make_batch(tmp_path, names=("P1",))
    project = prj.Project(str(tmp_path / "P1"))
    project.scripts = []
    script, source, _ = batch_mod.resolve_designated_script(None, [], project)
    assert script is None and source == ""


def test_builtin_report_pipeline_still_drops_figures_without_specs(tmp_path):
    """Designating the built-in by name remains available, conditional
    figure step and all."""
    _make_batch(tmp_path, names=("P1",))
    project = prj.Project(str(tmp_path / "P1"))
    project.scripts = []            # so the name falls through to built-ins
    script, source, note = batch_mod.resolve_designated_script(
        "Report pipeline", [], project)
    assert source == "built-in"
    assert "render_publication_figures" not in [
        s["action"] for s in script["steps"]]
    assert "plot_specs.yaml" in note
    (tmp_path / "P1" / "plot_specs.yaml").write_text("plots: {}\n",
                                                     encoding="utf-8")
    script, _, note = batch_mod.resolve_designated_script(
        "Report pipeline", [], project)
    assert [s["action"] for s in script["steps"]] == [
        "project_report", "render_publication_figures"]
    assert note is None


def test_report_pipeline_is_valid_and_ungated():
    assert pa.project_validation_issues(pa.REPORT_PIPELINE["steps"]) == []
    # No validate_design gate: Projects mid-migration must not fail the
    # default batch designation (ADR-0009).
    assert all(s["action"] != "validate_design"
               for s in pa.REPORT_PIPELINE["steps"])


# ---- the Batch Run executor ------------------------------------------------

def test_run_batch_continue_on_error_and_skips(tmp_path, monkeypatch):
    _make_batch(tmp_path)
    (tmp_path / "notes").mkdir()                  # not a Project: skipped
    (tmp_path / "Broken").mkdir()                 # loads, then raises
    (tmp_path / "Broken" / "project.yaml").write_text("name: B\n",
                                                      encoding="utf-8")

    ran: list = []

    def fake_run(script, project, log_cb, figure_cb=None):
        name = os.path.basename(project.project_directory)
        ran.append((name, script["name"]))
        if name == "P2":
            raise pa.ProjectScriptError("boom")

    monkeypatch.setattr(pa, "run_project_script", fake_run)
    logs: list[str] = []
    results = batch_mod.run_batch(str(tmp_path), log=logs.append)

    # An empty designless Project raises at load — that Project's failure,
    # never the run's; the boom in P2 is likewise contained.
    assert results["Broken"].startswith("ValueError")
    assert results["P1"] == "ok"
    assert "boom" in results["P2"]
    # Each Project ran its own seeded default, named "batch".
    assert ran == [("P1", pa.DEFAULT_PROJECT_SCRIPT_NAME),
                   ("P2", pa.DEFAULT_PROJECT_SCRIPT_NAME)]
    # Non-Project children are skipped with a log line, and a Batch Run
    # never creates or upgrades a project.yaml.
    assert any("notes" in line and "skipped" in line for line in logs)
    assert not (tmp_path / "notes" / "project.yaml").exists()
    assert any("1/3" in line for line in logs)


def test_run_batch_subset_and_designated_name(tmp_path, monkeypatch):
    _make_batch(tmp_path)
    (tmp_path / "batch.yaml").write_text(yaml.safe_dump({
        "script": "Night run",
        "project_scripts": [{"name": "Night run", "steps": [
            {"action": "project_report", "params": {}}]}]}),
        encoding="utf-8")
    ran: list = []
    monkeypatch.setattr(
        pa, "run_project_script",
        lambda script, project, log_cb, figure_cb=None:
        ran.append((os.path.basename(project.project_directory),
                    script["name"])))
    results = batch_mod.run_batch(str(tmp_path), project_names=["P2"],
                                  log=lambda _m: None)
    assert results == {"P2": "ok"}
    assert ran == [("P2", "Night run")]


def test_resolution_central_beats_own_when_both_define_the_name(tmp_path):
    """Pin the order — it was silently flipped once. Central wins, then the
    Project's own, then built-ins (ADR-0009)."""
    _make_batch(tmp_path, names=("P1",))
    project = prj.Project(str(tmp_path / "P1"))
    project.scripts = [{"name": "dup", "steps": []}]
    central = [{"name": "dup", "steps": [
        {"action": "project_report", "params": {}}]}]
    script, source, _ = batch_mod.resolve_designated_script(
        "dup", central, project)
    assert source == "batch.yaml project_scripts"
    assert script is central[0]
    # A padded central name still resolves — the designation is stripped on
    # load, so the comparison strips too.
    padded = [{"name": " padded ", "steps": []}]
    script, _, _ = batch_mod.resolve_designated_script(
        "padded", padded, project)
    assert script is padded[0]


def test_run_batch_empty_subset_and_unknown_names(tmp_path, monkeypatch):
    _make_batch(tmp_path)
    called: list = []
    monkeypatch.setattr(pa, "run_project_script",
                        lambda *a, **k: called.append(1))
    logs: list[str] = []
    # An explicit empty subset runs nothing — unlike None, which means all.
    assert batch_mod.run_batch(str(tmp_path), project_names=[],
                               log=logs.append) == {}
    assert called == []
    assert any("No Projects to run" in line for line in logs)
    # A stale requested name is ignored with a log line, never silently.
    logs.clear()
    results = batch_mod.run_batch(str(tmp_path),
                                  project_names=["P1", "Ghost"],
                                  log=logs.append)
    assert sorted(results) == ["P1"]
    assert any("Ghost" in line and "ignored" in line for line in logs)


def test_run_batch_summary_survives_an_empty_error_message(
        tmp_path, monkeypatch):
    """str() of a bare exception is empty — the summary must not crash and
    the per-Project result must still say something."""
    _make_batch(tmp_path, names=("P1",))

    def boom(script, project, log_cb, figure_cb=None):
        raise ValueError()

    monkeypatch.setattr(pa, "run_project_script", boom)
    logs: list[str] = []
    results = batch_mod.run_batch(str(tmp_path), log=logs.append)
    assert results["P1"] == "ValueError"
    assert any("0/1" in line for line in logs)


def test_run_batch_unresolvable_designation_fails_that_project(
        tmp_path, monkeypatch):
    _make_batch(tmp_path, names=("P1",))
    called: list = []
    monkeypatch.setattr(pa, "run_project_script",
                        lambda *a, **k: called.append(1))
    results = batch_mod.run_batch(str(tmp_path), script_name="ghost",
                                  log=lambda _m: None)
    assert called == []
    assert "ghost" in results["P1"]


# ---- the Batch AI narrative ------------------------------------------------

class _FakeSummarizer:
    """Stands in for a provider: records what it was asked, returns prose."""

    display_name = "Fake"
    model = "fake-1"

    def __init__(self):
        self.instructions = None
        self.text = None

    def summarize(self, payload, instructions):
        self.instructions = instructions
        self.text = payload.text
        return "P1 avoided light; P2 lost most of its flies to exclusions."


def _write_narrative(project_dir, name, body):
    analysis = project_dir / "analysis"
    analysis.mkdir(exist_ok=True)
    (analysis / "ai_narrative.md").write_text(
        f"# AI narrative — {name}\n\n{body}\n", encoding="utf-8")


def test_batch_narrative_synthesizes_the_project_narratives(
        tmp_path, monkeypatch):
    _make_batch(tmp_path, names=("P1", "P2"))
    _write_narrative(tmp_path / "P1", "P1", "Strong avoidance; 2/24 excluded.")
    _write_narrative(tmp_path / "P2", "P2", "Inconclusive; 18/24 excluded.")

    fake = _FakeSummarizer()
    monkeypatch.setattr("pytrackinganalysis.ai.get_summarizer",
                        lambda provider, model=None: fake)

    path = batch_mod.generate_batch_narrative(
        str(tmp_path), "anthropic", ensure_projects=False, log=lambda _m: None)

    assert os.path.basename(path) == batch_mod.BATCH_NARRATIVE_FILENAME
    assert os.path.dirname(path) == str(tmp_path)     # at the Batch root
    body = open(path, encoding="utf-8").read()
    assert "P1 avoided light" in body
    assert "Projects summarized (2):** P1, P2" in body
    # Both Projects reached the model, each labelled.
    assert "PROJECT: P1" in fake.text and "PROJECT: P2" in fake.text
    # The prompt asks for what the user actually wants out of a batch.
    assert "design" in fake.instructions.lower()
    assert "fly loss" in fake.instructions.lower()


def test_batch_narrative_names_the_projects_it_could_not_read(
        tmp_path, monkeypatch):
    """A synthesis that silently skipped half the batch reads exactly like
    one that covered it, so the front matter has to say."""
    _make_batch(tmp_path, names=("P1", "P2"))
    _write_narrative(tmp_path / "P1", "P1", "Strong avoidance.")

    monkeypatch.setattr("pytrackinganalysis.ai.get_summarizer",
                        lambda provider, model=None: _FakeSummarizer())
    path = batch_mod.generate_batch_narrative(
        str(tmp_path), "anthropic", ensure_projects=False, log=lambda _m: None)
    body = open(path, encoding="utf-8").read()
    assert "Projects summarized (1):** P1" in body
    assert "no narrative (excluded)" in body and "P2" in body


def test_batch_narrative_generates_a_missing_project_narrative_first(
        tmp_path, monkeypatch):
    """The default 'batch' script rebuilds Combined Analysis, which deletes
    each Project's narrative — so straight after a run there is usually
    nothing to read, and the step has to make one."""
    _make_batch(tmp_path, names=("P1",))
    generated: list = []

    def fake_generate(self, provider, model=None):
        generated.append(os.path.basename(self.project_directory))
        _write_narrative(tmp_path / "P1", "P1", "Freshly written.")
        return "Freshly written."

    monkeypatch.setattr(prj.Project, "generate_ai_summary", fake_generate)
    monkeypatch.setattr("pytrackinganalysis.ai.get_summarizer",
                        lambda provider, model=None: _FakeSummarizer())

    path = batch_mod.generate_batch_narrative(
        str(tmp_path), "anthropic", log=lambda _m: None)
    assert generated == ["P1"]
    body = open(path, encoding="utf-8").read()
    assert "regenerated for this run:** P1" in body


def test_batch_narrative_refuses_when_there_is_nothing_to_summarize(tmp_path):
    from pytrackinganalysis.ai.base import AISummaryError

    _make_batch(tmp_path, names=("P1",))
    with pytest.raises(AISummaryError, match="No Project narratives"):
        batch_mod.generate_batch_narrative(
            str(tmp_path), "anthropic", ensure_projects=False,
            log=lambda _m: None)
