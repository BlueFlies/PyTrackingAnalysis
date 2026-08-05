"""Backend-agnostic document model for analysis reports.

This module is the contract between the analysis core and whatever engine
renders the report. It deliberately imports **nothing** from the analysis code
and **nothing** from any rendering library (reportlab, LaTeX, markdown, …).

A report is an ordered list of typed *blocks*. The analysis side builds this
structure from its data; a *backend* (see :mod:`pytrackinganalysis.report.render`)
walks the blocks and produces a file. Swapping reportlab for a LaTeX or Markdown
engine means writing a new backend over these same blocks — the analysis core
never changes.

Design rules for anything added here:

* Pure data only — dataclasses of primitives, ``bytes``, and other blocks.
* No imports of matplotlib/reportlab/pandas. A :class:`Figure` carries already
  rendered image *bytes*, not a live matplotlib figure, so the model stays
  independent of how plots are drawn.
* Semantic, not presentational — a table row carries a :class:`Level`
  ("this row is good/bad"), never a hex color. Backends own the styling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Level(str, Enum):
    """Semantic emphasis for status lines and table rows.

    Backends map these to their own palette; the model never names a color.
    """

    NEUTRAL = "neutral"
    OK = "ok"
    WARN = "warn"
    ERROR = "error"


# --------------------------------------------------------------------------
# Blocks
# --------------------------------------------------------------------------


@dataclass
class StatusLine:
    """A short, emphasis-colored one-liner (e.g. the QC pass/fail summary)."""

    text: str
    level: Level = Level.NEUTRAL


@dataclass
class Cover:
    """Title page. ``metadata`` renders as a label/value block."""

    title: str
    subtitle: str = ""
    metadata: list[tuple[str, str]] = field(default_factory=list)
    status: StatusLine | None = None


@dataclass
class SectionDivider:
    """A full-page divider that opens a major section."""

    title: str
    subtitle: str = ""


@dataclass
class Heading:
    """An in-flow heading. ``level`` 1..3 (1 = largest)."""

    text: str
    level: int = 1


@dataclass
class Paragraph:
    """A run of ordinary prose."""

    text: str


@dataclass
class Preformatted:
    """Monospaced, whitespace-preserving text (e.g. a ``*_Stats.txt`` dump)."""

    text: str
    title: str | None = None


@dataclass
class Table:
    """A tabular block.

    ``rows`` are pre-stringified cells (the analysis side decides number
    formatting). ``row_levels``, if given, is one :class:`Level` per body row
    for semantic tinting (e.g. quality thresholds); an empty list means no
    tinting. Backends are responsible for wrapping/splitting to fit the page.
    """

    columns: list[str]
    rows: list[list[str]]
    title: str | None = None
    caption: str | None = None
    row_levels: list[Level | None] = field(default_factory=list)


@dataclass
class Figure:
    """A rendered plot, carried as image bytes so the model stays engine-free.

    ``width_in``/``height_in`` are the figure's intrinsic size in inches; a
    backend scales to fit its frame while preserving that aspect ratio.
    """

    data: bytes
    fmt: str = "png"  # "png" today; "svg"/"pdf" possible for a vector backend
    width_in: float = 6.5
    height_in: float = 4.0
    title: str | None = None
    caption: str | None = None


@dataclass
class PageBreak:
    """Force the following block onto a new page."""


# A block is any of the above. Kept as a plain tuple for isinstance dispatch
# in backends without importing each name individually.
BLOCK_TYPES = (
    Cover,
    SectionDivider,
    Heading,
    Paragraph,
    Preformatted,
    Table,
    Figure,
    PageBreak,
)


@dataclass
class Report:
    """An ordered document: a title plus a list of blocks.

    Build it with :meth:`add`; hand it to a backend to render::

        report = Report("MyExperiment")
        report.add(Cover(...)).add(SectionDivider("Analysis"))
        render(report, "out.pdf")            # backend="reportlab" by default
    """

    title: str
    blocks: list = field(default_factory=list)

    def add(self, block) -> "Report":
        """Append a block and return ``self`` so calls can chain."""
        self.blocks.append(block)
        return self

    def extend(self, blocks) -> "Report":
        """Append several blocks in order."""
        for block in blocks:
            self.blocks.append(block)
        return self
