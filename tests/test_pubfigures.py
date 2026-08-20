"""Tests for the publication-figure path (ADR-0004): the Style+Spec model,
plot_specs.yaml persistence, the plotnine renderer (editable-text SVG), the
headless batch render, and the Plot Editor app's control round trip."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

from pytrackinganalysis import experiment_types as et
from pytrackinganalysis import pubfigures as pf

_PHASES = [(0, 10), (10, 70), (70, float("inf"))]


class _Arena:
    def __init__(self, summary):
        self._summary = summary

    def summarize(self, range_minutes=(0, 0), **kw):
        return self._summary.copy()

    def summarize_facet(self, cutoffs=None, **kw):
        frames = []
        for win in _PHASES:
            tmp = self._summary.copy()
            tmp["FacetRange"] = [win] * len(tmp)
            frames.append(tmp)
        return pd.concat(frames, ignore_index=True)


class _Exp:
    def __init__(self, summary, project_dir=".", cutoffs=(10, 70)):
        self.arena = _Arena(summary)
        self.facet_cutoffs = list(cutoffs) if cutoffs else None
        self.experiment_type = et.get_experiment_type("Valence")
        self.config = {"global": {},
                       "counting_regions": {"Light": {"alias": "L"},
                                            "NoLight": {"alias": "N"}}}
        self.project_directory = str(project_dir)


def _summary(n_per=4):
    treat = ["chr"] * n_per + ["control"] * n_per
    n = len(treat)
    return pd.DataFrame({
        "Name": [f"T_{i}_0" for i in range(n)],
        "Treatment": treat,
        "FinalPI": np.linspace(-0.5, 0.5, n),
        "FinalPercentage": np.linspace(0.3, 0.8, n),
        "TotalDistancePerMin": np.linspace(80, 300, n),
        "TransitionsPerMin": np.linspace(0.2, 3.0, n),
    })


# ---- model ----------------------------------------------------------------

def test_style_and_spec_round_trip_and_fallbacks():
    style = pf.PlotStyle(theme="nope", mean_style="wat", colors={"chr": "#123456"})
    restored = pf.PlotStyle.from_dict(style.to_dict())
    assert restored.theme == "classic"          # invalid values fall back
    assert restored.mean_style == "point+sem"
    assert restored.colors == {"chr": "#123456"}
    assert restored.color_for("chr", 3) == "#123456"
    # Unmapped treatments cycle the palette by position.
    assert restored.color_for("new", 1) == pf.DEFAULT_PALETTE[1]

    spec = pf.PlotSpec(treatments={"chr": {"label": "ChR"}},
                       y_limits=(0, 1))
    restored = pf.PlotSpec.from_dict(spec.to_dict())
    assert restored.treatments["chr"] == {"label": "ChR", "show": True}
    assert restored.y_limits == [0.0, 1.0]


def test_default_specs_per_plot_type():
    pi = pf.default_spec("faceted_pi")
    assert pi.y_limits == [-1.0, 1.0] and pi.ref_line == 0.0
    perc = pf.default_spec("faceted_percentage", region1="Light")
    assert "Light" in perc.y_label and perc.ref_line == 0.5
    move = pf.default_spec("faceted_movement")
    assert move.y_limits is None and move.ref_line is None


def test_project_specs_yaml_round_trip(tmp_path):
    specs = pf.ProjectSpecs()
    specs.ensure_default_style()
    specs.styles["pub"] = pf.PlotStyle(width_mm=85, colors={"chr": "#000000"})
    specs.default_style = "pub"
    specs.plots["faceted_pi"] = pf.PlotSpec(style="pub", title="Fig 1a")
    pf.save_project_specs(str(tmp_path), specs)

    loaded = pf.load_project_specs(str(tmp_path))
    assert loaded.default_style == "pub"
    assert loaded.styles["pub"].width_mm == 85
    assert loaded.plots["faceted_pi"].title == "Fig 1a"
    assert loaded.style_for(loaded.plots["faceted_pi"]).width_mm == 85


def test_load_specs_drops_unknown_plots_and_defaults(tmp_path):
    (tmp_path / "plot_specs.yaml").write_text(
        "default_style: ghost\nplots:\n  bogus_plot: {}\n", encoding="utf-8")
    loaded = pf.load_project_specs(str(tmp_path))
    assert "bogus_plot" not in loaded.plots
    # Unknown default style falls back to an existing one.
    assert loaded.default_style in loaded.styles


# ---- data -----------------------------------------------------------------

def test_faceted_data_is_tidy_and_ordered(tmp_path):
    exp = _Exp(_summary(), tmp_path)
    df = pf.faceted_data(exp, "FinalPI")
    assert list(df.columns) == ["Treatment", "Phase", "Value"]
    assert list(df["Phase"].cat.categories) == \
        ["Acclimation", "Experiment", "Cooldown"]
    assert len(df) == 8 * 3

    # Blank treatments and NaN values are dropped.
    s = _summary()
    s.loc[0, "Treatment"] = " "
    s.loc[1, "FinalPI"] = float("nan")
    df = pf.faceted_data(_Exp(s, tmp_path), "FinalPI")
    assert len(df) == 6 * 3

    # No cutoffs -> one whole-recording phase.
    df = pf.faceted_data(_Exp(_summary(), tmp_path, cutoffs=None), "FinalPI")
    assert list(df["Phase"].cat.categories) == ["Whole recording"]


def test_merged_treatments_appends_data_levels(tmp_path):
    df = pf.faceted_data(_Exp(_summary(), tmp_path), "FinalPI")
    spec = pf.PlotSpec(treatments={"control": {"label": "Ctrl", "show": True}})
    merged = pf.merged_treatments(spec, df)
    assert list(merged) == ["control", "chr"]   # spec order first, data appended
    assert merged["chr"] == {"label": "chr", "show": True}


# ---- rendering ------------------------------------------------------------

def test_svg_has_editable_text_and_honours_spec(tmp_path):
    exp = _Exp(_summary(), tmp_path)
    spec = pf.default_spec("faceted_pi")
    spec.facets = ["Acclimation", "Experiment"]      # drop Cooldown
    spec.facet_labels = {"Experiment": "Stimulation"}
    spec.treatments = {"chr": {"label": "ChR2", "show": True},
                       "control": {"label": "Control", "show": True}}
    style = pf.PlotStyle(colors={"chr": "#112233"})
    g = pf.figure_for(exp, "faceted_pi", spec, style)
    path = pf.save_ggplot(g, str(tmp_path / "fig.svg"), style)
    svg = open(path, encoding="utf-8").read()
    assert "<text" in svg                 # svg.fonttype='none' -> live text
    assert "ChR2" in svg and "Stimulation" in svg
    assert "Cooldown" not in svg          # excluded facet is gone
    assert "#112233" in svg               # explicit treatment color used


def test_bar_sem_style_and_hidden_treatment(tmp_path):
    exp = _Exp(_summary(), tmp_path)
    spec = pf.default_spec("faceted_movement")
    spec.treatments = {"chr": {"label": "chr", "show": False},
                       "control": {"label": "control", "show": True}}
    style = pf.PlotStyle(mean_style="bar+sem")
    g = pf.figure_for(exp, "faceted_movement", spec, style)
    path = pf.save_ggplot(g, str(tmp_path / "fig.svg"), style)
    svg = open(path, encoding="utf-8").read()
    assert ">control<" in svg or "control" in svg
    assert ">chr<" not in svg             # hidden treatment absent from axis


def test_render_all_writes_defaults_and_respects_specs_file(tmp_path):
    exp = _Exp(_summary(), tmp_path)
    written = pf.render_all(exp)
    names = sorted(os.path.basename(p) for p in written)
    assert names == sorted(f"{pid}.svg" for pid in pf.PLOT_TYPES)
    assert all(os.path.exists(p) for p in written)

    # With a specs file, only the plots it defines are rendered.
    specs = pf.ProjectSpecs()
    specs.ensure_default_style()
    specs.plots["faceted_pi"] = pf.PlotSpec()
    pf.save_project_specs(str(tmp_path), specs)
    written = pf.render_all(exp, fmt="pdf")
    assert [os.path.basename(p) for p in written] == ["faceted_pi.pdf"]


def test_resolve_font_family_always_returns_something():
    families = pf.resolve_font_family("NoSuchFontEver")
    assert families and all(isinstance(f, str) for f in families)


# ---- Plot Editor app ------------------------------------------------------

@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception:  # pragma: no cover - no Qt in env
            pytest.skip("Qt unavailable")
    return app


@pytest.fixture
def editor(qapp, tmp_path):
    from pytrackinganalysis.apps.plot_editor import PlotEditorWindow

    win = PlotEditorWindow()
    # Inject a fake loaded project (bypasses the heavy Experiment load).
    win._experiment = _Exp(_summary(), tmp_path)
    win._project_dir = str(tmp_path)
    win._specs = pf.load_project_specs(str(tmp_path))
    win._reload_style_combo()
    win._set_controls_enabled(True)
    win._load_controls()
    yield win
    win._experiment = None  # closeEvent must not persist for the fake
    win.close()


def test_editor_renders_preview_and_round_trips_controls(editor):
    editor._render_preview()
    assert editor.preview.pixmap() is not None
    assert not editor.preview.pixmap().isNull()

    # Tables were populated from the data.
    assert editor.facet_table.rowCount() == 3
    assert editor.treat_table.rowCount() == 2

    # Widget -> model round trip.
    editor.point_size.setValue(3.0)
    editor.title_edit.setText("Figure 1")
    editor.ylim_check.setChecked(True)
    editor.ylim_lo.setValue(-0.8)
    editor.ylim_hi.setValue(0.8)
    editor._read_controls()
    assert editor._current_style().point_size == 3.0
    spec = editor._current_spec()
    assert spec.title == "Figure 1"
    assert spec.y_limits == [-0.8, 0.8]


def test_editor_save_style_as_and_default_persist(editor, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("pub", True)))
    editor._save_style_as()
    assert "pub" in editor._specs.styles
    assert editor._current_spec().style == "pub"

    editor._set_default_style()
    loaded = pf.load_project_specs(str(tmp_path))
    assert loaded.default_style == "pub"
    assert "pub" in loaded.styles


def test_editor_reorders_treatments(editor):
    editor.treat_table.selectRow(0)
    first = editor.treat_table.item(0, 0).text()
    editor._move_treatment(+1)
    assert editor.treat_table.item(1, 0).text() == first
    assert list(editor._current_spec().treatments)[1] == first


# ---- ggplot look, backgrounds, p-values, boxplots --------------------------

def test_new_style_fields_round_trip_and_fallbacks():
    style = pf.PlotStyle(geom="violin", strip_style="fancy", line_pt=1.4,
                         panel_bg="#fafafa", strip_bg="#e8eef7")
    restored = pf.PlotStyle.from_dict(style.to_dict())
    assert restored.geom == "dots"            # invalid values fall back
    assert restored.strip_style == "plain"
    assert restored.line_pt == 1.4
    assert restored.panel_bg == "#fafafa" and restored.strip_bg == "#e8eef7"

    spec = pf.PlotSpec(p_values=True)
    assert pf.PlotSpec.from_dict(spec.to_dict()).p_values is True
    assert pf.PlotSpec.from_dict({}).p_values is False


def test_facet_pvalues_welch_per_phase(tmp_path):
    # Deterministic separation: chr ~0, control ~1 -> tiny p in every phase.
    s = _summary()
    s["FinalPI"] = [0.0, 0.01, 0.02, 0.03, 1.0, 1.01, 1.02, 1.03]
    df = pf.faceted_data(_Exp(s, tmp_path), "FinalPI")
    pvals = pf.facet_pvalues(df)
    assert list(pvals["Phase"]) == ["Acclimation", "Experiment", "Cooldown"]
    assert (pvals["p"] < 1e-6).all()
    assert set(zip(pvals["a"], pvals["b"])) == {("chr", "control")}


def test_pvalue_brackets_render_and_extend_ylim(tmp_path):
    exp = _Exp(_summary(), tmp_path)
    spec = pf.default_spec("faceted_pi")     # y_limits [-1, 1]
    spec.p_values = True
    style = pf.PlotStyle()
    g = pf.figure_for(exp, "faceted_pi", spec, style)
    path = pf.save_ggplot(g, str(tmp_path / "p.svg"), style)
    svg = open(path, encoding="utf-8").read()
    # A formatted p-value label made it into the vector file as text.
    pvals = pf.facet_pvalues(pf.faceted_data(exp, "FinalPI"))
    assert any(f"{p:.2g}" in svg for p in pvals["p"])


def test_boxplot_and_boxed_strip_render(tmp_path):
    exp = _Exp(_summary(), tmp_path)
    spec = pf.default_spec("faceted_movement")
    style = pf.PlotStyle(geom="box", strip_style="boxed",
                         strip_bg="#e8eef7", panel_bg="#f5f5f5", line_pt=1.2)
    g = pf.figure_for(exp, "faceted_movement", spec, style)
    path = pf.save_ggplot(g, str(tmp_path / "box.svg"), style)
    svg = open(path, encoding="utf-8").read()
    assert "#e8eef7" in svg.lower()          # strip box fill present
    assert "#f5f5f5" in svg.lower()          # panel background present

    # box+dots renders too (dots overlaid, boxplot outliers suppressed).
    style.geom = "box+dots"
    g = pf.figure_for(exp, "faceted_movement", spec, style)
    assert pf.render_png_bytes(g, style, dpi=72)[:8] == b"\x89PNG\r\n\x1a\n"


def test_editor_round_trips_new_controls(editor):
    editor.geom_combo.setCurrentText("box")
    editor.strip_combo.setCurrentText("boxed")
    editor.line_pt.setValue(1.5)
    editor.panel_bg_check.setChecked(True)
    editor.pvalues_check.setChecked(True)
    editor._read_controls()
    style, spec = editor._current_style(), editor._current_spec()
    assert style.geom == "box" and style.strip_style == "boxed"
    assert style.line_pt == 1.5
    assert style.panel_bg          # checked -> a color is written
    assert spec.p_values is True
    editor.panel_bg_check.setChecked(False)
    editor._read_controls()
    assert editor._current_style().panel_bg == ""


def test_point_outline_round_trip_and_render(tmp_path, editor):
    # Model round trip.
    style = pf.PlotStyle(point_stroke=0.8)
    assert pf.PlotStyle.from_dict(style.to_dict()).point_stroke == 0.8
    assert pf.PlotStyle.from_dict({}).point_stroke == 0.0  # default: no outline

    # Outlined points render (black edge + treatment fill via scale_fill).
    exp = _Exp(_summary(), tmp_path)
    spec = pf.default_spec("faceted_pi")
    g = pf.figure_for(exp, "faceted_pi", spec,
                      pf.PlotStyle(point_stroke=0.8, colors={"chr": "#112233"}))
    path = pf.save_ggplot(g, str(tmp_path / "o.svg"),
                          pf.PlotStyle(point_stroke=0.8))
    svg = open(path, encoding="utf-8").read()
    assert "#112233" in svg               # treatment color survives as fill

    # Editor round trip.
    editor.point_stroke.setValue(1.2)
    editor._read_controls()
    assert editor._current_style().point_stroke == 1.2


def test_editor_restore_defaults_resets_spec_not_style(editor):
    editor.title_edit.setText("Customized")
    editor.point_size.setValue(3.3)
    editor._read_controls()
    style_name = editor._current_spec().style
    assert editor._current_spec().title == "Customized"

    editor._restore_defaults()
    spec = editor._current_spec()
    assert spec.title == ""                       # spec content reset
    assert spec.y_limits == [-1.0, 1.0]
    assert spec.style == editor._specs.default_style
    # Shared style untouched by the plot reset.
    assert editor._specs.styles[style_name].point_size == 3.3


def test_facet_width_mode_keeps_panels_constant(tmp_path):
    import io as _io

    from PIL import Image

    # Off (0): the figure is width_mm regardless of facet count.
    style = pf.PlotStyle(width_mm=180, facet_width_mm=0)
    assert pf.effective_width_mm(style, 3) == 180
    # On: margin + per-facet width x shown facets.
    style = pf.PlotStyle(facet_width_mm=50)
    assert pf.effective_width_mm(style, 3) == pf._AXIS_MARGIN_MM + 150
    assert pf.effective_width_mm(style, 2) == pf._AXIS_MARGIN_MM + 100

    # Rendered pixels agree: dropping a facet shrinks the figure by exactly
    # one facet width instead of stretching the remaining panels.
    exp = _Exp(_summary(), tmp_path)
    spec = pf.default_spec("faceted_pi")
    dpi = 72
    g3 = pf.figure_for(exp, "faceted_pi", spec, style)
    w3 = Image.open(_io.BytesIO(pf.render_png_bytes(g3, style, dpi=dpi))).size[0]
    spec.facets = ["Acclimation", "Experiment"]
    g2 = pf.figure_for(exp, "faceted_pi", spec, style)
    w2 = Image.open(_io.BytesIO(pf.render_png_bytes(g2, style, dpi=dpi))).size[0]
    expected_delta = 50 / 25.4 * dpi
    assert abs((w3 - w2) - expected_delta) <= 2


def test_editor_facet_width_round_trip_and_wheelproof_controls(editor):
    from pytrackinganalysis.apps import plot_editor as pe

    editor.facet_width.setValue(55.0)
    editor._read_controls()
    assert editor._current_style().facet_width_mm == 55.0

    # Every dropdown and spinner in the editor ignores the mouse wheel, so
    # scrolling the options panel never edits a hovered control.
    for combo in (editor.theme_combo, editor.mean_combo, editor.geom_combo,
                  editor.strip_combo, editor.plot_combo, editor.style_combo):
        assert isinstance(combo, pe._NoWheelCombo)
    assert isinstance(editor.font_combo, pe._NoWheelFontCombo)
    for spin in (editor.width_mm, editor.height_mm, editor.facet_width,
                 editor.point_size, editor.jitter, editor.line_pt):
        assert isinstance(spin, pe._NoWheelSpin)
