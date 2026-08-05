"""Load packaged markdown and convert a small subset to HTML for QTextBrowser."""

from __future__ import annotations

import html
import re
from importlib import resources

from .topics import HelpTopic, get_topic


def load_topic_markdown(topic_id: str) -> str:
    topic = get_topic(topic_id)
    root = resources.files("pytrackinganalysis.help")
    path = root.joinpath("content", topic.filename)
    return path.read_text(encoding="utf-8")


def md_to_html(md: str) -> str:
    """Convert a limited markdown dialect to HTML.

    Supports: ATX headings (#–###), fenced code blocks, unordered/ordered lists,
    paragraphs, inline ``code``, **bold**, *italic*, and [links](url).
    """
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_ul = False
    in_ol = False
    in_code = False
    code_buf: list[str] = []

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            if in_code:
                close_lists()
                escaped = html.escape("\n".join(code_buf))
                out.append(f"<pre><code>{escaped}</code></pre>")
                code_buf = []
                in_code = False
            else:
                close_lists()
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if not line.strip():
            close_lists()
            i += 1
            continue

        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            close_lists()
            level = len(heading.group(1))
            text = _inline(heading.group(2).strip())
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        ul = re.match(r"^[-*]\s+(.*)$", line)
        if ul:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(ul.group(1).strip())}</li>")
            i += 1
            continue

        ol = re.match(r"^(\d+)\.\s+(.*)$", line)
        if ol:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_inline(ol.group(2).strip())}</li>")
            i += 1
            continue

        close_lists()
        # Merge consecutive non-blank, non-structural lines into one paragraph.
        para = [line.strip()]
        while i + 1 < len(lines):
            nxt = lines[i + 1]
            if (
                not nxt.strip()
                or nxt.startswith("```")
                or re.match(r"^#{1,3}\s+", nxt)
                or re.match(r"^[-*]\s+", nxt)
                or re.match(r"^\d+\.\s+", nxt)
            ):
                break
            para.append(nxt.strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")
        i += 1

    close_lists()
    if in_code:
        escaped = html.escape("\n".join(code_buf))
        out.append(f"<pre><code>{escaped}</code></pre>")

    body = "\n".join(out)
    return (
        "<html><head><meta charset='utf-8'/>"
        "<style>"
        "body { font-family: sans-serif; font-size: 13px; line-height: 1.45; }"
        "h1 { font-size: 18px; margin: 0.4em 0 0.5em; }"
        "h2 { font-size: 15px; margin: 1em 0 0.4em; }"
        "h3 { font-size: 13px; margin: 0.8em 0 0.3em; }"
        "code, pre { font-family: Consolas, monospace; font-size: 12px; }"
        "pre { background: palette(alternate-base); padding: 8px; "
        "border-radius: 4px; overflow-x: auto; }"
        "ul, ol { margin: 0.4em 0 0.6em 1.2em; }"
        "li { margin: 0.2em 0; }"
        "p { margin: 0.45em 0; }"
        "</style></head><body>"
        f"{body}</body></html>"
    )


def topic_html(topic_id: str) -> str:
    return md_to_html(load_topic_markdown(topic_id))


def topic_title(topic: HelpTopic | str) -> str:
    if isinstance(topic, str):
        topic = get_topic(topic)
    return topic.title


_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline(text: str) -> str:
    # Escape first, then re-introduce intentional tags from markdown markers.
    text = html.escape(text)
    text = _LINK.sub(r'<a href="\2">\1</a>', text)
    text = _INLINE_CODE.sub(r"<code>\1</code>", text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    return text
