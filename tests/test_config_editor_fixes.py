"""Regressions for the Config Editor's data-loss bugs (C1–C5, U6, U7).

Every test here pins a way the editor used to destroy something the user had
already saved: a script written by the Script Editor, a fractional facet
cutoff, a deleted region table, a hand-added per-region key, a re-calibration,
or — on an interrupted write — the whole file.

Qt runs under the offscreen platform plugin; the module is skipped when a
QApplication cannot be created.
"""

from __future__ import annotations

import os

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as err:  # noqa: BLE001
            pytest.skip(f"Qt is unavailable: {err}")
    return app


# A project with something to lose in every one of the affected places.
CONFIG = {
    "global": {
        "tracking_type": "TRACKER",
        "tracking_rig": "small_arena",
        "mm_per_pixel": 0.0605,          # a deliberate re-calibration (U6)
        "facet_cutoffs": [10, 70],       # C2
        "experimental_design_factors": {
            "Diet": ["Starved", "Fed"],
            "Sex": ["Female", "Male"],
        },
        "custom_lab_note": "keep me",
    },
    "tracking_regions": {
        "T_0": {
            "experimental_factors": "Starved, Female, Batch1",  # Batch1 undeclared (U7)
            "x_location_multiplier": 1,
            "y_location_multiplier": -1,
            "notes": "broken tube",                            # unknown key (U7)
        },
        "T_1": {
            "experimental_factors": "Fed, Male",
            "x_location_multiplier": 1,
            "y_location_multiplier": 1,
        },
    },
    "counting_regions": {
        "Light": {"alias": "Light, LL, L", "color": "yellow"},  # unknown key (U7)
        "NoLight": {"alias": "NoLight, N"},
    },
    "scripts": [
        {"name": "nightly", "steps": [{"action": "load_experiment", "params": {"path": "."}}]}
    ],
}


@pytest.fixture
def dialogs(monkeypatch):
    """Capture the editor's modal dialogs — they would block a headless run."""
    from pytrackinganalysis.apps import config_editor as ce

    seen: dict[str, list] = {"information": [], "warning": [], "critical": []}
    for kind in seen:
        monkeypatch.setattr(
            ce.QMessageBox, kind,
            lambda *args, _kind=kind, **kwargs: seen[_kind].append(args),
        )
    return seen


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "tracking_config.yaml"
    path.write_text(yaml.safe_dump(CONFIG, sort_keys=False))
    return path


@pytest.fixture
def editor(qapp, config_path, dialogs):
    from pytrackinganalysis.apps.config_editor import ConfigEditorWindow

    window = ConfigEditorWindow(str(config_path))
    yield window
    window.close()


class FakeScriptEditor(QMainWindow):
    """Stand-in for ScriptEditorWindow with the same construction signature."""

    scriptsSaved = pyqtSignal(str)
    raised = 0

    def __init__(self, config_path, parent=None):
        super().__init__(parent)
        self._config_path = config_path

    def raise_(self):  # noqa: D102 — count focus requests instead of showing
        type(self).raised += 1


@pytest.fixture
def fake_script_editor(monkeypatch):
    from pytrackinganalysis.script_editor import window as se_window

    FakeScriptEditor.raised = 0
    monkeypatch.setattr(se_window, "ScriptEditorWindow", FakeScriptEditor)
    return FakeScriptEditor


# ==========================================================================
# C1 — a Save must not delete the scripts the Script Editor just wrote
# ==========================================================================

def test_external_script_write_is_picked_up_before_the_next_save(editor, config_path):
    """_loaded_config was a load-time snapshot, so Save reverted the child's write."""
    on_disk = yaml.safe_load(config_path.read_text())
    on_disk["scripts"] = [{"name": "batch", "steps": [{"action": "run_qc", "params": {}}]}]
    config_path.write_text(yaml.safe_dump(on_disk, sort_keys=False))

    editor._reload_external_changes(str(config_path))

    assert editor._dump_config()["scripts"] == on_disk["scripts"]


def test_reload_does_not_resurrect_a_section_the_child_removed(editor, config_path):
    on_disk = yaml.safe_load(config_path.read_text())
    del on_disk["scripts"]
    config_path.write_text(yaml.safe_dump(on_disk, sort_keys=False))

    editor._reload_external_changes(str(config_path))

    assert "scripts" not in editor._dump_config()


def test_reload_leaves_the_sections_this_window_owns_alone(editor, config_path):
    """The child must not be able to stomp unsaved edits in our own tabs."""
    editor._counting_tab.table.setRowCount(0)
    editor._reload_external_changes(str(config_path))

    assert editor._counting_tab.table.rowCount() == 0
    assert "counting_regions" not in editor._dump_config()


def test_launching_the_script_editor_wires_up_scripts_saved(editor, config_path,
                                                            fake_script_editor):
    """scriptsSaved existed but was connected nowhere."""
    editor._launch_script_editor()

    on_disk = yaml.safe_load(config_path.read_text())
    on_disk["scripts"] = [{"name": "from-child", "steps": []}]
    config_path.write_text(yaml.safe_dump(on_disk, sort_keys=False))
    editor._script_editor.scriptsSaved.emit(str(config_path))

    assert editor._dump_config()["scripts"] == on_disk["scripts"]


