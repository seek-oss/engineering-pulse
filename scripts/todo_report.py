"""
Todoist queue helpers for HTML email reports — view links only.

Each task / reading item gets a stable Todoist web URL. No signing, no worker.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List


def build_view_url(task_id: str) -> str:
    """Todoist web UI for this task."""
    tid = (task_id or "").strip()
    return f"https://app.todoist.com/app/task/{tid}" if tid else ""


def enrich_json_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add ``view_url`` to each row (for ``todo.py list --json``)."""
    out: List[Dict[str, Any]] = []
    for row in items:
        r = dict(row)
        tid = str(r.get("id", "")).strip()
        r["view_url"] = build_view_url(tid)
        out.append(r)
    return out


def format_view_action_html(item: Dict[str, Any]) -> str:
    """
    Email-safe HTML for Part D Actions column: single **View** link to Todoist.
    """
    url = str(item.get("view_url") or "").strip() or build_view_url(str(item.get("id", "")))
    if not url:
        return '<span style="color:#a0aec0">—</span>'
    return f'<a href="{html.escape(url, quote=True)}">View</a>'
