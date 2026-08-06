"""Tests for the report subsystem: the backend-agnostic document model, the
reportlab backend, the backend dispatcher, and the report-native figure builder.

Hermetic — nothing is read from disk except the temp PDF these tests write.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from pytrackinganalysis import Parameters, report_figures
from pytrackinganalysis import report
from pytrackinganalysis.report import model as m


def _sample_report() -> report.Report:
    r = report.Report("UnitExperiment")
    r.add(m.Cover("UnitExperiment", "Tracking Analysis Report",
                  metadata=[("Tracking type", "TWOCHOICETRACKER"),
                            ("Project", "C:/" + "long/" * 40 + "proj")],
                  status=m.StatusLine("Data quality: 3/4 ok", m.Level.ERROR)))
    r.add(m.SectionDivider("Analysis"))
    r.add(m.Preformatted("a" * 400, title="Stats"))          # must not overflow
    r.add(m.Table(["Treatment", "HighQuality"],
                  [["control", "0.98"], ["chr", "0.72"]],
                  title="Summary", row_levels=[m.Level.OK, m.Level.ERROR]))
    return r


def test_reportlab_backend_writes_a_pdf(tmp_path):
    out = tmp_path / "r.pdf"
    report.render(_sample_report(), str(out))
    assert out.exists()
    head = out.read_bytes()[:5]
    assert head == b"%PDF-", "output is not a PDF"
    assert out.stat().st_size > 1500


def test_long_monospaced_line_is_wrapped_not_clipped():
    # The backend soft-wraps long monospaced lines so they cannot run off the
    # page; the wrap width must be a sane positive number of characters.
    from pytrackinganalysis.report.backends import reportlab_backend as rb

    assert rb._MONO_WRAP > 40
    wrapped = rb._wrap_mono("x" * 400)
    assert all(len(line) <= rb._MONO_WRAP for line in wrapped.splitlines())


def test_dispatcher_lists_reportlab_and_rejects_unknown(tmp_path):
    assert "reportlab" in report.available_backends()
    with pytest.raises(ValueError, match="Unknown report backend"):
        report.render(_sample_report(), str(tmp_path / "x.pdf"), backend="nope")


def test_model_stays_free_of_rendering_imports():
    # The whole point of the split: the document model must not drag in a
    # rendering engine. Importing it must not import reportlab.
    import importlib
    import sys

    sys.modules.pop("reportlab", None)
    importlib.reload(importlib.import_module("pytrackinganalysis.report.model"))
    assert "reportlab" not in sys.modules


_PHASES = [(0, 10), (10, float("inf"))]


class _FakeArena:
    def __init__(self, summary, dq=None):
        self._summary = summary
        self._dq = dq

    def summarize(self, range_minutes=(0, 0), remove_partners=False, **kw):
        return self._summary.copy()

    def summarize_facet(self, cutoffs=None, remove_partners=False, **kw):
        frames = []
        for win in _PHASES:
            tmp = self._summary.copy()
            tmp["FacetRange"] = [win] * len(tmp)
            frames.append(tmp)
        return pd.concat(frames, ignore_index=True)

    def supports_data_quality(self):
        return self._dq is not None

    def get_data_quality(self, range_minutes=(0, 0)):
        if self._dq is None:
            raise ValueError("no dq")
        return self._dq.copy()


class _FakeExp:
    def __init__(self, tracking_type, summary, dq=None, facet_cutoffs=None):
        self.arena = _FakeArena(summary, dq)
        self.facet_cutoffs = facet_cutoffs
        self.parameters = Parameters.Parameters(tracking_type=tracking_type)


def _twochoice_summary():
    treat = ["control"] * 4 + ["chr"] * 4
    n = len(treat)
    return pd.DataFrame({
        "Treatment": treat,
        "TotalDistancePerMin": np.linspace(8, 13, n),
        "PercWalking": np.linspace(0.2, 0.4, n),
        "PercResting": np.linspace(0.5, 0.3, n),
        "FinalPI": np.linspace(-0.5, 0.5, n),
        "FinalPercentage": np.linspace(0.3, 0.8, n),
    })


def test_analysis_figures_built_for_two_choice():
    exp = _FakeExp(Parameters.TrackingType.TWOCHOICETRACKER, _twochoice_summary())
    figs = report_figures.build_analysis_figures(exp)
    # At least the Choice and Locomotion figures, each carrying PNG bytes.
    assert len(figs) >= 2
    for fig in figs:
        assert isinstance(fig, m.Figure)
        assert fig.data[:8] == b"\x89PNG\r\n\x1a\n"
        assert fig.width_in > 0 and fig.height_in > 0


def test_analysis_figures_empty_when_no_treatments():
    summary = _twochoice_summary()
    summary["Treatment"] = ""  # every row unassigned
    exp = _FakeExp(Parameters.TrackingType.TWOCHOICETRACKER, summary)
    assert report_figures.build_analysis_figures(exp) == []


def test_qc_figure_built_when_supported():
    dq = pd.DataFrame({"Tracker": [f"T_{i}" for i in range(5)],
                       "HighQuality": [0.6, 0.85, 0.95, 0.99, 0.7]})
    exp = _FakeExp(Parameters.TrackingType.TWOCHOICETRACKER,
                   _twochoice_summary(), dq=dq)
    figs = report_figures.build_qc_figures(exp)
    assert len(figs) == 1 and isinstance(figs[0], m.Figure)


def test_qc_figure_absent_when_unsupported():
    exp = _FakeExp(Parameters.TrackingType.TWOCHOICECOUNTER, _twochoice_summary())
    assert report_figures.build_qc_figures(exp) == []


def test_faceted_figures_empty_without_cutoffs():
    exp = _FakeExp(Parameters.TrackingType.TWOCHOICETRACKER, _twochoice_summary(),
                   facet_cutoffs=None)
    assert report_figures.build_faceted_figures(exp) == []


def test_faceted_figures_built_with_cutoffs():
    exp = _FakeExp(Parameters.TrackingType.TWOCHOICETRACKER, _twochoice_summary(),
                   facet_cutoffs=[10])
    figs = report_figures.build_faceted_figures(exp)
    # Choice-by-phase and Locomotion-by-phase at least; each carries PNG bytes.
    assert len(figs) >= 2
    assert all(isinstance(f, m.Figure) and f.data[:4] == b"\x89PNG" for f in figs)


def test_faceted_figures_use_experiment_type_phase_labels(monkeypatch):
    # A Valence experiment_type should label phases Acclimation/Experiment/…
    # rather than raw minute ranges. Capture the tick labels the panel sets.
    from pytrackinganalysis import experiment_types as et
    from pytrackinganalysis import report_figures as rf

    captured = {}
    real = rf.plt.Axes.set_xticklabels

    def _spy(self, labels, *a, **k):
        captured.setdefault("labels", list(labels))
        return real(self, labels, *a, **k)

    monkeypatch.setattr(rf.plt.Axes, "set_xticklabels", _spy)

    exp = _FakeExp(Parameters.TrackingType.TWOCHOICETRACKER, _twochoice_summary(),
                   facet_cutoffs=[10])
    exp.experiment_type = et.get_experiment_type("Valence")
    rf.build_faceted_figures(exp)
    assert captured.get("labels") == ["Acclimation", "Experiment"]


def test_report_model_has_figures_and_stats_but_no_data_tables(tmp_path):
    # Data belongs in the CSVs, not the PDF: the assembled model must carry
    # figures and the stats text, but no Table blocks even though a CSV sits in
    # the analysis directory.
    from pytrackinganalysis.Experiment import Experiment

    analysis = tmp_path / "analysis"
    qc = tmp_path / "qc"
    analysis.mkdir()
    qc.mkdir()
    _twochoice_summary().to_csv(analysis / "E_Summary.csv", index=False)
    (analysis / "E_Stats.txt").write_text("control vs chr: T=3.1, p=0.005\n",
                                           encoding="utf-8")

    from pytrackinganalysis import experiment_types as et

    class _Exp(Experiment):
        def __init__(self):
            self.arena = _FakeArena(_twochoice_summary())
            self.arena.experiment_name = "E"
            self.project_directory = str(tmp_path)
            self.analysis_path = str(analysis) + os.sep
            self.qc_path = str(qc) + os.sep
            self.config = {"global": {"tracking_rig": "colosseum"}}
            self.facet_cutoffs = [10]
            self.experiment_type = et.get_experiment_type(None)
            self.parameters = Parameters.Parameters(
                tracking_type=Parameters.TrackingType.TWOCHOICETRACKER)

    model = _Exp().build_report_model(qc_cutoff=0.9)
    kinds = [type(b).__name__ for b in model.blocks]
    assert "Table" not in kinds
    assert kinds.count("Figure") >= 2       # overall + faceted figures
    assert "Preformatted" in kinds          # the stats text survives
