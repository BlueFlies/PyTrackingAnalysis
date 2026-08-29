"""Centralised icon factory.

Vendored from pyflic's ``base/ui/icons.py``.  Wraps ``qtawesome`` so glyph
names live in one file and tinting follows the active theme + category
color.  Use ``icon("load")`` for a category icon, or
``icon("fa5s.folder")`` for an explicit qtawesome name.
"""

from __future__ import annotations

import qtawesome as qta
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from .theme import Category, category_color, resolved_mode

# Logical name → (qtawesome glyph, default Category for tinting).
_GLYPHS: dict[str, tuple[str, Category | None]] = {
    # Navigation / sidebar
    "home":       ("fa5s.home",                Category.NEUTRAL),
    "project":    ("fa5s.folder-open",         Category.NEUTRAL),
    "run":        ("fa5s.bolt",                Category.LOAD),
    "plots":      ("fa5s.chart-bar",           Category.PLOTS),
    "qc":         ("fa5s.search",              Category.QC),
    "scripts":    ("fa5s.scroll",              Category.SCRIPTS),
    "ai":         ("fa5s.robot",               Category.AI),
    "tools":      ("fa5s.tools",               Category.TOOLS),
    "settings":   ("fa5s.cog",                 Category.NEUTRAL),
    "theme_dark": ("fa5s.moon",                Category.NEUTRAL),
    "theme_light":("fa5s.sun",                 Category.NEUTRAL),
    # Actions
    "load":       ("fa5s.download",            Category.LOAD),
    "remove":     ("fa5s.minus-circle",        Category.LOAD),
    "script":     ("fa5s.play",                Category.SCRIPTS),
    "basic":      ("fa5s.chart-area",          Category.ANALYZE),
    "csv":        ("fa5s.file-csv",            Category.ANALYZE),
    "binned":     ("fa5s.stream",              Category.ANALYZE),
    "weighted":   ("fa5s.balance-scale",       Category.ANALYZE),
    "tidy":       ("fa5s.table",               Category.ANALYZE),
    "bootstrap":  ("fa5s.dice",                Category.ANALYZE),
    "compare":    ("fa5s.code-branch",         Category.ANALYZE),
    "lightphase": ("fa5s.adjust",              Category.ANALYZE),
    "sensitivity":("fa5s.sliders-h",           Category.ANALYZE),
    "transition": ("fa5s.exchange-alt",        Category.ANALYZE),
    "pdf":        ("fa5s.file-pdf",            Category.ANALYZE),
    "plot":       ("fa5s.chart-line",          Category.PLOTS),
    "feeding":    ("fa5s.utensils",            Category.PLOTS),
    "dot":        ("fa5s.braille",             Category.PLOTS),
    "well":       ("fa5s.vials",               Category.PLOTS),
    "lint":       ("fa5s.spell-check",         Category.TOOLS),
    "compare_cfg":("fa5s.exchange-alt",        Category.TOOLS),
    "clear":      ("fa5s.trash-alt",           Category.TOOLS),
    "refresh":    ("fa5s.sync-alt",            Category.TOOLS),
    "config":     ("fa5s.sliders-h",           Category.TOOLS),
    # Tracking-specific (new to PyTrackingAnalysis)
    "track":      ("fa5s.route",               Category.ANALYZE),
    "batch":      ("fa5s.layer-group",         Category.LOAD),
    "experiment": ("fa5s.flask",               Category.LOAD),
    "distance":   ("fa5s.ruler-horizontal",    Category.PLOTS),
    "quality":    ("fa5s.check-circle",        Category.QC),
    "xy":         ("fa5s.crosshairs",          Category.PLOTS),
    "report":     ("fa5s.file-pdf",            Category.ANALYZE),
    # File menu
    "open":       ("fa5s.folder-open",         Category.NEUTRAL),
    "save":       ("fa5s.save",                Category.LOAD),
    "save_as":    ("fa5s.file-export",         Category.LOAD),
    "new":        ("fa5s.file",                Category.NEUTRAL),
    # Misc
    "warning":    ("fa5s.exclamation-triangle",Category.QC),
    "info":       ("fa5s.info-circle",         Category.NEUTRAL),
    "play":       ("fa5s.play",                Category.LOAD),
    "stop":       ("fa5s.stop",                Category.QC),
    "browse":     ("fa5s.ellipsis-h",          Category.NEUTRAL),
    "add":        ("fa5s.plus-circle",         Category.LOAD),
    "up":         ("fa5s.chevron-up",          Category.NEUTRAL),
    "down":       ("fa5s.chevron-down",        Category.NEUTRAL),
    "menu":       ("fa5s.ellipsis-v",          Category.NEUTRAL),
    "delete":     ("fa5s.times-circle",        Category.QC),
}


def _tint_for(category: Category | None) -> str:
    if category is None:
        # Default tint = a neutral foreground that reads on either theme.
        return "#cbd5e1" if resolved_mode() == "dark" else "#334155"
    return category_color(category)


def icon(name: str, category: Category | None = None) -> QIcon:
    """Return a themed QIcon for *name*.

    *name* is either a logical key (``"load"``) or an explicit qtawesome
    glyph (``"fa5s.folder-open"``).  *category* overrides the default
    tint registered for that key.
    """
    if name in _GLYPHS:
        glyph, default_category = _GLYPHS[name]
    else:
        glyph, default_category = name, None
    color = _tint_for(category if category is not None else default_category)
    return qta.icon(glyph, color=color)


def render_app_badge(size: int) -> QPixmap:
    """Render the application badge — a fly inside a tracking reticle — at *size* px."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)
    c = s / 2

    # Rounded-square badge background (dark slate, reads on any taskbar).
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1e293b"))
    corner = s * 0.22
    p.drawRoundedRect(QRectF(0, 0, s, s), corner, corner)

    # Tracking reticle: ring + N/S/E/W tick marks in the accent color.
    accent = QColor("#38bdf8")
    p.setPen(QPen(accent, max(1.0, s * 0.05)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    margin = s * 0.17
    p.drawEllipse(QRectF(margin, margin, s - 2 * margin, s - 2 * margin))
    r_ring = c - margin
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        p.drawLine(
            QPointF(c + dx * (r_ring - s * 0.06), c + dy * (r_ring - s * 0.06)),
            QPointF(c + dx * (r_ring + s * 0.06), c + dy * (r_ring + s * 0.06)),
        )

    # The fly, centered inside the reticle.
    glyph = s * 0.44
    bug_pm = qta.icon("fa5s.bug", color="#e2e8f0").pixmap(int(glyph), int(glyph))
    target = QRectF(c - glyph / 2, c - glyph / 2, glyph, glyph)
    p.drawPixmap(target, bug_pm, QRectF(bug_pm.rect()))
    p.end()
    return pm


def app_icon() -> QIcon:
    """Window/taskbar QIcon for all PyTrackingAnalysis apps, in multiple sizes."""
    ico = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ico.addPixmap(render_app_badge(size))
    return ico
