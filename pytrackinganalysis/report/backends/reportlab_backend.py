"""reportlab renderer for the :mod:`pytrackinganalysis.report.model` document.

This is the only module that knows about reportlab. It walks a :class:`Report`
of backend-agnostic blocks and produces a letter-size PDF with a consistent
visual system: a cover page, full-page section dividers, wrapped monospaced
text, paginated tables that never run off the page, and figures scaled to the
content frame.

To add a different engine (LaTeX, Markdown, …), write a sibling module with the
same ``render(report, path)`` entry point over the same blocks — nothing here
leaks into the analysis core.
"""

from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    TableStyle,
)

from .. import model as m

# --------------------------------------------------------------------------
# Palette — one place, so the whole document reads as a single system.
# --------------------------------------------------------------------------
_INK = colors.HexColor("#0f172a")
_SUBTLE = colors.HexColor("#475569")
_MUTED = colors.HexColor("#64748b")
_HAIR = colors.HexColor("#cbd5e1")
_HAIR_SOFT = colors.HexColor("#e2e8f0")
_HEADER_BG = colors.HexColor("#1f2937")
_ROW_ALT = colors.HexColor("#f8fafc")

_LEVEL_TEXT = {
    m.Level.OK: colors.HexColor("#16a34a"),
    m.Level.WARN: colors.HexColor("#d97706"),
    m.Level.ERROR: colors.HexColor("#dc2626"),
    m.Level.NEUTRAL: _SUBTLE,
}
_LEVEL_ROW_BG = {
    m.Level.OK: colors.HexColor("#dcfce7"),
    m.Level.WARN: colors.HexColor("#fef9c3"),
    m.Level.ERROR: colors.HexColor("#fee2e2"),
}

_MARGIN = 0.7 * inch
_PAGE_W, _PAGE_H = letter
_CONTENT_W = _PAGE_W - 2 * _MARGIN
_CONTENT_H = _PAGE_H - 2 * _MARGIN
# Longest monospaced line (in characters) that fits the content width before we
# soft-wrap it. Courier is 0.6em wide; at 8pt that is 4.8pt/char.
_MONO_FONT_SIZE = 8
_MONO_WRAP = int(_CONTENT_W / (_MONO_FONT_SIZE * 0.6)) - 1


def _styles():
    """Build the paragraph styles used across the document."""
    base = getSampleStyleSheet()
    styles = {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"], fontSize=28, leading=32,
            textColor=_INK, alignment=TA_CENTER, spaceAfter=6),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle", parent=base["Normal"], fontSize=14, leading=18,
            textColor=_MUTED, alignment=TA_CENTER),
        "cover_meta_label": ParagraphStyle(
            "cover_meta_label", parent=base["Normal"], fontSize=10, leading=15,
            textColor=_MUTED, fontName="Helvetica-Bold"),
        "cover_meta_value": ParagraphStyle(
            "cover_meta_value", parent=base["Normal"], fontSize=10, leading=15,
            textColor=_INK, fontName="Courier"),
        "cover_status": ParagraphStyle(
            "cover_status", parent=base["Normal"], fontSize=12, leading=16,
            alignment=TA_CENTER, fontName="Helvetica-Bold"),
        "divider": ParagraphStyle(
            "divider", parent=base["Title"], fontSize=40, leading=46,
            textColor=_INK, alignment=TA_CENTER),
        "divider_sub": ParagraphStyle(
            "divider_sub", parent=base["Normal"], fontSize=13, leading=18,
            textColor=_MUTED, alignment=TA_CENTER),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontSize=15, leading=19,
            textColor=_INK, spaceBefore=10, spaceAfter=4),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=12, leading=16,
            textColor=_INK, spaceBefore=8, spaceAfter=3),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], fontSize=10.5, leading=14,
            textColor=_SUBTLE, spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=10, leading=14,
            textColor=_INK, spaceAfter=6),
        "caption": ParagraphStyle(
            "caption", parent=base["Normal"], fontSize=8.5, leading=11,
            textColor=_MUTED, alignment=TA_CENTER, spaceBefore=3),
        "block_title": ParagraphStyle(
            "block_title", parent=base["Heading2"], fontSize=11, leading=15,
            textColor=_INK, spaceBefore=6, spaceAfter=3),
        "mono": ParagraphStyle(
            "mono", parent=base["Code"], fontSize=_MONO_FONT_SIZE,
            leading=_MONO_FONT_SIZE + 2, textColor=_INK),
        "cell": ParagraphStyle(
            "cell", parent=base["Normal"], fontSize=7.5, leading=9,
            textColor=_INK, alignment=TA_LEFT),
        "cell_head": ParagraphStyle(
            "cell_head", parent=base["Normal"], fontSize=7.5, leading=9,
            textColor=colors.white, fontName="Helvetica-Bold",
            alignment=TA_LEFT),
    }
    return styles


