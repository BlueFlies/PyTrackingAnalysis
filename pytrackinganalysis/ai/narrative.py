"""The AI narrative as a Markdown companion file.

The canonical saved narrative is ``<name>_AI_Summary.txt`` beside the other
analysis outputs — that is what the report embeds. This module writes the
same text a second time as ``ai_narrative.md``: a fixed filename, so a later
agent (or a plain ``grep -r``) can find every narrative in a tree without
knowing any project's or replicate's name, with enough front matter to say
what the prose is actually about.

It is a derivative of one analysis run, exactly like its ``.txt`` sibling
(ADR-0004), so it is deleted whenever that one is.
"""

from __future__ import annotations

import os

#: Fixed, name-independent — the point is that it globs.
AI_NARRATIVE_FILENAME = "ai_narrative.md"


def narrative_path(directory: str) -> str:
    return os.path.join(str(directory), AI_NARRATIVE_FILENAME)


def write_narrative_md(directory: str, *, title: str, level: str,
                       provider: str, model: str, stamp: str,
                       text: str, context: list[tuple[str, str]] | None = None,
                       ) -> str:
    """Write *text* as ``ai_narrative.md`` in *directory*; returns the path.

    *context* is rendered as a small table of facts (experiment type,
    replicate names, …) so the file stands on its own when something reads it
    without the surrounding directory for company.
    """
    path = narrative_path(directory)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lines = [
        f"# AI narrative — {title}",
        "",
        f"- **Level:** {level}",
        f"- **Generated:** {stamp}",
        f"- **Model:** {provider} {model}",
    ]
    for label, value in context or []:
        if value:
            lines.append(f"- **{label}:** {value}")
    lines += [
        "",
        "> Written by an AI model from this analysis run's own outputs, and "
        "embedded in the corresponding report. It describes that run only — "
        "re-running the analysis deletes it.",
        "",
        "---",
        "",
        text.strip(),
        "",
    ]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return path


def delete_narrative_md(directory: str) -> None:
    try:
        os.remove(narrative_path(directory))
    except (FileNotFoundError, NotADirectoryError):
        pass
