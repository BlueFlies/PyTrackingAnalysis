"""Regressions for the Script Editor findings C4, C5/U7, U6, U8.

Everything here is hermetic: configs are built under ``tmp_path`` and Qt runs
under the offscreen platform plugin, as in ``tests/test_ui.py``.
"""

from __future__ import annotations

import os

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pytrackinganalysis.script_editor.runner import (  # noqa: E402
    ScriptError,
    load_scripts,
    save_scripts,
)


VALID_SCRIPT = {
    "name": "nightly",
    "steps": [
        {"action": "load_experiment", "params": {"path": "."}},
        {"action": "run_qc", "params": {}},
    ],
}


# --------------------------------------------------------------------------
# C4 — a malformed scripts: block must raise, not reach the widgets
# --------------------------------------------------------------------------

def _write_config(tmp_path, doc):
    path = tmp_path / "tracking_config.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def test_load_scripts_accepts_a_well_formed_block(tmp_path):
    path = _write_config(tmp_path, {"scripts": [VALID_SCRIPT]})
    assert load_scripts(path) == [VALID_SCRIPT]


def test_load_scripts_rejects_a_mapping_instead_of_a_list(tmp_path):
    """The old code returned ``['nightly']`` — the *keys* — and the widgets died."""
    path = _write_config(tmp_path, {"scripts": {"nightly": {"steps": []}}})
    with pytest.raises(ScriptError, match="must be a list"):
        load_scripts(path)


def test_load_scripts_rejects_string_steps(tmp_path):
    """``dict('run_qc')`` inside a Qt slot escalated to qFatal()/SIGABRT."""
    path = _write_config(tmp_path, {"scripts": [{"name": "n", "steps": ["run_qc"]}]})
    with pytest.raises(ScriptError) as err:
        load_scripts(path)
    assert "step 1" in str(err.value) and "run_qc" in str(err.value)


def test_load_scripts_rejects_a_non_mapping_entry(tmp_path):
    path = _write_config(tmp_path, {"scripts": ["nightly"]})
    with pytest.raises(ScriptError, match="entry 1"):
        load_scripts(path)


def test_load_scripts_rejects_non_mapping_params(tmp_path):
    path = _write_config(
        tmp_path, {"scripts": [{"name": "n", "steps": [{"action": "run_qc", "params": "x"}]}]}
    )
    with pytest.raises(ScriptError, match="'params:' must be a"):
        load_scripts(path)


def test_load_scripts_of_a_missing_file_is_empty(tmp_path):
    assert load_scripts(tmp_path / "nope.yaml") == []


# --------------------------------------------------------------------------
# C5 / U7 — atomic write, and comments survive a Script Editor save
# --------------------------------------------------------------------------

COMMENTED_CONFIG = """\
# Project configuration — hand-documented.
global:
  # millimetres per pixel, measured 2024-03-11
  mm_per_pixel: 0.0605
  tracking_type: TRACKER

scripts:
- name: old
  steps:
  - action: run_qc
    params: {}

# The region table follows.
tracking_regions:
  T_0:
    notes: broken tube   # keep me
"""


def _comment_lines(text):
    return [ln for ln in text.splitlines() if ln.lstrip().startswith("#")]


def test_saving_scripts_keeps_every_comment(tmp_path):
    path = tmp_path / "tracking_config.yaml"
    path.write_text(COMMENTED_CONFIG, encoding="utf-8")
    before = _comment_lines(path.read_text(encoding="utf-8"))

    save_scripts(path, [VALID_SCRIPT])

    after_text = path.read_text(encoding="utf-8")
    assert _comment_lines(after_text) == before
    assert "# keep me" in after_text
    assert load_scripts(path) == [VALID_SCRIPT]


def test_saving_scripts_keeps_every_other_section_byte_identical(tmp_path):
    path = tmp_path / "tracking_config.yaml"
    path.write_text(COMMENTED_CONFIG, encoding="utf-8")

    save_scripts(path, [VALID_SCRIPT])

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["global"] == {"mm_per_pixel": 0.0605, "tracking_type": "TRACKER"}
    assert doc["tracking_regions"] == {"T_0": {"notes": "broken tube"}}


def test_deleting_the_last_script_removes_the_block_and_keeps_comments(tmp_path):
    path = tmp_path / "tracking_config.yaml"
    path.write_text(COMMENTED_CONFIG, encoding="utf-8")

    save_scripts(path, [])

    text = path.read_text(encoding="utf-8")
    assert "scripts:" not in text
    assert "# The region table follows." in text
    assert yaml.safe_load(text)["tracking_regions"] == {"T_0": {"notes": "broken tube"}}