class _Doc(BaseDocTemplate):
    """Letter document with a single content frame and a running footer."""

    def __init__(self, path, title):
        super().__init__(
            path, pagesize=letter,
            leftMargin=_MARGIN, rightMargin=_MARGIN,
            topMargin=_MARGIN, bottomMargin=_MARGIN,
            title=title, author="PyTrackingAnalysis",
        )
        self._doc_title = title
        frame = Frame(
            _MARGIN, _MARGIN, _CONTENT_W, _CONTENT_H, id="content",
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        self.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                            onPage=self._footer)])

    def _footer(self, canvas, doc):
        # Page 1 is the cover — leave it clean.
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(_HAIR_SOFT)
        canvas.setLineWidth(0.5)
        y = _MARGIN - 0.18 * inch
        canvas.line(_MARGIN, y, _PAGE_W - _MARGIN, y)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(_MUTED)
        canvas.drawString(_MARGIN, y - 0.14 * inch, self._doc_title)
        canvas.drawRightString(_PAGE_W - _MARGIN, y - 0.14 * inch,
                               f"Page {doc.page}")
        canvas.restoreState()


# --------------------------------------------------------------------------
# Block → flowables
# --------------------------------------------------------------------------


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _wrap_mono(text: str) -> str:
    """Soft-wrap long monospaced lines so nothing runs past the frame."""
    import textwrap

    out = []
    for line in (text or "").splitlines() or [""]:
        if len(line) <= _MONO_WRAP:
            out.append(line)
        else:
            wrapped = textwrap.wrap(
                line, width=_MONO_WRAP, break_long_words=True,
                break_on_hyphens=False, subsequent_indent="    ",
            )
            out.extend(wrapped or [""])
    return "\n".join(out)


def _cover_flowables(block: m.Cover, styles) -> list:
    flow = [Spacer(1, 1.6 * inch),
            Paragraph(_xml_escape(block.title), styles["cover_title"])]
    if block.subtitle:
        flow.append(Paragraph(_xml_escape(block.subtitle), styles["cover_subtitle"]))
    flow.append(Spacer(1, 0.5 * inch))

    if block.metadata:
        rows = [[Paragraph(_xml_escape(f"{label}:"), styles["cover_meta_label"]),
                 Paragraph(_xml_escape(str(value)), styles["cover_meta_value"])]
                for label, value in block.metadata]
        meta = LongTable(rows, colWidths=[1.8 * inch, _CONTENT_W - 1.8 * inch])
        meta.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        # Center the metadata block within the page.
        holder = LongTable([[meta]], colWidths=[_CONTENT_W])
        holder.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        flow.append(holder)

    if block.status is not None:
        flow.append(Spacer(1, 0.6 * inch))
        style = ParagraphStyle("status_col", parent=styles["cover_status"],
                               textColor=_LEVEL_TEXT.get(block.status.level, _SUBTLE))
        flow.append(Paragraph(_xml_escape(block.status.text), style))

    # No trailing PageBreak: the following SectionDivider carries a leading one,
    # so ending the cover here too would leave an empty page between them.
    return flow


def _divider_flowables(block: m.SectionDivider, styles) -> list:
    flow = [PageBreak(), Spacer(1, 3.6 * inch),
            Paragraph(_xml_escape(block.title), styles["divider"])]
    if block.subtitle:
        flow.append(Spacer(1, 0.1 * inch))
        flow.append(Paragraph(_xml_escape(block.subtitle), styles["divider_sub"]))
    flow.append(PageBreak())
    return flow


