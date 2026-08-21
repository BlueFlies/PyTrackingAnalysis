"""Tests for the Project layer (ADR-0005): identity, replicate discovery,
design-match validation, the Combined Analysis, pooled + mixed statistics,
and the Project Report model."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest
import yaml

from pytrackinganalysis import project as prj


def _exp_config(levels=("chr", "control"), min_movement=140):
    return {
        "global": {
            "experiment_type": "Valence",
            "tracking_rig": "arena_max",
            "facet_cutoffs": [10, 70],
            "experimental_design_factors": {"genotype": list(levels)},
            "min_transitions": 5,
            "min_movement": min_movement,
        },
        "counting_regions": {"Light": {"alias": "L"},
                             "NoLight": {"alias": "N"}},
        "tracking_regions": {"T_0": {"experimental_factors": "chr"}},
    }


def _summary_frame(seed=0, n_per=6):
    rng = np.random.default_rng(seed)
    treat = ["chr"] * n_per + ["control"] * n_per
    n = len(treat)
    return pd.DataFrame({
        "Treatment": treat,
        "Name": [f"T_{i}_0" for i in range(n)],
        "FinalPI": np.where(np.array(treat) == "chr",
                            rng.normal(0.5, 0.15, n),
                            rng.normal(0.0, 0.15, n)),
        "FinalPercentage": rng.uniform(0.3, 0.8, n),
        "TotalDistancePerMin": rng.uniform(80, 300, n),
        "TransitionsPerMin": rng.uniform(0.2, 3.0, n),
        "LowMovementFlag": [False] * n,
    })


def _make_project(tmp_path, names=("Rep1", "Rep2"), with_analysis=True,
                  config_for=None):
    prj.create_project_file(str(tmp_path), "Proj", notes="notes here")
    for i, name in enumerate(names):
        d = tmp_path / name
        (d / "analysis").mkdir(parents=True)
        cfg = (config_for or (lambda _n: _exp_config()))(name)
        (d / "tracking_config.yaml").write_text(
            yaml.safe_dump(cfg), encoding="utf-8")
        if with_analysis:
            summary = _summary_frame(seed=i)
            summary.to_csv(d / "analysis" / "Rec_Summary.csv", index=False)
            frames = []
            for win in ["(0, 10)", "(10, 70)", "(70, inf)"]:
                f = _summary_frame(seed=i + 10)
                f["FacetRange"] = win
                frames.append(f)
            pd.concat(frames).to_csv(d / "analysis" / "Rec_Summary_Facet.csv",
                                     index=False)
            pd.DataFrame({"Name": [f"x{i}"], "TrackingRegion": ["T_9"],
                          "Treatment": ["chr"], "Transitions": [1]}).to_csv(
                d / "analysis" / "Rec_Excluded.csv", index=False)
    return prj.Project(str(tmp_path))


# ---- identity & validation -------------------------------------------------

def test_marker_and_discovery(tmp_path):
    assert not prj.is_project_dir(str(tmp_path))
    p = _make_project(tmp_path)
    assert prj.is_project_dir(str(tmp_path))
    assert p.name == "Proj" and p.notes == "notes here"
    assert p.experiment_names == ["Rep1", "Rep2"]
    assert p.design_factors == {"genotype": ["chr", "control"]}
    assert p.experiment_type.name == "Valence"


def test_no_experiments_is_an_error(tmp_path):
    prj.create_project_file(str(tmp_path))
    with pytest.raises(ValueError, match="no experiments"):
        prj.Project(str(tmp_path))


def test_design_mismatch_hard_fails(tmp_path):
    def config_for(name):
        if name == "Rep2":
            return _exp_config(levels=("chr", "ctrl"))   # near-miss level
        return _exp_config()

    with pytest.raises(ValueError, match="Rep2.*genotype"):
        _make_project(tmp_path, config_for=config_for)


def test_criteria_differences_warn_not_fail(tmp_path):
    def config_for(name):
        return _exp_config(min_movement=100 if name == "Rep2" else 140)

    p = _make_project(tmp_path, config_for=config_for)
    assert any("min_movement" in w for w in p.warnings)


# ---- combined analysis -----------------------------------------------------

def test_combined_frames_and_build(tmp_path):
    p = _make_project(tmp_path)
    summary, facet, excluded, missing = p.combined_frames()
    assert missing == []
    assert list(summary.columns)[0] == "Experiment"
    assert len(summary) == 24 and summary["Experiment"].nunique() == 2
    assert len(excluded) == 2

    result = p.build_combined_analysis()
    names = sorted(os.path.basename(w) for w in result["written"])
    assert names == ["Proj_Excluded.csv", "Proj_Stats.txt",
                     "Proj_Summary.csv", "Proj_Summary_Facet.csv"]
    text = open(os.path.join(p.analysis_path, "Proj_Stats.txt"),
                encoding="utf-8").read()
    assert "mixed" in text and "Welch" in text


def test_missing_replicate_reported_not_analyzed(tmp_path):
    p = _make_project(tmp_path, names=("Rep1", "Rep2", "Rep3"),
                      with_analysis=False)
    with pytest.raises(ValueError, match="Rep1, Rep2, Rep3"):
        p.build_combined_analysis()


# ---- statistics ------------------------------------------------------------

def test_comparison_rows_pooled_and_mixed(tmp_path):
    p = _make_project(tmp_path)
    summary, facet, _, _ = p.combined_frames()
    rows = p.comparison_rows(summary, facet)
    pi_rows = [r for r in rows if r["metric"] == "FinalPI"]
    assert {r["phase"] for r in pi_rows} == \
        {"Acclimation", "Experiment", "Cooldown"}
    r = pi_rows[0]
    assert r["a"] == "chr" and r["b"] == "control"
    assert r["n_a"] == 12 and r["n_b"] == 12          # pooled across 2 reps
    # The synthetic effect (chr ≈ +0.5 vs control ≈ 0) is detected by both.
    assert r["p_pooled"] < 0.01
    assert r["p_mixed"] is not None and r["p_mixed"] < 0.05


def test_parse_window_handles_inf():
    assert prj.Project.parse_window("(10, 70)") == (10.0, 70.0)
    assert prj.Project.parse_window("(70, inf)") == (70.0, float("inf"))


# ---- report ----------------------------------------------------------------

def test_project_report_model_and_pdf(tmp_path):
    from pytrackinganalysis.report import model as m
    from pytrackinganalysis.report import render

    p = _make_project(tmp_path)
    model = p.build_report_model()
    kinds = [type(b).__name__ for b in model.blocks]
    assert kinds[0] == "Cover"
    tables = [b for b in model.blocks if isinstance(b, m.Table)]
    titles = [t.title for t in tables]
    assert "Statistical comparisons (pooled + mixed model)" in titles
    assert "Per-replicate summary" in titles
    stats = [t for t in tables if "pooled" in (t.title or "")][0]
    assert "Mixed p" in stats.columns
    reps = [t for t in tables if t.title == "Per-replicate summary"][0]
    assert [r[0] for r in reps.rows] == ["Rep1", "Rep2"]
    figures = [b for b in model.blocks if isinstance(b, m.Figure)]
    assert len(figures) >= 3                       # pooled pub figures

    out = p.create_report()
    assert os.path.basename(out) == "Proj_report.pdf"
    assert open(out, "rb").read(5) == b"%PDF-"


def test_ai_narrative_round_trip_and_embed(tmp_path):
    p = _make_project(tmp_path)
    assert p.read_ai_summary() is None
    p.write_ai_summary("Pooled results agree across replicates.",
                       "TestAI", "model-x")
    provenance, body = p.read_ai_summary()
    assert "TestAI model-x" in provenance and "agree" in body
    model = p.build_report_model()
    paragraphs = [b.text for b in model.blocks
                  if type(b).__name__ == "Paragraph"]
    assert any("agree across replicates" in t for t in paragraphs)
    # Rebuilding the Combined Analysis deletes the stale narrative.
    p.build_combined_analysis()
    assert p.read_ai_summary() is None


# ---- UI: hub project view & plot-editor project mode -----------------------

@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception:  # pragma: no cover
            pytest.skip("Qt unavailable")
    return app


def test_hub_project_view_populates_and_drills_in(qapp, tmp_path):
    from pytrackinganalysis.apps.hub import HubWindow

    _make_project(tmp_path)
    win = HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()
    card = win._cards["projectview"]
    assert not card.isHidden()
    assert win._exp_table.rowCount() == 2
    assert "Proj" in win._projectview_summary.text()
    assert win._exp_table.item(0, 0).text() == "Rep1"
    assert win._exp_table.item(0, 2).text() == "12"      # flies

    # project.yaml / plot_specs.yaml never offered as tracking configs
    combos = [win._config_combo.itemText(i)
              for i in range(win._config_combo.count())]
    assert "project.yaml" not in combos

    # Drilling into a replicate keeps the project view up (anchored to the
    # enclosing Project) with the current replicate's row selected.
    win._set_project_dir(str(tmp_path / "Rep1"))
    assert not card.isHidden()
    selected = win._exp_table.selectedItems()
    assert selected and selected[0].text() == "Rep1"
    win.close()


def test_editor_opens_project_dir_with_pooled_data(qapp, tmp_path):
    from pytrackinganalysis.apps.plot_editor import PlotEditorWindow

    _make_project(tmp_path)
    win = PlotEditorWindow()
    win.open_project(str(tmp_path))
    assert "Project: Proj (2 replicates)" in win._project_label.text()
    win._render_preview()
    assert win.preview.pixmap() is not None
    assert not win.preview.pixmap().isNull()
    data = win._current_data()
    assert "Experiment" in data.columns and len(data) == 24 * 3

    win.mark_check.setChecked(True)
    win._read_controls()
    assert win._current_spec().mark_experiments is True
    win._experiment = None
    win._project = None
    win.close()


def test_create_project_file_merges_and_preserves_unknown_keys(tmp_path):
    (tmp_path / "project.yaml").write_text(
        "name: Old\nnotes: keep me?\ncustom_key: survives\n", encoding="utf-8")
    prj.create_project_file(str(tmp_path), "NewName", notes="new notes")
    meta = yaml.safe_load((tmp_path / "project.yaml").read_text())
    assert meta["name"] == "NewName"
    assert meta["notes"] == "new notes"
    assert meta["custom_key"] == "survives"     # unknown keys preserved
    # Clearing notes removes the key rather than writing an empty string.
    prj.create_project_file(str(tmp_path), "NewName", notes="")
    meta = yaml.safe_load((tmp_path / "project.yaml").read_text())
    assert "notes" not in meta


def test_project_info_dialog_creates_and_edits(qapp, tmp_path):
    from pytrackinganalysis.apps.hub import ProjectInfoDialog

    target = tmp_path / "NewProj"
    dlg = ProjectInfoDialog(None, start_dir=str(target))
    assert dlg.windowTitle() == "Create project"
    dlg.name_edit.setText("My Study")
    dlg.notes_edit.setPlainText("Three replicates planned.")
    dlg._save()
    assert dlg.saved_dir == str(target)
    meta = yaml.safe_load((target / "project.yaml").read_text())
    assert meta["name"] == "My Study"
    assert meta["notes"] == "Three replicates planned."
    # The dialog writes the shared design too (type defaults seeded).
    g = meta["design"]["global"]
    assert g["experiment_type"] == "Valence"
    assert g["facet_cutoffs"] == [10, 70]
    assert g["min_transitions"] == 5 and g["min_movement"] == 140
    assert meta["design"]["counting_regions"] == ["Light", "NoLight"]

    # Reopening on the same directory switches to edit mode, prefilled.
    dlg2 = ProjectInfoDialog(None, start_dir=str(target))
    assert dlg2.windowTitle() == "Edit project"
    assert dlg2.name_edit.text() == "My Study"
    assert "replicates" in dlg2.notes_edit.toPlainText()
    dlg2.close()
    dlg.close()


def test_hub_sidebar_has_both_creation_flows(qapp, tmp_path):
    from PyQt6.QtWidgets import QPushButton

    from pytrackinganalysis.apps.hub import HubWindow

    win = HubWindow()
    texts = [b.text() for b in win.findChildren(QPushButton)]
    assert any("Create experiment" in t for t in texts)
    assert any("Create project" in t for t in texts)
    win.close()


def test_hub_project_context_survives_drill_in(qapp, tmp_path):
    from pytrackinganalysis.apps.hub import HubWindow

    _make_project(tmp_path)
    win = HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()
    card = win._cards["projectview"]
    assert not card.isHidden()
    assert win._up_btn.isHidden()          # at project level: no up button

    # Inside a replicate: the card STAYS up (enclosing project), project
    # actions resolve to the parent, and the up button offers the root.
    win._set_project_dir(str(tmp_path / "Rep1"))
    assert not card.isHidden()
    assert win._exp_table.rowCount() == 2
    assert not win._up_btn.isHidden()
    assert "Proj" in win._up_btn.text()
    project = win._current_project()
    assert project is not None and project.name == "Proj"

    # Double-clicking another row hops replicates directly (base = parent).
    win._open_selected_replicate(win._exp_table.item(1, 0))
    assert str(win._project_dir).endswith("Rep2")
    assert not card.isHidden()

    # Up returns the selected directory to the project root.
    win._go_up_to_project()
    assert win._up_btn.isHidden()
    assert str(win._project_dir) == str(tmp_path)
    win.close()


def test_project_table_refreshes_when_a_task_finishes(qapp, tmp_path):
    # Running an analysis on a loaded replicate must update its row from
    # "not analyzed" — every task completion refreshes the project view.
    from pytrackinganalysis.apps.hub import HubWindow

    _make_project(tmp_path, names=("Rep1", "Rep2"), with_analysis=False)
    win = HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()
    assert win._exp_table.item(0, 2).text() == "not analyzed"

    # Simulate what a finished Run Analysis leaves behind for Rep1…
    analysis = tmp_path / "Rep1" / "analysis"
    _summary_frame().to_csv(analysis / "Rec_Summary.csv", index=False)
    # …and the task-finished signal landing on the GUI thread.
    win._on_task_finished(object())
    assert win._exp_table.item(0, 2).text() == "12"      # flies now counted
    assert win._exp_table.item(1, 2).text() == "not analyzed"
    win.close()


def test_plot_editor_is_project_level_only(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    from pytrackinganalysis.apps.plot_editor import PlotEditorWindow

    ## Project and the standalone experiment must be SIBLINGS: a stray
    ## experiment dir inside the project would be discovered as a replicate.
    proj = tmp_path / "proj"
    proj.mkdir()
    _make_project(proj)
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    win = PlotEditorWindow()

    # A replicate inside a Project redirects up to the Project.
    win.open_project(str(proj / "Rep1"))
    assert "Project: Proj" in win._project_label.text()

    # A standalone experiment (no enclosing Project) is refused with guidance.
    alone = tmp_path / "alone"
    alone.mkdir()
    (alone / "tracking_config.yaml").write_text(
        yaml.safe_dump(_exp_config()), encoding="utf-8")
    messages = []
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: messages.append(a)))
    before = win._project_dir
    win.open_project(str(alone))
    assert messages and "Project level" in messages[0][2]
    assert win._project_dir == before          # nothing was opened
    win._experiment = None
    win._project = None
    win.close()


def test_hub_plot_editor_launches_with_project_root(qapp, tmp_path, monkeypatch):
    import subprocess

    from PyQt6.QtWidgets import QPushButton

    from pytrackinganalysis.apps import hub as hub_mod

    _make_project(tmp_path)
    launched = []

    class _Proc:
        pid = 12345

        def poll(self):
            return 0

    monkeypatch.setattr(hub_mod.subprocess, "Popen",
                        lambda args, **k: launched.append(args) or _Proc())
    win = hub_mod.HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()
    # Drill into a replicate, then use the Project card's Plot editor button:
    win._set_project_dir(str(tmp_path / "Rep1"))
    card = win._cards["projectview"]
    btn = [b for b in card.findChildren(QPushButton)
           if b.text() == "Plot editor…"][0]
    btn.click()
    assert launched and launched[0][-1] == str(tmp_path)   # project root, not Rep1

    # The top directory card no longer offers an experiment-scoped editor.
    top = win._cards["project"]
    assert not [b for b in top.findChildren(QPushButton)
                if "Plot editor" in b.text()]
    win.close()


# ---- design authority in project.yaml (ADR-0005 amendment) -----------------

_DESIGN = {
    "global": {
        "experiment_type": "Valence",
        "facet_cutoffs": [10, 70],
        "facet_labels": ["Acclimation", "Experiment", "Cooldown"],
        "experimental_design_factors": {"genotype": ["chr", "control"]},
        "min_transitions": 5,
        "min_movement": 140,
    },
    "counting_regions": ["Light", "NoLight"],
}


def _design_project(tmp_path, config_for=None, names=("Rep1", "Rep2")):
    import copy
    prj.create_project_file(str(tmp_path), "DProj", design=copy.deepcopy(_DESIGN))
    for name in names:
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        cfg = (config_for or (lambda _n: _exp_config()))(name)
        (d / "tracking_config.yaml").write_text(
            yaml.safe_dump(cfg), encoding="utf-8")
    return prj.Project(str(tmp_path))


def test_design_authority_accepts_conforming_and_resolved_defaults(tmp_path):
    def config_for(name):
        cfg = _exp_config()
        if name == "Rep2":
            # Omitting keys the type defaults still matches the design:
            # min_transitions resolves to 5, cutoffs to [10, 70].
            del cfg["global"]["min_transitions"]
            del cfg["global"]["facet_cutoffs"]
            # Aliases are experiment-specific — different ones are fine.
            cfg["counting_regions"]["Light"]["alias"] = "Lux, L1"
        return cfg

    p = _design_project(tmp_path, config_for)
    assert p.design_factors == {"genotype": ["chr", "control"]}
    assert p.experiment_type.name == "Valence"


def test_design_authority_rejects_mismatches(tmp_path):
    def bad_levels(name):
        cfg = _exp_config()
        if name == "Rep2":
            cfg["global"]["experimental_design_factors"] = {
                "genotype": ["chr", "ctrl"]}
        return cfg

    with pytest.raises(ValueError, match="Rep2.*genotype"):
        _design_project(tmp_path, bad_levels)


def test_design_authority_rejects_changed_global_value(tmp_path):
    def bad_cutoffs(name):
        cfg = _exp_config()
        if name == "Rep1":
            cfg["global"]["min_movement"] = 90     # differs from design's 140
        return cfg

    with pytest.raises(ValueError, match="Rep1.*min_movement"):
        _design_project(tmp_path, bad_cutoffs)


def test_design_authority_enforces_counting_region_names(tmp_path):
    def wrong_regions(name):
        cfg = _exp_config()
        if name == "Rep2":
            cfg["counting_regions"] = {"Bright": {"alias": "L"},
                                       "NoLight": {"alias": "N"}}
        return cfg

    with pytest.raises(ValueError, match="Rep2.*counting_regions"):
        _design_project(tmp_path, wrong_regions)


def test_empty_project_with_design_is_legal_and_scaffolds(tmp_path):
    import copy
    prj.create_project_file(str(tmp_path), "Empty", design=copy.deepcopy(_DESIGN))
    p = prj.Project(str(tmp_path))
    assert p.experiment_names == []
    assert p.experiment_type.name == "Valence"
    assert p.design_factors == {"genotype": ["chr", "control"]}

    cfg = p.scaffold_replicate_config()
    g = cfg["global"]
    assert g["experiment_type"] == "Valence"
    assert g["facet_cutoffs"] == [10, 70]
    assert g["min_transitions"] == 5 and g["min_movement"] == 140
    assert g["experimental_design_factors"] == {"genotype": ["chr", "control"]}
    assert list(cfg["counting_regions"]) == ["Light", "NoLight"]

    # A replicate written from the scaffold validates against the design.
    d = tmp_path / "Rep1"
    d.mkdir()
    (d / "tracking_config.yaml").write_text(yaml.safe_dump(cfg),
                                            encoding="utf-8")
    p2 = prj.Project(str(tmp_path))
    assert p2.experiment_names == ["Rep1"]


def test_legacy_projects_without_design_still_agree_based(tmp_path):
    # No design section -> the original agreement validation still applies.
    def config_for(name):
        return _exp_config(levels=("chr", "ctrl") if name == "Rep2"
                           else ("chr", "control"))

    with pytest.raises(ValueError, match="Rep2"):
        _make_project(tmp_path, config_for=config_for)


def test_dialog_design_round_trip_and_inference(qapp, tmp_path):
    from PyQt6.QtWidgets import QTableWidgetItem

    from pytrackinganalysis.apps.hub import ProjectInfoDialog

    # Creating with explicit factors writes them into the design…
    target = tmp_path / "P1"
    dlg = ProjectInfoDialog(None, start_dir=str(target))
    dlg.factors_table.insertRow(0)
    dlg.factors_table.setItem(0, 0, QTableWidgetItem("genotype"))
    dlg.factors_table.setItem(0, 1, QTableWidgetItem("chr, control"))
    dlg._save()
    meta = yaml.safe_load((target / "project.yaml").read_text())
    assert meta["design"]["global"]["experimental_design_factors"] == \
        {"genotype": ["chr", "control"]}

    # …and the written project is loadable + scaffolds a valid replicate.
    p = prj.Project(str(target))
    cfg = p.scaffold_replicate_config()
    assert cfg["global"]["experimental_design_factors"] == \
        {"genotype": ["chr", "control"]}

    # Wrapping existing experiments: the dialog infers the design from the
    # first replicate's config (migration path).
    wrap = tmp_path / "wrap"
    (wrap / "Old1").mkdir(parents=True)
    (wrap / "Old1" / "tracking_config.yaml").write_text(
        yaml.safe_dump(_exp_config()), encoding="utf-8")
    dlg2 = ProjectInfoDialog(None, start_dir=str(wrap))
    dlg2._prefill_from_dir()
    assert dlg2.factors_table.rowCount() == 1
    assert dlg2.factors_table.item(0, 0).text() == "genotype"
    assert dlg2.counting_edit.text() == "Light, NoLight"
    dlg2._save()
    p2 = prj.Project(str(wrap))       # validates Old1 against inferred design
    assert p2.experiment_names == ["Old1"]
    dlg.close()
    dlg2.close()


# ---- per-experiment configs inside a Project -------------------------------

def _project_with_bare_dirs(tmp_path, names=("FirstOne", "SecondOne")):
    """The common starting point: a Project created around folders that have
    no tracking_config.yaml yet."""
    import copy
    prj.create_project_file(str(tmp_path), "Bare",
                            design=copy.deepcopy(_DESIGN))
    for name in names:
        (tmp_path / name / "data").mkdir(parents=True)
    (tmp_path / "analysis").mkdir()          # a project output, not a replicate
    return prj.Project(str(tmp_path))


def test_unconfigured_dirs_lists_folders_without_a_config(tmp_path):
    p = _project_with_bare_dirs(tmp_path)
    assert p.experiment_names == []          # discovery is by config file
    assert p.unconfigured_dirs() == ["FirstOne", "SecondOne"]

    # Project outputs and dot/underscore folders are never candidates.
    (tmp_path / "figures").mkdir()
    (tmp_path / ".cache").mkdir()
    assert prj.Project(str(tmp_path)).unconfigured_dirs() == \
        ["FirstOne", "SecondOne"]


def test_scaffold_replicate_adopts_an_existing_folder(tmp_path):
    p = _project_with_bare_dirs(tmp_path)
    path = p.scaffold_replicate("FirstOne")
    assert path == str(tmp_path / "FirstOne" / "tracking_config.yaml")
    cfg = yaml.safe_load((tmp_path / "FirstOne" /
                          "tracking_config.yaml").read_text())
    assert cfg["global"]["experiment_type"] == "Valence"
    assert cfg["global"]["experimental_design_factors"] == \
        {"genotype": ["chr", "control"]}

    # The folder is now a replicate, and it validates against the design.
    p2 = prj.Project(str(tmp_path))
    assert p2.experiment_names == ["FirstOne"]
    assert p2.unconfigured_dirs() == ["SecondOne"]

    # A second scaffold never overwrites hand-made region assignments.
    with pytest.raises(FileExistsError):
        p2.scaffold_replicate("FirstOne")

    # A name that doesn't exist yet gets the directory and its data/ folder.
    p2.scaffold_replicate("Third")
    assert (tmp_path / "Third" / "data").is_dir()


def test_hub_project_dir_has_no_config_of_its_own(qapp, tmp_path):
    from pytrackinganalysis.apps.hub import HubWindow

    _project_with_bare_dirs(tmp_path)
    win = HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()

    # The Config selector used to fall back to "tracking_config.yaml" here,
    # pointing Edit config / Validate YAML at a file a Project never has.
    assert win._config_combo.count() == 0
    assert not win._config_combo.isEnabled()
    assert win._config_path() is None
    assert not win._btn_edit_cfg.isEnabled()
    assert "each experiment directory" in win._config_note.text()
    assert not win._config_note.isHidden()

    # The config-less folders are listed (discovery would hide them) and the
    # summary says how to fix them.
    names = [win._exp_table.item(r, 0).text()
             for r in range(win._exp_table.rowCount())]
    assert names == ["FirstOne", "SecondOne"]
    assert win._exp_table.item(0, 1).text() == "missing"
    assert "without a config" in win._projectview_summary.text()
    win.close()


def test_experiment_configs_dialog_creates_and_edits(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    from pytrackinganalysis.apps import hub as hub_mod

    _project_with_bare_dirs(tmp_path)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k:
                                     QMessageBox.StandardButton.Yes))
    launched: list = []

    class _Proc:
        pid = 4321

        def poll(self):
            return 0

    monkeypatch.setattr(hub_mod.subprocess, "Popen",
                        lambda args, **k: launched.append(args) or _Proc())

    win = hub_mod.HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()
    dlg = hub_mod.ExperimentConfigsDialog(win, win._current_project())
    assert [dlg._table.item(r, 1).text() for r in range(dlg._table.rowCount())] \
        == ["missing", "missing"]

    dlg._create_all_missing()
    for name in ("FirstOne", "SecondOne"):
        assert (tmp_path / name / "tracking_config.yaml").is_file()
    # Reloaded in place: both rows now carry a config, and the Project sees
    # them as replicates (they validate against the design).
    assert [dlg._table.item(r, 1).text() for r in range(dlg._table.rowCount())] \
        == ["yes", "yes"]
    assert prj.Project(str(tmp_path)).experiment_names == \
        ["FirstOne", "SecondOne"]

    # Editing opens the Config Editor on that experiment directory — not the
    # project root, which has no config.
    dlg._table.selectRow(0)
    dlg._edit_selected()
    assert launched and launched[0][-1] == str(tmp_path / "FirstOne")
    dlg.close()
    win.close()


def test_hub_add_experiment_anchors_on_the_project(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    from pytrackinganalysis.apps.hub import HubWindow

    _make_project(tmp_path, names=("Rep1",), with_analysis=False)
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Rep2", True)))
    win = HubWindow(initial_project=str(tmp_path))
    qapp.processEvents()

    # With a replicate open, the new replicate belongs to the Project — it
    # used to be created inside the currently selected directory.
    win._set_project_dir(str(tmp_path / "Rep1"))
    win._project_add_experiment()
    assert (tmp_path / "Rep2" / "tracking_config.yaml").is_file()
    assert not (tmp_path / "Rep1" / "Rep2").exists()
    win.close()
