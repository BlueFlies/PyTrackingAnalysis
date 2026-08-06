"""UI-layer regressions that can be checked headlessly.

Qt runs under the offscreen platform plugin; the whole module is skipped when a
QApplication cannot be created (no Qt libs in the environment).
"""

from __future__ import annotations

import os

import pandas as pd
import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt  # noqa: E402
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
# Config Editor round trip
# --------------------------------------------------------------------------

CONFIG_WITH_EXTRAS = {
    "global": {
        "tracking_type": "TRACKER",
        "tracking_rig": "small_arena",
        "facet_cutoffs": [10, 70],
        # A key the Global tab does not render.
        "custom_lab_note": "keep me",
    },
    "tracking_regions": {"T_1": {"experimental_factors": "Ctrl"}},
    # A whole top-level section the editor has no tab for.
    "scripts": [
        {"name": "nightly", "steps": [{"action": "load_experiment", "params": {"path": "."}}]}
    ],
    "some_future_section": {"a": 1},
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
    # A modal question() (e.g. the "seed required regions?" prompt) would block a
    # headless run forever. Default to "No" so nothing is auto-inserted.
    monkeypatch.setattr(
        ce.QMessageBox, "question",
        lambda *args, **kwargs: ce.QMessageBox.StandardButton.No,
    )
    return seen


@pytest.fixture
def editor(qapp, tmp_path, dialogs):
    from pytrackinganalysis.apps.config_editor import ConfigEditorWindow

    path = tmp_path / "tracking_config.yaml"
    path.write_text(yaml.safe_dump(CONFIG_WITH_EXTRAS, sort_keys=False))
    window = ConfigEditorWindow(str(path))
    yield window
    window.close()


def test_saving_preserves_the_scripts_section(editor):
    """Rebuilding the file from the three visible tabs used to delete scripts:."""
    dumped = editor._dump_config()
    assert dumped["scripts"] == CONFIG_WITH_EXTRAS["scripts"]


def test_saving_preserves_unknown_top_level_sections(editor):
    assert editor._dump_config()["some_future_section"] == {"a": 1}


def test_saving_preserves_unknown_global_keys(editor):
    assert editor._dump_config()["global"]["custom_lab_note"] == "keep me"


def test_saving_still_writes_the_edited_sections(editor):
    dumped = editor._dump_config()
    assert dumped["global"]["tracking_type"] == "TRACKER"
    assert "tracking_regions" in dumped


def test_a_full_write_round_trip_keeps_everything(editor, tmp_path):
    out = tmp_path / "written.yaml"
    editor._write(out)
    reloaded = yaml.safe_load(out.read_text())
    assert reloaded["scripts"] == CONFIG_WITH_EXTRAS["scripts"]
    assert reloaded["global"]["custom_lab_note"] == "keep me"


def test_an_invalid_number_blocks_the_save(editor, tmp_path, dialogs):
    """A bad value used to be dropped silently, leaving the analysis on defaults."""
    editor._global_tab.mm_per_pixel.setText("not-a-number")
    out = tmp_path / "blocked.yaml"
    editor._write(out)

    assert dialogs["warning"], "the user was not told the value was rejected"
    assert not out.exists(), "an invalid config was written to disk"


def test_movie_rig_without_calibration_is_flagged(editor):
    from pytrackinganalysis.apps._config_tabs import TRACKING_RIGS

    index = [value for _, value in TRACKING_RIGS].index("movie")
    editor._global_tab.tracking_rig.setCurrentIndex(index)
    editor._global_tab.fps.setText("")
    editor._global_tab.mm_per_pixel.setText("")
    errors = " | ".join(editor._global_tab.validation_errors())
    assert "FPS" in errors and "mm per pixel" in errors


# --------------------------------------------------------------------------
# Experiment Type UI (Phase 5)
# --------------------------------------------------------------------------

def _select_experiment_type(tab, name):
    from pytrackinganalysis.apps._config_tabs import _find_data
    tab.experiment_type.setCurrentIndex(_find_data(tab.experiment_type, name))


def test_global_tab_defaults_to_custom_and_is_unconstrained(qapp):
    from pytrackinganalysis.apps._config_tabs import GlobalTab, TRACKING_RIGS
    tab = GlobalTab()
    assert tab.current_experiment_type().is_custom
    assert tab.tracking_type.isEnabled()          # editable for Custom
    # Full rig list available for Custom.
    assert tab.tracking_rig.count() == len(TRACKING_RIGS)


def test_selecting_valence_locks_owned_fields_and_constrains_rig(qapp):
    from pytrackinganalysis.apps._config_tabs import GlobalTab
    tab = GlobalTab()
    _select_experiment_type(tab, "Valence")
    # Tracking type fixed + disabled.
    assert tab.tracking_type.currentData() == "TWOCHOICETRACKER"
    assert not tab.tracking_type.isEnabled()
    # Rig constrained to Max/Colosseum.
    rigs = {tab.tracking_rig.itemData(i) for i in range(tab.tracking_rig.count())}
    assert rigs == {"arena_max", "colosseum"}
    # Facets fixed + disabled; calibration disabled.
    assert tab.facet_cutoffs.text().replace(" ", "") == "10,70"
    assert not tab.facet_cutoffs.isEnabled()
    assert not tab.fps.isEnabled() and not tab.mm_per_pixel.isEnabled()


def test_valence_dump_is_minimal_and_omits_owned_fields(qapp):
    from pytrackinganalysis.apps._config_tabs import GlobalTab, _find_data
    tab = GlobalTab()
    _select_experiment_type(tab, "Valence")
    tab.tracking_rig.setCurrentIndex(_find_data(tab.tracking_rig, "colosseum"))
    g = tab.dump()["global"]
    assert g["experiment_type"] == "Valence"
    assert g["tracking_rig"] == "colosseum"
    # Owned/derived fields must NOT be written to disk (ADR-0001).
    assert "tracking_type" not in g
    assert "facet_cutoffs" not in g
    assert "fps" not in g and "mm_per_pixel" not in g


def test_custom_dump_has_no_experiment_type_key(qapp):
    from pytrackinganalysis.apps._config_tabs import GlobalTab
    tab = GlobalTab()  # defaults to Custom
    g = tab.dump()["global"]
    assert "experiment_type" not in g          # absence == Custom (back-compat)
    assert g["tracking_type"] == "TRACKER"


def test_load_then_dump_round_trips_a_valence_config(qapp):
    from pytrackinganalysis.apps._config_tabs import GlobalTab
    tab = GlobalTab()
    tab.load({"global": {"experiment_type": "Valence", "tracking_rig": "arena_max"}})
    assert tab.current_experiment_type().name == "Valence"
    assert tab.tracking_rig.currentData() == "arena_max"
    g = tab.dump()["global"]
    assert g["experiment_type"] == "Valence" and g["tracking_rig"] == "arena_max"
    assert "tracking_type" not in g


def test_editor_blocks_saving_an_incomplete_valence_config(editor, tmp_path, dialogs):
    # Switch to Valence but leave counting regions as the loaded Custom set
    # (which are not Light/NoLight) -> save must be refused.
    _select_experiment_type(editor._global_tab, "Valence")
    out = tmp_path / "bad_valence.yaml"
    editor._write(out)
    assert dialogs["warning"], "an invalid typed config was allowed through"
    assert not out.exists()


def test_scaffold_project_creates_a_shaped_incomplete_valence_project(qapp, tmp_path):
    from pytrackinganalysis.apps.config_editor import ConfigEditorWindow
    from pytrackinganalysis import config_validation

    config_path = ConfigEditorWindow.scaffold_project(tmp_path, "MyValence", "Valence")
    project = config_path.parent
    assert (project / "data").is_dir()
    assert (project / "analysis").is_dir() and (project / "qc").is_dir()

    cfg = yaml.safe_load(config_path.read_text())
    assert cfg["global"]["experiment_type"] == "Valence"
    assert list(cfg["counting_regions"]) == ["Light", "NoLight"]
    # Intentionally incomplete: rig is blank, so it does not yet validate.
    problems = config_validation.validate_config(cfg)
    assert any("tracking_rig" in p for p in problems)


def test_scaffold_project_refuses_to_overwrite(qapp, tmp_path):
    from pytrackinganalysis.apps.config_editor import ConfigEditorWindow
    (tmp_path / "Dup").mkdir()
    with pytest.raises(FileExistsError):
        ConfigEditorWindow.scaffold_project(tmp_path, "Dup", "Valence")


def test_editor_rig_calibrations_match_the_analysis(qapp):
    """The editor's placeholder table must not drift from Parameters."""
    from pytrackinganalysis import Parameters
    from pytrackinganalysis.apps._config_tabs import RIG_MM_PER_PIXEL

    for rig, value in Parameters.RIG_MM_PER_PIXEL.items():
        assert RIG_MM_PER_PIXEL[rig] == value


# --------------------------------------------------------------------------
# DataFrame table model
# --------------------------------------------------------------------------

def test_table_model_sorts(qapp):
    """Views call setSortingEnabled(True); without sort() the clicks did nothing."""
    from pytrackinganalysis.ui.table_model import DataFrameModel

    df = pd.DataFrame({"Tracker": ["c", "a", "b"], "HighQuality": [0.5, 0.9, 0.7]})
    model = DataFrameModel(df)

    model.sort(1, Qt.SortOrder.AscendingOrder)
    assert list(model.dataframe()["HighQuality"]) == [0.5, 0.7, 0.9]

    model.sort(0, Qt.SortOrder.DescendingOrder)
    assert list(model.dataframe()["Tracker"]) == ["c", "b", "a"]


def test_table_model_sort_ignores_an_out_of_range_column(qapp):
    from pytrackinganalysis.ui.table_model import DataFrameModel

    model = DataFrameModel(pd.DataFrame({"A": [1, 2]}))
    model.sort(9)  # must not raise
    assert list(model.dataframe()["A"]) == [1, 2]
