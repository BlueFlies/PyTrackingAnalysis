"""Shared themed-UI primitives for PyTrackingAnalysis Qt apps.

Vendored from pyflic (``pyflic/base/ui/``) with ``Pyflic*`` objectNames
renamed to ``Ptrack*`` so the QSS rules don't collide if both projects
ever share a process.
"""

from .icons import icon
from .theme import Category, ThemeMode, apply_theme, category_color, current_mode, resolved_mode
from .widgets import ActionButton, Card, OutputLog, PlotDock, SidebarNav, TopBar

__all__ = [
    "ActionButton",
    "Card",
    "Category",
    "OutputLog",
    "PlotDock",
    "SidebarNav",
    "ThemeMode",
    "TopBar",
    "apply_theme",
    "category_color",
    "current_mode",
    "icon",
    "resolved_mode",
]
