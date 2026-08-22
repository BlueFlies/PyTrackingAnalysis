"""Tests for the Hub tile-strip redesign (ADR-0007) and the Project-first Hub
(ADR-0008): the strip's six tiles, their live summaries and dimming across
loading states, the anchored panels (open/close/one-at-a-time/
auto-close-on-launch), and loading an experiment by double-clicking its row in
the replicates table."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from test_project import _make_project, qapp  # noqa: F401  (fixture reuse)


@pytest.fixture
def hub(qapp):  # noqa: F811
    from pytrackinganalysis.apps.hub import HubWindow

    win = HubWindow()
    win.resize(1400, 900)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


TILE_ORDER = ["project", "analyze", "plots", "scripts", "ai", "tools"]


def test_strip_has_six_fixed_tiles_and_full_width_output(hub):
    assert list(hub._tiles) == TILE_ORDER
    assert not hasattr(hub, "_sidebar")
    assert "tools" in hub._panels
    # Experiments load from the Project panel's table — no Experiment tile.
    assert "experiment" not in hub._panels
    assert "load" not in hub._cards
    # The output dock owns nearly the full window width under the strip.
    assert hub._plot_dock.width() > hub.width() - 80


def test_tiles_dim_with_hints_when_nothing_is_loaded(hub):
    assert hub._tiles["project"].is_dimmed()
    assert "no project" in hub._tiles["project"].summary_text()
    # Every experiment-dependent tile waits on a load, Scripts included:
    # its recipes run against the loaded experiment.
    for key in ("analyze", "plots", "scripts"):
        assert hub._tiles[key].is_dimmed(), key


def test_project_tile_reflects_state(hub, qapp, tmp_path):  # noqa: F811
    _make_project(tmp_path)
    hub._set_project_dir(str(tmp_path))
    qapp.processEvents()
    tile = hub._tiles["project"]
    assert not tile.is_dimmed()
    assert "Proj" in tile.summary_text()
    assert "2 replicates" in tile.summary_text()

    # Choosing a replicate directory selects the Project it belongs to.
    hub._set_project_dir(str(tmp_path / "Rep1"))
    assert not hub._tiles["project"].is_dimmed()
    assert "Proj" in hub._tiles["project"].summary_text()


def test_panels_open_one_at_a_time_and_toggle(hub, qapp):
    hub._open_panel("project")
    assert hub._open_panel_key == "project"
    assert hub._panels["project"].isVisible()
    assert hub._tiles["project"]._active

    hub._open_panel("analyze")                # switching closes the previous
    assert hub._open_panel_key == "analyze"
    assert not hub._panels["project"].isVisible()
    assert not hub._tiles["project"]._active

    hub._toggle_panel("analyze")              # toggling the open one closes
    assert hub._open_panel_key is None
    assert not hub._panels["analyze"].isVisible()


def test_tools_tile_opens_tools_panel(hub):
    hub._toggle_panel("tools")
    assert hub._open_panel_key == "tools"
    assert hub._panels["tools"].isVisible()
    assert hub._tiles["tools"]._active
    hub._close_panel()


def test_a_panel_survives_running_a_task(hub, qapp):
    """A panel closes on a click, not on a task: running one action then
    another from the same panel must not make it vanish underneath."""
    import time

    hub._open_panel("analyze")
    assert hub._panels["analyze"].isVisible()
    hub._spawn_task("noop", lambda: "done")
    assert hub._open_panel_key == "analyze"
    assert hub._panels["analyze"].isVisible()

    deadline = time.monotonic() + 10
    while hub._worker is not None and time.monotonic() < deadline:
        qapp.processEvents()
    assert hub._worker is None
    assert hub._open_panel_key == "analyze"   # still open when it finishes


def test_a_click_on_the_output_closes_the_panel_but_the_strip_does_not(
        hub, monkeypatch):
    """The three ways out: the same tile, another tile, or a click on the
    background. Clicks on the strip or inside the panel are not one of them."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication

    class _Press:
        def globalPosition(self):
            return QPointF(0, 0)

    def _clicking(widget):
        monkeypatch.setattr(QApplication, "widgetAt",
                            staticmethod(lambda _p: widget))

    hub._open_panel("analyze")
    _clicking(hub._panels["analyze"])         # inside the panel: stays open
    hub._handle_click_away(_Press())
    assert hub._open_panel_key == "analyze"

    _clicking(hub._tiles["plots"])            # on the strip: the tile decides
    hub._handle_click_away(_Press())
    assert hub._open_panel_key == "analyze"

    _clicking(hub._log)                       # the output area: closes
    hub._handle_click_away(_Press())
    assert hub._open_panel_key is None


