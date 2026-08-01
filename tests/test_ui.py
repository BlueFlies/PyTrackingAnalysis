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
