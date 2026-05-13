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
- `Focus`  — optional; surfaced in console output but not used by the renderer

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
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Dashboard:
    """One parsed dashboard markdown file."""

    title: str
    slug: str
    url: str
    source: Path


def discover_dashboards(dashboards_dir: Path) -> List[Path]:
    """Return sorted `*.md` paths in `dashboards_dir`, skipping `_*.md` templates.

    Returns an empty list if the directory does not exist — dashboards are
    optional, so missing directories are not an error.
    """
    if not dashboards_dir.is_dir():
        return []
    return sorted(
        p
        for p in dashboards_dir.glob("*.md")
        if p.is_file() and not p.name.startswith("_")
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

    title: Optional[str] = None
    fields: Dict[str, str] = {}

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
    )


def load_snapshot(slug: str, output_dir: Path) -> Optional[Dict[str, Any]]:
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