def test_only_one_script_editor_is_ever_opened(editor, fake_script_editor):
    """Two windows would each hold a snapshot of the same file; last writer won."""
    editor._launch_script_editor()
    first = editor._script_editor
    editor._launch_script_editor()

    assert editor._script_editor is first
    assert fake_script_editor.raised == 1, "the existing window was not focused"


# ==========================================================================
# C4 — a malformed scripts: block must not kill the application
# ==========================================================================

def test_a_script_editor_that_fails_to_construct_is_reported_not_fatal(
    editor, dialogs, monkeypatch
):
    """The try block wrapped only the import, so __init__ raised inside a Qt slot."""
    from pytrackinganalysis.script_editor import window as se_window

    class Exploding(QMainWindow):
        scriptsSaved = pyqtSignal(str)

        def __init__(self, config_path, parent=None):
            raise ValueError("'scripts:' must be a list of {name, steps} mappings")

    monkeypatch.setattr(se_window, "ScriptEditorWindow", Exploding)

    editor._launch_script_editor()  # must not raise

    assert dialogs["critical"], "the user was not told why the editor would not open"
    assert editor._script_editor is None


# ==========================================================================
# C2 — a fractional facet cutoff must be rejected, never silently deleted
# ==========================================================================

def test_a_fractional_facet_cutoff_is_a_validation_error(editor):
    editor._global_tab.facet_cutoffs.setText("10.5, 70")
    errors = " | ".join(editor._global_tab.validation_errors())
    assert "Facet cutoffs" in errors and "whole minutes" in errors


def test_a_fractional_facet_cutoff_blocks_the_save_instead_of_dropping_the_key(
    editor, config_path, dialogs
):
    editor._global_tab.facet_cutoffs.setText("10.5, 70")
    editor._save()

    assert dialogs["warning"], "the user was told nothing"
    assert not dialogs["information"], "the editor claimed it saved"
    assert yaml.safe_load(config_path.read_text())["global"]["facet_cutoffs"] == [10, 70]


def test_whole_minute_cutoffs_still_round_trip(editor, config_path):
    editor._global_tab.facet_cutoffs.setText("5, 15, 30")
    editor._save()
    assert yaml.safe_load(config_path.read_text())["global"]["facet_cutoffs"] == [5, 15, 30]


def test_facet_labels_round_trip(editor, config_path):
    editor._global_tab.facet_labels.setText("Warmup, Assay, Rest")
    editor._save()
    g = yaml.safe_load(config_path.read_text())["global"]
    assert g["facet_labels"] == ["Warmup", "Assay", "Rest"]


def test_mismatched_facet_labels_block_the_save(editor, config_path, dialogs):
    # Two cutoffs = three phases; two names cannot label them.
    editor._global_tab.facet_labels.setText("Warmup, Assay")
    editor._save()
    assert dialogs["warning"], "the user was told nothing"
    assert "facet_labels" not in yaml.safe_load(config_path.read_text())["global"]


def test_facet_labels_field_follows_the_faceting_checkbox(editor):
    tab = editor._global_tab
    assert tab.use_facets.isChecked() and tab.facet_labels.isEnabled()
    tab.use_facets.setChecked(False)
    assert not tab.facet_labels.isEnabled()
    tab.use_facets.setChecked(True)
    assert tab.facet_labels.isEnabled()


# ==========================================================================
# C3 — clearing a region table must actually clear it on disk
# ==========================================================================

@pytest.mark.parametrize("tab_attr, section", [
    ("_tracking_tab", "tracking_regions"),
    ("_counting_tab", "counting_regions"),
])
def test_deleting_every_region_is_not_reverted_on_save(editor, config_path,
                                                       tab_attr, section):
    """dump() returned {} and config.update({}) is a no-op, so the old plate came back."""
    getattr(editor, tab_attr).table.setRowCount(0)
    editor._save()

    reloaded = yaml.safe_load(config_path.read_text())
    assert not reloaded.get(section), f"{section} was resurrected from the load-time snapshot"


def test_deleting_every_region_shows_the_unsaved_indicator(editor):
    """The output used to be byte-identical to disk, so nothing flagged the loss."""
    assert editor._dirty_label.text() == ""
    editor._tracking_tab.table.setRowCount(0)
    editor._refresh_dirty()
    assert editor._dirty_label.text() != ""


def test_clearing_one_table_leaves_the_other_alone(editor, config_path):
    editor._tracking_tab.table.setRowCount(0)
    editor._save()

    reloaded = yaml.safe_load(config_path.read_text())
    assert set(reloaded["counting_regions"]) == {"Light", "NoLight"}


# ==========================================================================
# C5 — an interrupted write must leave the original file intact
# ==========================================================================

