"""Tests for the rich text rendering of the Output log and text tabs:
proportional prose with headings, monospace reserved for tabular content,
and on-screen numbers capped at four decimal places."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pytrackinganalysis.ui import textformat as tf

from test_project import qapp  # noqa: F401  (fixture reuse)


# ---- number display --------------------------------------------------------

def test_decimals_cap_at_four_places():
    assert tf.shorten_decimals("PI = 0.523456789") == "PI = 0.5235"
    assert tf.shorten_decimals("delta -1.000049 done") == "delta -1.0000 done"
    # At most four: shorter numbers are untouched, integers too.
    assert tf.shorten_decimals("0.12 and 7 and 3.1415") == "0.12 and 7 and 3.1415"
    # Scientific notation survives — 1.2e-08 must not become 0.0000.
    assert tf.shorten_decimals("p=1.234567e-08") == "p=1.234567e-08"
    # Version-ish dotted tokens are not floats.
    assert tf.shorten_decimals("v1.2.345678") == "v1.2.345678"


def test_tabular_detection():
    assert tf.looks_tabular("Tracker   HighQuality   NotFound")
    assert tf.looks_tabular("a\tb")
    assert not tf.looks_tabular("A plain sentence with single spaces.")
    assert not tf.looks_tabular("   indented but single-spaced words")


# ---- log lines -------------------------------------------------------------

def test_log_line_prose_is_proportional_with_muted_prefix():
    html = tf.log_line_to_html("[Rep1] running 'QC' (from project)…")
    assert tf.MONO_FAMILY not in html
    assert "[Rep1]" in html and tf._MUTED in html


def test_log_line_tabular_and_traceback_are_monospace():
    assert tf.MONO_FAMILY in tf.log_line_to_html("T_0    0.98    0.01")
    assert tf.MONO_FAMILY in tf.log_line_to_html('  File "x.py", line 3')


def test_log_line_accents_and_step_headings():
    assert "#d9534f" in tf.log_line_to_html("[Rep2] FAILED: boom")
    assert "#c77700" in tf.log_line_to_html("[notes] skipped — not a Project")
    assert "#2e8b57" in tf.log_line_to_html("✓ Project script complete.")
    heading = tf.log_line_to_html("── Step 1/5: Run all analyses")
    assert "<b" in heading and "Step 1/5" in heading


def test_log_line_escapes_markup():
    assert "<script>" not in tf.log_line_to_html("evil <script> here")


# ---- whole files -----------------------------------------------------------

def test_text_blocks_classify_heading_table_prose():
    text = (
        "Experiment summary\n"
        "==================\n"
        "\n"
        "The recording ran for 80 minutes with 0.123456 mean movement.\n"
        "\n"
        "Tracker   HighQuality   NotFound\n"
        "T_0       0.987654      0.000123\n"
    )
    html = tf.text_to_html(text)
    assert "<b" in html and "Experiment summary" in html
    # Monospace appears exactly once: on the table block.
    assert html.count(tf.MONO_FAMILY) == 1
    # Numbers cap at four decimals everywhere, padded inside the table.
    assert "0.1235" in html and "0.9877" in html
    assert "0.123456" not in html


def test_csv_renders_as_a_real_table():
    html = tf.csv_to_html("Tracker,PI,Flies\nT_0,0.523456789,12\n")
    assert "<table" in html and "<th" in html
    assert "0.5235" in html and "0.523456789" not in html
    assert 'align="right"' in html          # numeric cells right-align
    assert tf.MONO_FAMILY not in html       # a table needs no mono font


def test_file_to_html_dispatches_on_suffix(tmp_path):
    assert "<table" in tf.file_to_html(tmp_path / "x.csv", "a,b\n1,2\n")
    assert "<table" not in tf.file_to_html(tmp_path / "x.txt", "hello world")


# ---- the widgets -----------------------------------------------------------

def test_output_log_uses_mono_only_for_tabular_lines(qapp):  # noqa: F811
    from pytrackinganalysis.ui import OutputLog

    log = OutputLog()
    emitted: list[str] = []
    log.line_appended.connect(emitted.append)
    log.append_line("Project: /tmp/somewhere")
    log.append_line("T_0    0.987654    0.000123")
    html = log.document().toHtml()
    assert "JetBrains Mono" in html          # the tabular line
    assert "0.9877" in html and "0.987654" not in html
    # The signal still carries the raw line for tests and mirrors.
    assert emitted == ["Project: /tmp/somewhere",
                       "T_0    0.987654    0.000123"]


def test_text_view_renders_csv_as_table(qapp, tmp_path):  # noqa: F811
    from pytrackinganalysis.ui import ZoomableTextView

    path = tmp_path / "Proj_Summary.csv"
    path.write_text("Tracker,PI\nT_0,0.523456789\n", encoding="utf-8")
    view = ZoomableTextView(path)
    html = view._editor.toHtml()
    assert "0.5235" in html and "0.523456789" not in html
    # Zoom still works through the default font.
    before = view._editor.font().pointSizeF()
    view.zoom_by(view._ZOOM_STEP)
    assert view._editor.font().pointSizeF() > before
    view.deleteLater()
