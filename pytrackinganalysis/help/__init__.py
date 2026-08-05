"""In-app help: topic registry, dialogs, and ? buttons.

Isolated from analysis code — apps import only this package.
"""

from __future__ import annotations

from .button import HelpButton, make_topbar_help_button
from .dialog import HelpBrowser, HelpDialog, open_getting_started, open_help_browser, show_help
from .topics import TOPICS, HelpTopic, get_topic, topic_ids

__all__ = [
    "HelpButton",
    "HelpBrowser",
    "HelpDialog",
    "HelpTopic",
    "TOPICS",
    "get_topic",
    "make_topbar_help_button",
    "open_getting_started",
    "open_help_browser",
    "show_help",
    "topic_ids",
]