def test_saving_into_a_config_without_a_scripts_block_appends_it(tmp_path):
    path = tmp_path / "tracking_config.yaml"
    path.write_text("# header\nglobal:\n  tracking_type: TRACKER  # trailing\n",
                    encoding="utf-8")

    save_scripts(path, [VALID_SCRIPT])

    text = path.read_text(encoding="utf-8")
    assert "# header" in text and "# trailing" in text
    assert load_scripts(path) == [VALID_SCRIPT]


def test_save_goes_through_the_atomic_write_helper(tmp_path, monkeypatch):
    from pytrackinganalysis import io_utils

    path = tmp_path / "tracking_config.yaml"
    path.write_text(COMMENTED_CONFIG, encoding="utf-8")

    calls = []
    real = io_utils.atomic_write_text
    monkeypatch.setattr(
        io_utils, "atomic_write_text",
        lambda p, render, **kw: (calls.append(p), real(p, render, **kw))[1],
    )
    save_scripts(path, [VALID_SCRIPT])
    assert calls == [path]


def test_an_interrupted_save_leaves_the_original_config_intact(tmp_path, monkeypatch):
    """The old truncate-then-write left an unparseable stub and no backup."""
    from pytrackinganalysis import io_utils

    path = tmp_path / "tracking_config.yaml"
    path.write_text(COMMENTED_CONFIG, encoding="utf-8")

    def boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(io_utils.os, "replace", boom)
    with pytest.raises(OSError):
        save_scripts(path, [VALID_SCRIPT])

    assert path.read_text(encoding="utf-8") == COMMENTED_CONFIG
    assert [p.name for p in tmp_path.iterdir()] == ["tracking_config.yaml"]


# --------------------------------------------------------------------------
# Qt-dependent regressions
# --------------------------------------------------------------------------

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as err:  # noqa: BLE001
            pytest.skip(f"Qt is unavailable: {err}")
    return app


# --------------------------------------------------------------------------
# U8 — card/step index desynchronisation on an unknown action
# --------------------------------------------------------------------------

MIXED_STEPS = [
    {"action": "run_qc", "params": {}},
    {"action": "totally_bogus", "params": {}},
    {"action": "summarize", "params": {}},
]


def test_an_unknown_action_still_gets_a_card(qapp):
    from pytrackinganalysis.script_editor.canvas import Canvas

    canvas = Canvas()
    canvas.load_steps(MIXED_STEPS)
    assert len(canvas._cards) == len(canvas._steps) == 3


def test_selecting_a_card_after_an_unknown_action_opens_the_right_step(qapp):
    from pytrackinganalysis.script_editor.canvas import Canvas

    canvas = Canvas()
    canvas.load_steps(MIXED_STEPS)
    canvas._on_card_selected(2)
    assert canvas.current_step()["action"] == "summarize"


def test_removing_the_unknown_step_removes_that_step_only(qapp):
    from pytrackinganalysis.script_editor.canvas import Canvas

    canvas = Canvas()
    canvas.load_steps(MIXED_STEPS)
    canvas._remove_at(1)
    assert [s["action"] for s in canvas.steps()] == ["run_qc", "summarize"]
    assert len(canvas._cards) == 2


def test_moving_a_step_past_an_unknown_action_keeps_the_lists_aligned(qapp):
    from pytrackinganalysis.script_editor.canvas import Canvas

    canvas = Canvas()
    canvas.load_steps(MIXED_STEPS)
    canvas._move(2, -1)
    assert [s["action"] for s in canvas.steps()] == ["run_qc", "summarize", "totally_bogus"]
    assert len(canvas._cards) == 3


# --------------------------------------------------------------------------
# U6 — an invalid recipe must not reach disk behind a "Saved" dialog
# --------------------------------------------------------------------------

INVALID_SCRIPT = {
    "name": "bad",
    # 99.0 is far outside the action's 0..1 range; it never passes through a
    # spin box, so only a save-time gate can catch it.
    "steps": [{"action": "filter_by_quality", "params": {"min_high_quality": 99.0}}],
}


@pytest.fixture
def script_dialogs(monkeypatch):
    from pytrackinganalysis.script_editor import window as win

    seen = {"information": [], "warning": [], "critical": []}
    for kind in seen:
        monkeypatch.setattr(
            win.QMessageBox, kind,
            lambda *args, _kind=kind, **kwargs: seen[_kind].append(args),
        )
    return seen


def _editor(path, qapp):
    from pytrackinganalysis.script_editor.window import ScriptEditorWindow

    return ScriptEditorWindow(str(path))


