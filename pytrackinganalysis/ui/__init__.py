"""Shared themed-UI primitives for PyTrackingAnalysis Qt apps.

Vendored from pyflic (``pyflic/base/ui/``) with ``Pyflic*`` objectNames
renamed to ``Ptrack*`` so the QSS rules don't collide if both projects
ever share a process.
"""

from .icons import app_icon, icon
from .theme import Category, ThemeMode, apply_theme, category_color, current_mode, resolved_mode
from .widgets import ActionButton, Card, OutputLog, PlotDock, SidebarNav, TopBar
from .zoom import ZoomableImageView, ZoomableTextView

__all__ = [
    "ActionButton",
    "Card",
    "Category",
    "OutputLog",
    "PlotDock",
    "SidebarNav",
    "ThemeMode",
    "TopBar",
    "ZoomableImageView",
    "ZoomableTextView",
    "apply_theme",
    "category_color",
    "current_mode",
    "app_icon",
    "icon",
    "resolved_mode",
]
