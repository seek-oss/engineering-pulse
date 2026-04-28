"""Drop-in extras plugin for the daily dashboard.

Any `*.md` file dropped into `prompts/extras/` (except files starting with `_`,
which are reference templates) is rendered as an extra task card in the daily
report.

File format
-----------
The first level-1 heading (`# Title`) becomes the card title. Everything below
is rendered with a small, dependency-free markdown subset:

- Headings: `#`, `##`, `###`
- Bold (`**text**`), italic (`*text*`), inline code (`` `code` ``)
- Bullet lists (`-`, `*`, `+`) and numbered lists (`1.`)
- Links (`[text](url)`)
- Fenced code blocks (```)
- Paragraphs separated by blank lines

If the file has no `# Heading`, the filename (without extension) is used as the
title and the entire body is rendered.

This module deliberately has no third-party dependencies — it is tested and
called directly from `render_daily_dashboard_html.py`.
"""

from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Extra:
    """One parsed extra-task markdown file."""

    title: str
    body_html: str
    source: Path


def discover_extras(extras_dir: Path) -> List[Path]:
    """Return sorted `*.md` paths in `extras_dir`, skipping `_*.md` templates.

    Returns an empty list if the directory does not exist — extras are
    optional, so missing directories are not an error.
    """
    if not extras_dir.is_dir():
        return []
    return sorted(
        p
        for p in extras_dir.glob("*.md")
        if p.is_file() and not p.name.startswith("_")
    )


def parse_extra(path: Path) -> Extra:
    """Parse a single extras `.md` file into title + rendered HTML body."""
    raw = path.read_text(encoding="utf-8")
    title, body = _split_title(raw, fallback=path.stem)
    return Extra(title=title, body_html=markdown_to_html(body), source=path)


def _split_title(raw: str, *, fallback: str) -> tuple[str, str]:
    """Split out the first `# Heading` as title; rest is the body.

    If no level-1 heading exists, returns (`fallback`, `raw`). The fallback is
    typically the file stem so the user always sees something sensible.
    """
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("# "):
            title = line.lstrip()[2:].strip() or fallback
            body = "\n".join(lines[i + 1 :]).strip("\n")
            return title, body
    return fallback, raw


# ── Minimal markdown → HTML ─────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^\d+\.\s+(.*)$")
_CODE_FENCE_RE = re.compile(r"^```")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_AUTOLINK_RE = re.compile(r"(?<![\"'=>])(https?://[^\s<\"')]+)")
_LINK_PLACEHOLDER = "\x00LINK{}\x00"


def markdown_to_html(text: str) -> str:
    """Convert a markdown-ish block to safe HTML.

    All raw HTML in the source is escaped first; only our own generated tags
    survive. This keeps untrusted markdown drop-ins safe to embed in the email.
    """
    if not text.strip():
        return ""

    out: List[str] = []
    in_ul = False
    in_ol = False
    in_code = False
    code_buf: List[str] = []
    para_buf: List[str] = []

    def flush_para() -> None:
        if para_buf:
            out.append(f"<p>{_inline(' '.join(para_buf))}</p>")
            para_buf.clear()

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if _CODE_FENCE_RE.match(stripped):
            flush_para()
            close_lists()
            if in_code:
                out.append(
                    "<pre><code>"
                    + html_mod.escape("\n".join(code_buf))
                    + "</code></pre>"
                )
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_buf.append(raw_line)
            continue

        if not stripped:
            flush_para()
            close_lists()
            continue

        m = _HEADING_RE.match(stripped)
        if m:
            flush_para()
            close_lists()
            level = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
            continue

        m = _UL_RE.match(stripped)
        if m:
            flush_para()
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue

        m = _OL_RE.match(stripped)
        if m:
            flush_para()
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue

        close_lists()
        para_buf.append(stripped)

    flush_para()
    close_lists()
    if in_code:
        out.append(
            "<pre><code>" + html_mod.escape("\n".join(code_buf)) + "</code></pre>"
        )

    return "\n".join(out)


def _inline(text: str) -> str:
    """Apply inline formatting (escape, code, bold, italic, links).

    Explicit `[text](url)` links are stashed as placeholders before the
    autolink pass so we never double-wrap a URL that already lives inside
    an explicit link's `href` attribute.
    """
    s = html_mod.escape(text, quote=True)
    s = _INLINE_CODE_RE.sub(r"<code>\1</code>", s)
    s = _BOLD_RE.sub(r"<strong>\1</strong>", s)
    s = _ITALIC_RE.sub(r"<em>\1</em>", s)

    stash: List[str] = []

    def link_repl(m: re.Match[str]) -> str:
        stash.append(f'<a href="{m.group(2)}">{m.group(1)}</a>')
        return _LINK_PLACEHOLDER.format(len(stash) - 1)

    s = _LINK_RE.sub(link_repl, s)
    s = _AUTOLINK_RE.sub(r'<a href="\1">\1</a>', s)
    for i, snippet in enumerate(stash):
        s = s.replace(_LINK_PLACEHOLDER.format(i), snippet)
    return s


# ── Section rendering ──────────────────────────────────────────────────────


def render_extras_section(
    extras_dir: Path, *, label: str = "Part E — Extras"
) -> Optional[str]:
    """Render the full extras section HTML, or `None` if no extras present.

    Callers can inline the returned string directly into the report. Returning
    `None` (rather than an empty string) lets the caller omit the section
    entirely when no plugin files exist, keeping the report tight.
    """
    paths = discover_extras(extras_dir)
    if not paths:
        return None

    cards: List[str] = []
    for p in paths:
        extra = parse_extra(p)
        cards.append(
            '<div class="extra-card">'
            f'<div class="extra-title">{html_mod.escape(extra.title)}</div>'
            f'<div class="extra-body">{extra.body_html}</div>'
            "</div>"
        )

    return (
        f'<div class="section-title">{html_mod.escape(label)}</div>\n    '
        + "\n    ".join(cards)
    )
