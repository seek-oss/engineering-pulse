"""Drop-in dashboards plugin for the daily report.

Every `*.md` file under `prompts/dashboards/` (except files starting with `_`,
which are reference templates) declares one Datadog dashboard to render as a
Part section in the daily report.

File format
-----------
The first level-1 heading (`# Title`) becomes the section title. The body is
a bullet list with bolded keys:

    # My Dashboard

    - **URL:** `https://app.datadoghq.com/dashboard/abc-xyz/...`
    - **Slug:** `my_dashboard`
    - **Focus:** `Some Widget Title, Another Widget`

Recognised keys (case-insensitive on the key, value taken verbatim after
stripping surrounding whitespace and backticks):

- `URL`    — Datadog dashboard URL (used for the header link; missing → no link)
- `Slug`   — output-file prefix used by `datadog_dashboard_extract.py --output-slug`
- `Focus`  — optional comma-separated widget-title fragments. When set, the
  HTML report shows only the first matching widget for each fragment.
  `(none)` means no filter. A colour table (`RED` / `YELLOW` / `GREEN`) in the
  same file sets tile colours for those metrics.

The snapshot JSON for slug `<x>` is expected at `output/<x>_metric_results.json`
(matching what `scripts/datadog_dashboard_extract.py` writes). If the snapshot
is missing, `load_snapshot()` returns `None` so callers can skip the dashboard
with a warning rather than crashing.

This module deliberately has no third-party dependencies — it is tested and
called directly from `render_daily_dashboard_html.py`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ColorRule:
    """One row of a dashboard markdown colour table."""

    label: str
    red: str
    yellow: str
    green: str


@dataclass(frozen=True)
class Dashboard:
    """One parsed dashboard markdown file."""

    title: str
    slug: str
    url: str
    source: Path
    focus: tuple[str, ...] = ()
    color_rules: tuple[ColorRule, ...] = ()


_NO_FOCUS = {"", "(none)", "none", "n/a", "—", "-"}


def _parse_focus(raw: str) -> tuple[str, ...]:
    if raw.strip().lower() in _NO_FOCUS:
        return ()
    parts = []
    for part in raw.split(","):
        item = part.strip()
        if item and item.lower() not in _NO_FOCUS:
            parts.append(item)
    return tuple(parts)


def _parse_color_rules(text: str) -> tuple[ColorRule, ...]:
    rules: list[ColorRule] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        label = cells[0]
        if label.lower() == "metric" or set(label) <= {"-", ":"}:
            continue
        rules.append(ColorRule(label, cells[1], cells[2], cells[3]))
    return tuple(rules)


def discover_dashboards(dashboards_dir: Path) -> list[Path]:
    """Return sorted `*.md` paths in `dashboards_dir`, skipping `_*.md` templates.

    Returns an empty list if the directory does not exist — dashboards are
    optional, so missing directories are not an error.
    """
    if not dashboards_dir.is_dir():
        return []
    return sorted(
        p for p in dashboards_dir.glob("*.md") if p.is_file() and not p.name.startswith("_")
    )


_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$")
# Bullet field: e.g. "- **URL:** `https://...`" or "* **Slug** foo".
# The colon may sit either inside the bold (`**URL:**`) or outside (`**URL**:`).
_FIELD_RE = re.compile(
    r"""^\s*[-*+]\s+              # bullet marker
        \*\*\s*([^*\n]+?)\s*\*\*  # bolded key (group 1) — any non-asterisk text
        \s*:?\s*                  # optional colon after the bold
        (.*?)\s*$                 # value (group 2), trimmed
    """,
    re.VERBOSE,
)


def _strip_value(raw: str) -> str:
    """Trim wrapping backticks/quotes and surrounding whitespace from a field value."""
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {"`", '"', "'"}:
        v = v[1:-1].strip()
    return v


def parse_dashboard(path: Path) -> Dashboard:
    """Parse a dashboard `.md` file into a `Dashboard` record.

    Falls back to the file stem for the title and slug when those are not
    declared.
    """
    raw = path.read_text(encoding="utf-8")

    title: str | None = None
    fields: dict[str, str] = {}

    for line in raw.splitlines():
        if title is None:
            m = _H1_RE.match(line)
            if m:
                title = m.group(1).strip()
                continue
        m = _FIELD_RE.match(line)
        if m:
            key = m.group(1).strip().rstrip(":").strip().lower()
            fields[key] = _strip_value(m.group(2))

    return Dashboard(
        title=title or path.stem,
        slug=fields.get("slug") or path.stem,
        url=fields.get("url", ""),
        source=path,
        focus=_parse_focus(fields.get("focus", "")),
        color_rules=_parse_color_rules(raw),
    )


def load_snapshot(slug: str, output_dir: Path) -> dict[str, Any] | None:
    """Return the parsed `<slug>_metric_results.json`, or `None` if missing.

    The extract script writes this file with shape::

        {
          "dashboard_title": "...",
          "source_url": "...",
          "generated_at": "...",
          "results": [...]
        }

    A missing file is not an error: the caller can render a grey "no data"
    placeholder or skip the section. An unreadable file (bad JSON) raises.
    """
    path = output_dir / f"{slug}_metric_results.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