def test_cards_live_inside_panels_and_stay_functional(hub):
    # The full existing cards moved into panels — handlers and widgets intact.
    project_panel = hub._panels["project"]
    assert hub._cards["project"] in project_panel.findChildren(type(hub._cards["project"]))
    assert hub._cards["projectview"] in project_panel.findChildren(type(hub._cards["projectview"]))
    # The replicates table is reachable exactly as before.
    assert hub._exp_table.parent() is not None


def test_tile_summary_lines_are_hard_capped(hub):
    tile = hub._tiles["project"]
    tile.set_summary(["x" * 100, "y" * 100, "third line is dropped"])
    text = tile.summary_text()
    assert all(len(line) <= 26 for line in text.splitlines())
    assert len(text.splitlines()) == 2


def test_status_panel_fills_the_strip_right_of_the_last_tile(hub):
    lay = hub._strip.layout()
    assert lay.itemAt(lay.count() - 1).widget() is hub._status_panel
    assert lay.itemAt(lay.count() - 2).widget() is hub._tiles["tools"]


def test_status_panel_reports_the_project_and_loaded_experiment(hub, qapp, tmp_path):  # noqa: F811
    class _Arena:
        experiment_name = "Rep1"

    class _Exp:
        arena = _Arena()

    assert "no project" in hub._status_panel.status_text().lower()

    _make_project(tmp_path)
    hub._set_project_dir(str(tmp_path))
    qapp.processEvents()
    text = hub._status_panel.status_text()
    assert "Proj" in text
    assert str(tmp_path) in text            # which project on disk
    assert "2" in text                      # replicate count
    assert "none loaded" in text            # no experiment yet

    hub._exp = _Exp()
    hub._refresh_tiles()
    assert "Rep1" in hub._status_panel.status_text()


def test_project_actions_use_three_columns(hub):
    grid = hub._project_actions_grid
    assert grid.columnCount() == 3
    # Five focused actions over three columns — no button spans the whole card.
    assert grid.count() == 5
    labels = [grid.itemAt(i).widget().text() for i in range(grid.count())]
    assert labels == [
        "Experiment configs…", "Add experiment…", "Create report",
        "Plot editor…", "AI narrative…",
    ]


def test_project_report_button_labels_create_or_update(hub, qapp, tmp_path):  # noqa: F811
    _make_project(tmp_path)
    hub._set_project_dir(str(tmp_path))
    qapp.processEvents()
    assert hub._btn_project_report.text() == "Create report"

    (tmp_path / "Proj_report.pdf").write_bytes(b"%PDF-")
    hub._refresh_project_view()
    assert hub._btn_project_report.text() == "Update report"


def test_project_report_button_runs_full_refresh(hub, tmp_path, monkeypatch):
    calls: list[str] = []

    class _Project:
        name = "Proj"
        project_directory = str(tmp_path)
        experiment_names = ["Rep1", "Rep2"]

        def run_all(self):
            calls.append("run_all")
            return []

        def build_combined_analysis(self):
            calls.append("combined")
            return {"written": ["a.csv", "b.txt"], "missing": []}

        def create_report(self):
            calls.append("report")
            return str(tmp_path / "Proj_report.pdf")

    spawned: list[tuple[str, str]] = []
    monkeypatch.setattr(hub, "_current_project", lambda: _Project())
    monkeypatch.setattr(
        hub, "_spawn_task",
        lambda name, fn: spawned.append((name, fn())),
    )

    hub._project_report()

    assert calls == ["run_all", "combined", "report"]
    assert spawned[0][0] == "Create report"
    assert "ran 2 replicate analyses" in spawned[0][1]
    assert "wrote Combined Analysis (2 files)" in spawned[0][1]


