"""Report subsystem: a backend-agnostic document model plus pluggable renderers.

The analysis core builds a :class:`~pytrackinganalysis.report.model.Report` out
of the block types in :mod:`~pytrackinganalysis.report.model` and hands it to
:func:`~pytrackinganalysis.report.render.render`. The rendering engine
(currently reportlab) lives entirely behind that call, so it can be replaced —
by a LaTeX or Markdown backend, say — without touching any analysis code.
"""

from . import model
from .model import (
    Cover,
    Figure,
    Heading,
    Level,
    PageBreak,
    Paragraph,
    Preformatted,
    Report,
    SectionDivider,
    StatusLine,
    Table,
)
from .render import available_backends, render

__all__ = [
    "model",
    "Report",
    "Cover",
    "SectionDivider",
    "Heading",
    "Paragraph",
    "Preformatted",
    "Table",
    "Figure",
    "PageBreak",
    "StatusLine",
    "Level",
    "render",
    "available_backends",
]