def _table_flowables(block: m.Table, styles) -> list:
    flow = []
    if block.title:
        flow.append(Paragraph(_xml_escape(block.title), styles["block_title"]))

    ncols = max(1, len(block.columns))
    col_w = _CONTENT_W / ncols
    header = [Paragraph(_xml_escape(str(c)), styles["cell_head"]) for c in block.columns]
    body = [[Paragraph(_xml_escape(str(c)), styles["cell"]) for c in row]
            for row in block.rows]
    data = [header] + body

    tbl = LongTable(data, colWidths=[col_w] * ncols, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _HEADER_BG),
        ("GRID", (0, 1), (-1, -1), 0.25, _HAIR_SOFT),
    ]
    # Row backgrounds: semantic level if given, else zebra striping.
    levels = block.row_levels or []
    for i in range(len(body)):
        level = levels[i] if i < len(levels) else None
        if level is not None and level in _LEVEL_ROW_BG:
            bg = _LEVEL_ROW_BG[level]
        else:
            bg = _ROW_ALT if i % 2 == 0 else colors.white
        style.append(("BACKGROUND", (0, i + 1), (-1, i + 1), bg))
    tbl.setStyle(TableStyle(style))
    flow.append(tbl)

    if block.caption:
        flow.append(Paragraph(_xml_escape(block.caption), styles["caption"]))
    flow.append(Spacer(1, 0.12 * inch))
    return flow


def _figure_flowables(block: m.Figure, styles) -> list:
    aspect = (block.height_in / block.width_in) if block.width_in else 0.75
    width = _CONTENT_W
    height = width * aspect
    # Cap the height to roughly half the content area so figures pack about two
    # per page instead of one near-square figure eating a whole page. Wide
    # multi-panel figures stay full width; tall/near-square ones shrink and
    # centre. KeepTogether keeps each figure's title+image+caption as a unit.
    max_h = 4.6 * inch
    if height > max_h:
        height = max_h
        width = height / aspect if aspect else _CONTENT_W

    img = Image(io.BytesIO(block.data), width=width, height=height)
    img.hAlign = "CENTER"

    # Title, image and caption travel together, so a title can never be orphaned
    # at the foot of a page while its figure flows to the next.
    parts = []
    if block.title:
        parts.append(Paragraph(_xml_escape(block.title), styles["block_title"]))
    parts.append(img)
    if block.caption:
        parts.append(Paragraph(_xml_escape(block.caption), styles["caption"]))
    return [KeepTogether(parts), Spacer(1, 0.15 * inch)]


def _blocks_to_flowables(report: m.Report, styles) -> list:
    flow: list = []
    for block in report.blocks:
        if isinstance(block, m.Cover):
            flow += _cover_flowables(block, styles)
        elif isinstance(block, m.SectionDivider):
            flow += _divider_flowables(block, styles)
        elif isinstance(block, m.Heading):
            key = {1: "h1", 2: "h2", 3: "h3"}.get(block.level, "h3")
            flow.append(Paragraph(_xml_escape(block.text), styles[key]))
        elif isinstance(block, m.Paragraph):
            flow.append(Paragraph(_xml_escape(block.text), styles["body"]))
        elif isinstance(block, m.Preformatted):
            if block.title:
                flow.append(Paragraph(_xml_escape(block.title), styles["block_title"]))
            flow.append(Preformatted(_wrap_mono(block.text), styles["mono"]))
            flow.append(Spacer(1, 0.12 * inch))
        elif isinstance(block, m.Table):
            flow += _table_flowables(block, styles)
        elif isinstance(block, m.Figure):
            flow += _figure_flowables(block, styles)
        elif isinstance(block, m.PageBreak):
            flow.append(PageBreak())
        # Unknown blocks are silently skipped — forward-compatible with new
        # block types a newer analysis core might emit.
    return flow


def render(report: m.Report, path: str) -> str:
    """Render *report* to a PDF at *path* and return *path*."""
    styles = _styles()
    doc = _Doc(path, report.title)
    doc.build(_blocks_to_flowables(report, styles))
    return path