def test_project_ai_narrative_rebuilds_report(hub, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    class _Provider:
        provider_name = "testai"

    class _Project:
        def __init__(self):
            self.calls: list[tuple[str, str] | tuple[str]] = []

        def generate_ai_summary(self, provider):
            self.calls.append(("ai", provider))

        def create_report(self):
            self.calls.append(("report",))
            return str(tmp_path / "Proj_report.pdf")

    project = _Project()
    spawned: list[tuple[str, str]] = []
    monkeypatch.setattr("pytrackinganalysis.ai.available_providers",
                        lambda: [_Provider()])
    monkeypatch.setattr(
        QInputDialog, "getItem",
        staticmethod(lambda *a, **k: ("testai", True)),
    )
    monkeypatch.setattr(hub, "_current_project", lambda: project)
    monkeypatch.setattr(
        hub, "_spawn_task",
        lambda name, fn: spawned.append((name, fn())),
    )

    hub._project_ai_narrative()

    assert project.calls == [("ai", "testai"), ("report",)]
    assert spawned[0][0] == "AI narrative"
    assert "report rebuilt" in spawned[0][1]


def test_project_script_controls_stay_on_one_row(hub):
    from PyQt6.QtWidgets import QPushButton

    row = hub._project_script_row
    widgets = [row.itemAt(i).widget() for i in range(row.count())]
    assert hub._project_script_combo in widgets
    buttons = [w.text() for w in widgets if isinstance(w, QPushButton)]
    assert buttons == ["Run script", "Edit scripts…"]


def test_experiment_scripts_come_from_the_loaded_experiment(hub, qapp, tmp_path):  # noqa: F811
    """Experiment Scripts run against the loaded experiment, so that is where
    the list comes from — selecting the Project offers none."""
    from types import SimpleNamespace

    import yaml

    _make_project(tmp_path)
    cfg_path = tmp_path / "Rep1" / "tracking_config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["scripts"] = [{"name": "nightly", "steps": []}]
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    hub._set_project_dir(str(tmp_path))
    qapp.processEvents()
    assert hub._scripts_combo.count() == 0
    assert hub._tiles["scripts"].is_dimmed()
    assert "load" in hub._tiles["scripts"].summary_text()

    hub._exp = SimpleNamespace(
        project_directory=str(tmp_path / "Rep1"),
        arena=SimpleNamespace(experiment_name="Rep1"))
    hub._refresh_scripts()
    hub._refresh_tiles()
    assert hub._scripts_combo.count() == 1
    assert not hub._tiles["scripts"].is_dimmed()


def test_create_config_on_an_experiment_folder_targets_the_parent(
        hub, qapp, tmp_path, monkeypatch):  # noqa: F811
    """A project.yaml beside a tracking_config.yaml would be a Project with
    zero replicates — offer the parent, which is where it belongs."""
    from PyQt6.QtWidgets import QDialog, QMessageBox

    from pytrackinganalysis import project as prj
    from pytrackinganalysis.apps import hub as hub_mod

    exp_dir = tmp_path / "Solo"
    (exp_dir / "data").mkdir(parents=True)
    (exp_dir / "tracking_config.yaml").write_text("global: {}\n", encoding="utf-8")

    opened: list = []

    class _Dlg:
        def __init__(self, parent=None, start_dir=None):
            opened.append(start_dir)
            self.saved_dir = start_dir

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(hub_mod, "ProjectInfoDialog", _Dlg)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))

    hub._set_project_dir(str(exp_dir))
    qapp.processEvents()
    hub._btn_edit_cfg.click()

    assert prj.is_project_dir(tmp_path)
    assert not (exp_dir / "project.yaml").exists()
    assert opened == [str(tmp_path)]


def test_project_tile_shows_the_loaded_experiment(hub, qapp, tmp_path):  # noqa: F811
    """With the Experiment tile gone, the Project tile carries load status."""
    class _Arena:
        experiment_name = "Rep1"

    class _Exp:
        arena = _Arena()

    _make_project(tmp_path)
    hub._set_project_dir(str(tmp_path / "Rep1"))
    qapp.processEvents()
    assert "2 replicates" in hub._tiles["project"].summary_text()

    hub._exp = _Exp()
    hub._refresh_tiles()
    text = hub._tiles["project"].summary_text()
    assert "Proj" in text
    assert "Rep1" in text


