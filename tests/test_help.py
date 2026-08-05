"""Tests for the isolated in-app help package."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from pytrackinganalysis.help import (
    HelpBrowser,
    HelpButton,
    HelpDialog,
    TOPICS,
    get_topic,
    show_help,
    topic_ids,
)
from pytrackinganalysis.help.render import md_to_html, load_topic_markdown, topic_html


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_registry_ids_unique_and_ordered():
    ids = topic_ids()
    assert ids[0] == "getting_started"
    assert len(ids) == len(set(ids))
    assert set(ids) == {t.id for t in TOPICS}


def test_every_topic_has_markdown_file():
    root = Path(__file__).resolve().parents[1] / "pytrackinganalysis" / "help" / "content"
    for topic in TOPICS:
        path = root / topic.filename
        assert path.is_file(), f"missing {path}"
        text = path.read_text(encoding="utf-8").strip()
        assert text, f"empty {path}"
        assert load_topic_markdown(topic.id).strip()


def test_get_topic_unknown_raises():
    with pytest.raises(KeyError, match="Unknown help topic"):
        get_topic("not_a_real_topic")


def test_md_to_html_basics():
    html = md_to_html(
        "# Title\n\n"
        "A **bold** and *italic* word with `code`.\n\n"
        "- one\n"
        "- two\n\n"
        "1. first\n"
        "2. second\n\n"
        "```\n"
        "x = 1\n"
        "```\n\n"
        "See [docs](https://example.com).\n"
    )
    assert "<h1>Title</h1>" in html
    assert "<b>bold</b>" in html
    assert "<i>italic</i>" in html
    assert "<code>code</code>" in html
    assert "<ul>" in html and "<li>one</li>" in html
    assert "<ol>" in html and "<li>first</li>" in html
    assert "<pre><code>" in html and "x = 1" in html
    assert 'href="https://example.com"' in html


def test_topic_html_for_all_topics():
    for topic_id in topic_ids():
        html = topic_html(topic_id)
        assert "<html>" in html
        assert len(html) > 50


def test_help_dialog_and_browser_construct(qapp):
    dlg = HelpDialog("getting_started")
    assert "Getting started" in dlg.windowTitle()
    dlg.close()

    browser = HelpBrowser(initial_topic="batch_experiments")
    assert browser._list.count() == len(TOPICS)
    browser.close()


def test_help_button_construct(qapp):
    btn = HelpButton("outputs", tooltip="Outputs help")
    assert btn.text() == "?"
    assert btn.toolTip() == "Outputs help"


def test_show_help_runs(qapp, monkeypatch):
    seen = {}

    def _fake_exec(self):
        seen["title"] = self.windowTitle()
        return 1

    monkeypatch.setattr(HelpDialog, "exec", _fake_exec)
    show_help(None, "qc_overview")
    assert "QC" in seen["title"] or "qc" in seen["title"].lower()
