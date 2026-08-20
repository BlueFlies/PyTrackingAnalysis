"""Build the provider-agnostic input for an AI Summary.

The AI is given exactly what the report's reader sees (ADR-0004): the report
document model serialized to text, the report figures as PNG images, and the
small per-fly summary CSVs — never the rendered PDF and never raw per-frame
tracking data. This module walks the
:mod:`pytrackinganalysis.report.model` blocks; it imports no provider SDK.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Guardrails, not tuning knobs: a Valence report is well inside these. They
# only bite on a pathological project, where the note they leave in the text
# tells the model (and anyone reading a prompt dump) that content was dropped.
MAX_IMAGES = 16
MAX_CSV_CHARS = 100_000

#: The on-disk data files appended to the payload text. Per-fly summaries and
#: exclusions only — small by construction (one row per fly).
_CSV_SUFFIXES = ("_Summary.csv", "_Summary_Facet.csv", "_Excluded.csv")


@dataclass
class SummaryPayload:
    """What a provider gets to see: serialized report text + figure PNGs."""

    text: str = ""
    #: ``(title, png_bytes)`` per figure, in report order.
    images: list[tuple[str, bytes]] = field(default_factory=list)


def build_payload(experiment) -> SummaryPayload:
    """Serialize *experiment*'s report model (and summary CSVs) for the AI.

    The report model is built without any existing AI Summary so the new
    summary can never quote its predecessor (ADR-0004).
    """
    from ..report import model as _m

    report = experiment.build_report_model(include_ai_summary=False)
    lines: list[str] = []
    images: list[tuple[str, bytes]] = []
    dropped_images = 0

    for block in report.blocks:
        if isinstance(block, _m.Cover):
            lines.append(f"# {block.title}")
            if block.subtitle:
                lines.append(block.subtitle)
            for label, value in block.metadata:
                lines.append(f"{label}: {value}")
            for status in block.status_lines():
                lines.append(f"Status: {status.text}")
            lines.append("")
        elif isinstance(block, _m.SectionDivider):
            lines.append(f"\n=== {block.title} ===")
            if block.subtitle:
                lines.append(block.subtitle)
        elif isinstance(block, _m.Heading):
            lines.append(f"\n{'#' * max(1, block.level)} {block.text}")
        elif isinstance(block, _m.Paragraph):
            lines.append(block.text)
        elif isinstance(block, _m.Preformatted):
            if block.title:
                lines.append(f"\n--- {block.title} ---")
            lines.append(block.text.rstrip())
        elif isinstance(block, _m.Table):
            lines.append(f"\n[Table: {block.title or 'untitled'}]")
            if block.caption:
                lines.append(block.caption)
            lines.append(" | ".join(block.columns))
            for row in block.rows:
                lines.append(" | ".join(row))
        elif isinstance(block, _m.Figure):
            title = block.title or f"Figure {len(images) + dropped_images + 1}"
            if len(images) < MAX_IMAGES:
                images.append((title, block.data))
                ref = f"[Figure {len(images)}: {title}"
            else:
                dropped_images += 1
                ref = f"[Figure (image omitted): {title}"
            if block.caption:
                ref += f" — {block.caption}"
            lines.append(ref + "]")

    if dropped_images:
        lines.append(f"\n(Note: {dropped_images} additional figure image(s) "
                     f"were omitted from this input; only their titles are "
                     f"listed above.)")

    lines.extend(_csv_sections(experiment))
    return SummaryPayload(text="\n".join(lines).strip() + "\n", images=images)


def _csv_sections(experiment) -> list[str]:
    """The per-fly summary CSVs from ``analysis/``, as fenced text sections."""
    name = experiment.arena.experiment_name
    lines: list[str] = ["\n=== Data files (analysis/) ==="]
    found = False
    for suffix in _CSV_SUFFIXES:
        path = os.path.join(experiment.analysis_path, f"{name}{suffix}")
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except OSError:
            continue
        found = True
        lines.append(f"\n--- {name}{suffix} ---")
        if len(content) > MAX_CSV_CHARS:
            content = (content[:MAX_CSV_CHARS]
                       + "\n(… truncated for length …)")
        lines.append(content.rstrip())
    if not found:
        lines.append("(no summary CSVs found — run the analysis first)")
    return lines