def test_double_clicking_a_replicate_loads_it(hub, qapp, tmp_path, monkeypatch):  # noqa: F811
    """The replicates table is the only way in: one double-click loads."""
    _make_project(tmp_path)
    hub._set_project_dir(str(tmp_path))
    qapp.processEvents()
    loaded: list = []
    monkeypatch.setattr(type(hub), "_load_experiment",
                        lambda self, directory=None: loaded.append(str(directory)))

    row = next(r for r in range(hub._exp_table.rowCount())
               if hub._exp_table.item(r, 0).text() == "Rep2")
    hub._exp_table.itemDoubleClicked.emit(hub._exp_table.item(row, 0))

    assert loaded == [str(tmp_path / "Rep2")]
    # The row that was double-clicked is the load target; the selection is
    # still the Project, so its actions keep working on the whole set.
    assert str(hub._project_dir) == str(tmp_path)


def test_create_project_lives_on_the_project_card(hub):
    """Creating a Project is project-level work, not part of loading one."""
    from PyQt6.QtWidgets import QPushButton

    labels = [b.text() for b in hub._cards["project"].findChildren(QPushButton)]
    assert any("Create project" in t for t in labels)


def test_one_load_action_and_no_reload(hub, qapp, tmp_path, monkeypatch):  # noqa: F811
    """Reloading a project WAS browsing to it and opening it again, so the
    card offers the one action — and picking the open project re-reads it."""
    from PyQt6.QtWidgets import QFileDialog, QPushButton

    buttons = {b.text(): b for b in
               hub._cards["project"].findChildren(QPushButton)}
    assert "Load…" in buttons
    assert not [t for t in buttons if "Reload" in t or "Browse" in t]
    assert not hasattr(hub, "_reload_project")

    _make_project(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: str(tmp_path)))
    buttons["Load…"].click()
    qapp.processEvents()
    assert hub._project_dir == tmp_path
    assert hub._exp_table.rowCount() == 2      # the project was read

    # Clicking it again re-reads from disk: a replicate added outside the Hub
    # appears without any separate Reload.
    (tmp_path / "Rep3" / "data").mkdir(parents=True)
    (tmp_path / "Rep3" / "tracking_config.yaml").write_text(
        (tmp_path / "Rep1" / "tracking_config.yaml").read_text(),
        encoding="utf-8")
    buttons["Load…"].click()
    qapp.processEvents()
    assert hub._exp_table.rowCount() == 3


def test_project_panel_headers_are_distinct(hub):
    """The panel is already titled Project — its cards name their own jobs."""
    titles = [hub._cards[key]._title_lbl.text() for key in ("project", "projectview")]
    assert titles == ["Create/Load", "Analysis"]


def test_project_card_edits_project_yaml_not_tracking_configs(
        hub, qapp, tmp_path, monkeypatch):  # noqa: F811
    """Project card: no config dropdown / QC; Edit/Create opens project.yaml."""
    from PyQt6.QtWidgets import QComboBox, QDialog

    from pytrackinganalysis import project as prj
    from pytrackinganalysis.apps import hub as hub_mod

    card = hub._cards["project"]
    assert not any(isinstance(w, QComboBox) for w in card.findChildren(QComboBox))
    assert not any("QC" in b.text() for b in card.findChildren(type(hub._btn_edit_cfg)))

    # No project.yaml yet → Create config writes a default and opens the editor.
    hub._set_project_dir(str(tmp_path))
    qapp.processEvents()
    assert hub._btn_edit_cfg.text().startswith("Create")
    assert hub._btn_edit_cfg.isEnabled()
    opened: list[str] = []

    class _Dlg:
        def __init__(self, parent=None, start_dir=None):
            opened.append(start_dir)
            self.saved_dir = start_dir

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(hub_mod, "ProjectInfoDialog", _Dlg)
    hub._btn_edit_cfg.click()
    qapp.processEvents()
    assert prj.is_project_dir(tmp_path)
    assert opened == [str(tmp_path.resolve())]

    # Already a Project → Edit config opens the same editor, no rewrite needed.
    assert hub._btn_edit_cfg.text().startswith("Edit")
    opened.clear()
    before = (tmp_path / "project.yaml").read_text(encoding="utf-8")
    hub._btn_edit_cfg.click()
    assert opened == [str(tmp_path.resolve())]
    assert (tmp_path / "project.yaml").read_text(encoding="utf-8") == before
