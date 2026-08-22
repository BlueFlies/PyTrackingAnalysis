"""Shared theming for PyTrackingAnalysis Qt apps.

Vendored from pyflic's ``base/ui/theme.py`` with ``Pyflic*`` objectNames
renamed to ``Ptrack*``.  A single :func:`apply_theme` is the entry point.
:class:`Category` defines the semantic color of an action and is consumed
by :mod:`.icons` and :mod:`.widgets` to tint icons, button borders, and
section headers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

import qdarktheme
from PyQt6.QtWidgets import QApplication

ThemeMode = Literal["light", "dark", "auto"]


class Category(str, Enum):
    LOAD = "load"
    ANALYZE = "analyze"
    PLOTS = "plots"
    QC = "qc"
    SCRIPTS = "scripts"
    AI = "ai"
    TOOLS = "tools"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class CategoryColors:
    light: str
    dark: str

    def for_mode(self, mode: ThemeMode) -> str:
        return self.dark if mode == "dark" else self.light


PALETTE: dict[Category, CategoryColors] = {
    Category.LOAD:    CategoryColors("#2563eb", "#3b82f6"),
    Category.ANALYZE: CategoryColors("#16a34a", "#22c55e"),
    Category.PLOTS:   CategoryColors("#ea580c", "#fb923c"),
    Category.QC:      CategoryColors("#dc2626", "#f87171"),
    Category.SCRIPTS: CategoryColors("#9333ea", "#a855f7"),
    Category.AI:      CategoryColors("#0d9488", "#2dd4bf"),
    Category.TOOLS:   CategoryColors("#475569", "#94a3b8"),
    Category.NEUTRAL: CategoryColors("#64748b", "#94a3b8"),
}

_current_mode: ThemeMode = "auto"
_resolved_mode: Literal["light", "dark"] = "light"


def current_mode() -> ThemeMode:
    return _current_mode


def resolved_mode() -> Literal["light", "dark"]:
    """The actually-applied light/dark mode (``"auto"`` resolves via OS)."""
    return _resolved_mode


def category_color(category: Category, mode: ThemeMode | None = None) -> str:
    use_mode: ThemeMode = mode or _resolved_mode
    if use_mode == "auto":
        use_mode = _resolved_mode
    return PALETTE[category].for_mode(use_mode)


def _resolve_auto() -> Literal["light", "dark"]:
    try:
        import darkdetect

        ans = (darkdetect.theme() or "Light").strip().lower()
        return "dark" if ans == "dark" else "light"
    except Exception:  # noqa: BLE001
        return "light"


def surface_colors() -> dict:
    """Explicit surface colors for the resolved theme.

    qdarktheme's stylesheet leaves the Window/Base/Mid/Midlight palette
    roles at the platform's LIGHT values, so any of our styles written as
    ``palette(base)`` etc. rendered light chips with unreadable text on the
    dark UI. Every custom surface resolves through this table instead."""
    if _resolved_mode == "dark":
        return {"base": "#1f2226", "band": "#26292d", "border": "#3f444b",
                "hover": "#33383e", "text": "#e1e5e9", "muted": "#8b949e"}
    return {"base": "#ffffff", "band": "#f4f5f7", "border": "#c4c8cc",
            "hover": "#e4e7ea", "text": "#0f172a", "muted": "#64748b"}


def _additional_qss() -> str:
    """QSS appended to qdarktheme's stylesheet for PyTrackingAnalysis widgets."""
    c = surface_colors()
    return f"""
    QPushButton#PtrackSidebarItem {{
        text-align: left;
        padding: 8px 12px;
        border: none;
        border-radius: 6px;
        font-weight: 500;
    }}
    QPushButton#PtrackSidebarItem:hover {{
        background: {c["hover"]};
    }}
    QPushButton#PtrackSidebarItem:checked {{
        background: palette(highlight);
        color: palette(highlighted-text);
    }}
    QFrame#PtrackCard {{
        border-radius: 10px;
        background: {c["base"]};
    }}
    QLabel#PtrackCardTitle {{
        font-size: 13pt;
        font-weight: 600;
        padding-bottom: 2px;
        color: {c["text"]};
    }}
    QLabel#PtrackCardSubtitle {{
        color: {c["muted"]};
        font-size: 9pt;
    }}
    QLabel#PtrackSectionDivider {{
        color: {c["muted"]};
        font-size: 10px;
        padding-top: 6px;
    }}
    QFrame#PtrackTopBar {{
        background: {c["base"]};
        border-bottom: 1px solid {c["border"]};
    }}
    QLabel#PtrackAppTitle {{
        font-size: 14pt;
        font-weight: 600;
        color: {c["text"]};
    }}
    /* Script-editor palette tiles (script_editor/palette.py): surface and
       description text must track the theme, not palette(base)/palette(mid),
       which stay at light values under qdarktheme. */
    QFrame#PtrackScriptTile {{
        background: {c["base"]};
    }}
    QFrame#PtrackScriptTile:hover {{
        background: {c["hover"]};
    }}
    QLabel#PtrackScriptTileDesc {{
        color: {c["text"]};
        font-size: 9pt;
    }}
    QFrame#PtrackStepCard {{
        background: {c["base"]};
    }}
    QLabel#PtrackStepNum {{
        color: {c["muted"]};
    }}
    QLabel#PtrackStepChip {{
        color: {c["text"]};
        font-size: 9pt;
    }}
    QWidget#PtrackInspectorHeader {{
        background: {c["band"]};
    }}
    QLabel#PtrackInspectorDesc {{
        color: {c["text"]};
        font-size: 9pt;
    }}
    QLabel#PtrackScriptHint {{
        color: {c["muted"]};
        font-style: italic;
    }}
    /* Proportional by default — tabular log lines carry their own
       monospace spans (ui/textformat.py). */
    QPlainTextEdit#PtrackLog {{
        font-size: 10pt;
    }}
    /* Make dropdowns embedded in tables blend with the table cell background
       and preserve the cell grid lines on the right/bottom edges. */
    QTableWidget QComboBox {{
        background: {c["base"]};
        color: {c["text"]};
        border-top: 1px solid transparent;
        border-left: 1px solid transparent;
        border-right: 1px solid {c["border"]};
        border-bottom: 1px solid {c["border"]};
        padding: 2px 4px;
    }}
    QTableWidget QComboBox:hover {{
        border: 1px solid {c["border"]};
    }}
    QTableWidget QComboBox::drop-down {{
        border: none;
        width: 16px;
    }}
    QTableWidget QComboBox QAbstractItemView {{
        background: {c["base"]};
        color: {c["text"]};
        selection-background-color: palette(highlight);
        selection-color: palette(highlighted-text);
    }}
    """


def apply_theme(app: QApplication, mode: ThemeMode = "auto") -> None:
    """Apply the chosen theme to *app* and remember it."""
    global _current_mode, _resolved_mode
    _current_mode = mode
    _resolved_mode = _resolve_auto() if mode == "auto" else mode  # type: ignore[assignment]
    qdarktheme.setup_theme(mode, additional_qss=_additional_qss())