def test_saving_an_invalid_step_is_refused_and_reported(qapp, tmp_path, script_dialogs):
    path = _write_config(tmp_path, {"global": {"tracking_type": "TRACKER"},
                                    "scripts": [INVALID_SCRIPT]})
    original = path.read_text(encoding="utf-8")
    window = _editor(path, qapp)
    try:
        assert window.script_validation_errors()
        window._save()

        assert script_dialogs["warning"], "the user must be told why nothing was saved"
        assert not script_dialogs["information"], "no 'Saved' dialog for a refused save"
        assert path.read_text(encoding="utf-8") == original
    finally:
        window.close()


def test_saving_a_valid_script_still_works(qapp, tmp_path, script_dialogs):
    path = _write_config(tmp_path, {"global": {"tracking_type": "TRACKER"},
                                    "scripts": [VALID_SCRIPT]})
    window = _editor(path, qapp)
    try:
        assert window.script_validation_errors() == []
        window._save()

        assert not script_dialogs["warning"]
        assert script_dialogs["information"]
        assert load_scripts(path) == [VALID_SCRIPT]
    finally:
        window.close()


# --------------------------------------------------------------------------
# actions.filter_by_region — region ids without an underscore
# --------------------------------------------------------------------------

class _FakeArena:
    def __init__(self, trackers):
        self.trackers = trackers

    def set_trackers(self, trackers):
        self.trackers = trackers


class _FakeTracker:
    def __init__(self, region_id):
        self.tracking_region_id = region_id


def _run_filter(regions, trackers, tmp_path):
    from pytrackinganalysis.script_editor.actions import RunContext, _exec_filter_by_region

    arena = _FakeArena(dict(trackers))
    exp = type("_Exp", (), {"arena": arena})()
    ctx = RunContext(project_dir=tmp_path, exp=exp, log=lambda _m: None)
    _exec_filter_by_region({"regions": regions}, ctx)
    return arena.trackers


def test_filter_by_region_handles_ids_without_an_underscore(tmp_path):
    """``'Chamber'.split('_')[1]`` used to raise IndexError and kill the run."""
    kept = _run_filter(
        "Chamber",
        {"Chamber": _FakeTracker("Chamber"), "Other": _FakeTracker("Other")},
        tmp_path,
    )
    assert list(kept) == ["Chamber"]


def test_filter_by_region_still_matches_the_conventional_prefix(tmp_path):
    kept = _run_filter(
        "T_0",
        {"T_0_1": _FakeTracker("T_0_1"), "T_1_0": _FakeTracker("T_1_0")},
        tmp_path,
    )
    assert list(kept) == ["T_0_1"]


# ---- palette tile sizing ---------------------------------------------------

def _clipped_labels(palette):
    """Tiles whose wrapped text does not fit the height it was given.

    ``QLabel.heightForWidth`` is the authoritative figure: a label narrower
    than its text needs wraps to more lines, and anything shorter than that
    is cut off — at the top and bottom, since the label is centred.
    """
    return [(tile._action.key, label.height(), label.heightForWidth(label.width()))
            for tile in palette._tiles
            for label in (tile._title_lbl, tile._desc_lbl)
            if label.height() < label.heightForWidth(label.width())]


@pytest.mark.parametrize("width", [160, 240, 320, 500])
def test_palette_tiles_show_their_whole_description(qapp, width):
    """Neither a QBoxLayout nor a QGridLayout applies a word-wrapped label's
    heightForWidth when assigning geometry, so the tile measures and pins the
    labels itself. Without that the descriptions were clipped top and bottom
    — worse the narrower the pane, because narrower means more wrapped lines.
    """
    from pytrackinganalysis.script_editor.palette import Palette
    from pytrackinganalysis.script_editor.project_actions import PROJECT_ACTIONS

    palette = Palette()
    palette.set_actions(PROJECT_ACTIONS)
    palette.show()
    palette.resize(width, 900)
    for _ in range(4):
        qapp.processEvents()

    assert palette._tiles
    assert _clipped_labels(palette) == []
    # Each tile is tall enough to hold both labels plus its margins.
    for tile in palette._tiles:
        assert tile.height() >= tile._title_lbl.height() + tile._desc_lbl.height()
    palette.close()


def test_palette_tiles_regrow_when_the_pane_narrows(qapp):
    """Narrowing rewraps the text onto more lines; the tile must follow."""
    from pytrackinganalysis.script_editor.palette import Palette
    from pytrackinganalysis.script_editor.project_actions import PROJECT_ACTIONS

    palette = Palette()
    palette.set_actions(PROJECT_ACTIONS)
    palette.show()
    palette.resize(460, 900)
    for _ in range(4):
        qapp.processEvents()
    wide = [t.height() for t in palette._tiles]

    palette.resize(170, 900)
    for _ in range(4):
        qapp.processEvents()
    narrow = [t.height() for t in palette._tiles]

    assert _clipped_labels(palette) == []
    assert any(n > w for n, w in zip(narrow, wide)), (wide, narrow)
    palette.close()
