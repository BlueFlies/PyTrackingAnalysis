"""Tests for the Hub tile-strip redesign (ADR-0007): the strip's six tiles,
their live summaries and dimming across loading states, the anchored panels
(open/close/one-at-a-time/auto-close-on-launch), and the sidebar's
open-the-panel behavior."""

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


TILE_ORDER = ["project", "experiment", "analyze", "plots", "scripts", "ai"]


def test_strip_has_six_fixed_tiles_and_full_width_output(hub):
    assert list(hub._tiles) == TILE_ORDER
    assert "tools" not in hub._tiles          # sidebar-only
    assert "tools" in hub._panels             # …but it still has a panel
    # The output dock owns the full width under the strip (no card column).
    assert hub._plot_dock.width() > hub.width() - 300


def test_tiles_dim_with_hints_when_nothing_is_loaded(hub):
    assert hub._tiles["project"].is_dimmed()
    assert "no project" in hub._tiles["project"].summary_text()
    assert hub._tiles["experiment"].is_dimmed()
    assert hub._tiles["analyze"].is_dimmed()


def test_project_and_experiment_tiles_reflect_state(hub, qapp, tmp_path):  # noqa: F811
    _make_project(tmp_path)
    hub._set_project_dir(str(tmp_path))
    qapp.processEvents()
    tile = hub._tiles["project"]
    assert not tile.is_dimmed()
    assert "Proj" in tile.summary_text()
    assert "2 replicates" in tile.summary_text()
    # Experiment tile: dimmed with the drill-in hint while at project level.
    assert hub._tiles["experiment"].is_dimmed()
    assert "replicate" in hub._tiles["experiment"].summary_text()

    # Drilling into a replicate keeps the project tile lit (effective root).
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


def test_sidebar_items_open_matching_panels(hub):
    hub._open_panel_for_sidebar("load")       # sidebar key -> experiment panel
    assert hub._open_panel_key == "experiment"
    hub._open_panel_for_sidebar("tools")      # sidebar-only panel, no tile
    assert hub._open_panel_key == "tools"
    assert hub._panels["tools"].isVisible()
    hub._close_panel()


def test_launching_a_task_closes_the_open_panel(hub, qapp):
    import time

    hub._open_panel("analyze")
    assert hub._panels["analyze"].isVisible()
    hub._spawn_task("noop", lambda: "done")
    assert hub._open_panel_key is None        # closed at launch, not at finish
    deadline = time.monotonic() + 10
    while hub._worker is not None and time.monotonic() < deadline:
        qapp.processEvents()
    assert hub._worker is None


def test_cards_live_inside_panels_and_stay_functional(hub):
    # The full existing cards moved into panels — handlers and widgets intact.
    project_panel = hub._panels["project"]
    assert hub._cards["project"] in project_panel.findChildren(type(hub._cards["project"]))
    assert hub._cards["projectview"] in project_panel.findChildren(type(hub._cards["projectview"]))
    assert hub._cards["load"] in hub._panels["experiment"].findChildren(type(hub._cards["load"]))
    # The replicates table is reachable exactly as before.
    assert hub._exp_table.parent() is not None


def test_tile_summary_lines_are_hard_capped(hub):
    tile = hub._tiles["project"]
    tile.set_summary(["x" * 100, "y" * 100, "third line is dropped"])
    text = tile.summary_text()
    assert all(len(line) <= 26 for line in text.splitlines())
    assert len(text.splitlines()) == 2