def test_an_interrupted_save_does_not_destroy_the_config(editor, config_path,
                                                         dialogs, monkeypatch):
    from pytrackinganalysis.apps import config_editor as ce

    before = config_path.read_text()

    def boom(*_args, **_kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(ce.yaml, "dump", boom)
    editor._save()

    assert config_path.read_text() == before, "the user's only copy was truncated"
    assert yaml.safe_load(config_path.read_text())["scripts"] == CONFIG["scripts"]
    assert dialogs["critical"], "the failure was not reported"
    leftovers = [p.name for p in config_path.parent.iterdir() if p.name != config_path.name]
    assert leftovers == [], f"temp files left behind: {leftovers}"


# ==========================================================================
# U6 — changing the rig must not erase a re-calibration
# ==========================================================================

def test_changing_the_rig_keeps_a_calibration_that_came_from_the_file(editor,
                                                                     config_path):
    from pytrackinganalysis.apps._config_tabs import TRACKING_RIGS

    assert editor._global_tab.mm_per_pixel.text() == "0.0605"

    index = [value for _, value in TRACKING_RIGS].index("obscura")
    editor._global_tab.tracking_rig.setCurrentIndex(index)

    assert editor._global_tab.mm_per_pixel.text() == "0.0605"
    editor._save()
    assert yaml.safe_load(config_path.read_text())["global"]["mm_per_pixel"] == 0.0605


def test_changing_the_rig_keeps_a_calibration_the_user_typed(editor):
    from PyQt6.QtTest import QTest

    from pytrackinganalysis.apps._config_tabs import TRACKING_RIGS

    rigs = [value for _, value in TRACKING_RIGS]
    editor._global_tab.tracking_rig.setCurrentIndex(rigs.index("movie"))
    editor._global_tab.fps.clear()
    QTest.keyClicks(editor._global_tab.fps, "29.97")

    editor._global_tab.tracking_rig.setCurrentIndex(rigs.index("small_arena"))

    assert editor._global_tab.fps.text() == "29.97"
    assert editor._global_tab.fps.isEnabled(), "the override cannot be revised or removed"


def test_an_untouched_calibration_field_still_follows_the_rig(qapp):
    """Nothing was typed and nothing was loaded — there is no override to protect."""
    from pytrackinganalysis.apps._config_tabs import TRACKING_RIGS, GlobalTab

    tab = GlobalTab()
    rigs = [value for _, value in TRACKING_RIGS]
    tab.tracking_rig.setCurrentIndex(rigs.index("movie"))
    tab.fps.setText("60")  # programmatic, not user input
    tab.tracking_rig.setCurrentIndex(rigs.index("colosseum"))

    assert tab.fps.text() == ""
    assert not tab.fps.isEnabled()


# ==========================================================================
# U7 — unknown per-region keys and undeclared factor tokens must survive
# ==========================================================================

def test_round_trip_preserves_unknown_tracking_region_keys(editor, config_path):
    editor._save()
    reloaded = yaml.safe_load(config_path.read_text())
    assert reloaded["tracking_regions"]["T_0"]["notes"] == "broken tube"


def test_round_trip_preserves_unknown_counting_region_keys(editor, config_path):
    editor._save()
    reloaded = yaml.safe_load(config_path.read_text())
    assert reloaded["counting_regions"]["Light"]["color"] == "yellow"


def test_round_trip_preserves_undeclared_factor_tokens(editor, config_path):
    """'Starved, Female, Batch1' used to come back as 'Starved, Female'."""
    editor._save()
    reloaded = yaml.safe_load(config_path.read_text())
    assert reloaded["tracking_regions"]["T_0"]["experimental_factors"] == \
        "Starved, Female, Batch1"


def test_undeclared_tokens_survive_a_factor_column_rebuild(editor, config_path):
    """Editing the Global factors re-creates every region row from a snapshot."""
    editor._global_tab.factors_table.item(1, 1).setText("Female, Male, Other")
    editor._save()

    reloaded = yaml.safe_load(config_path.read_text())
    assert "Batch1" in reloaded["tracking_regions"]["T_0"]["experimental_factors"]


def test_the_keys_the_tabs_do_own_are_still_written(editor, config_path):
    """Preservation must not turn into 'never update anything'."""
    editor._tracking_tab.table.cellWidget(0, editor._tracking_tab._y_col()).setCurrentText("1")
    editor._counting_tab.table.item(0, 1).setText("Light, LL")
    editor._save()

    reloaded = yaml.safe_load(config_path.read_text())
    assert reloaded["tracking_regions"]["T_0"]["y_location_multiplier"] == 1
    assert reloaded["counting_regions"]["Light"]["alias"] == "Light, LL"
    assert reloaded["counting_regions"]["Light"]["color"] == "yellow"


def test_a_renamed_region_does_not_inherit_the_old_one_s_extra_keys(editor, config_path):
    editor._tracking_tab.table.item(0, 0).setText("T_9")
    editor._save()

    regions = yaml.safe_load(config_path.read_text())["tracking_regions"]
    assert "T_0" not in regions
    assert "notes" not in regions["T_9"]
