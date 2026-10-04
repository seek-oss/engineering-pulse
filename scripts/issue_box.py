#!/usr/bin/env python3
"""The red problems box at the top of a report, and the fallback report frame.

Inline styles only: the box is injected into reports written by different tools
(the pulse renderer, agent-written sprint and compare HTML) and into email.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from urllib.parse import urlencode

MARKER = "data-ep-issues"
TYPE_LABELS = {"pulse": "Engineering Pulse", "sprint": "Sprint report", "compare": "Comparison"}
RERUN_TYPES = ("pulse", "sprint")

_BOX_RE = re.compile(rf"<div {MARKER}[\s\S]*?<!--/ep-issues-->", re.IGNORECASE)
_BODY_OPEN_RE = re.compile(r"<body\b[^>]*>", re.IGNORECASE)

_BUTTON = (
    "display:inline-block;margin:6px 8px 0 0;padding:6px 14px;border-radius:6px;"
    "background:#c53030;color:#fff;font-weight:700;font-size:13px;text-decoration:none"
)


def _link(params: dict[str, str], action: str) -> str:
    return f"engineering-pulse://{action}?{urlencode(params)}"


def auth_link(agent: str, server: str) -> str:
    return _link({"agent": agent, "server": server}, "auth")


def rerun_link(report_type: str) -> str:
    return _link({"type": report_type}, "run")


def _row(issue: dict) -> str:
    source = html.escape(str(issue.get("source") or "run").capitalize())
    message = html.escape(str(issue.get("message") or ""))
    fix = issue.get("fix") or {}
    button = ""
    if fix.get("kind") == "mcp_login" and fix.get("server") and fix.get("agent"):
        href = html.escape(auth_link(fix["agent"], fix["server"]))
        server = html.escape(fix["server"])
        button = f'<br><a href="{href}" style="{_BUTTON}">Sign in to {server}</a>'
    return (
        '<li style="margin:8px 0;line-height:1.5">'
        f"<strong>{source}:</strong> {message}{button}</li>"
    )


def render_issue_box(issues: list[dict], report_type: str) -> str:
    """Red box listing this run's problems; empty string when there are none."""
    if not issues:
        return ""
    count = len(issues)
    heading = f"{count} problem{'s' if count != 1 else ''} in this run"
    fixable = any((i.get("fix") or {}).get("kind") for i in issues)
    footer = ""
    if fixable and report_type in RERUN_TYPES:
        href = html.escape(rerun_link(report_type))
        footer = (
            f'<p style="margin:12px 0 0"><a href="{href}" style="{_BUTTON}">'
            "Re-run this report</a> after signing in.</p>"
        )
    if fixable:
        footer += (
            '<p style="margin:8px 0 0;font-size:12px;color:#9b2c2c">'
            "Buttons work when this report is opened on the Mac where Engineering Pulse "
            "is installed.</p>"
        )
    rows = "".join(_row(i) for i in issues)
    return (
        f"<div {MARKER} "
        'style="max-width:900px;margin:16px auto;padding:16px 20px;background:#fff5f5;'
        "border:2px solid #fc8181;border-left-width:8px;border-radius:10px;color:#742a2a;"
        'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">'
        f'<div style="font-size:17px;font-weight:800;color:#c53030">{heading}</div>'
        '<div style="font-size:13px;margin-top:2px">Sections below show everything that '
        "could still be generated.</div>"
        f'<ul style="margin:10px 0 0;padding-left:20px;font-size:14px">{rows}</ul>'
        f"{footer}</div><!--/ep-issues-->"
    )


def inject(page: str, box: str) -> str:
    """Put ``box`` right after <body>, replacing any earlier box (idempotent)."""
    page = _BOX_RE.sub("", page)
    if not box:
        return page
    if m := _BODY_OPEN_RE.search(page):
        return page[: m.end()] + box + page[m.end() :]
    return box + page


def fallback_report(report_type: str, issues: list[dict], when: datetime | None = None) -> str:
    """A complete report page for a run whose agent produced nothing."""
    when = when or datetime.now()
    label = TYPE_LABELS.get(report_type, "Report")
    title = html.escape(f"{label} — {when:%Y-%m-%d} (incomplete)")
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>{title}</title></head>"
        '<body style="margin:0;background:#f7fafc;font-family:-apple-system,'
        'BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;color:#1a202c">'
        '<div style="max-width:900px;margin:0 auto;padding:24px 20px 0">'
        f'<h1 style="font-size:22px;margin:0">{title}</h1>'
        f'<div style="color:#718096;font-size:13px;margin-top:4px">'
        f"Generated {when:%a %-d %b %Y %H:%M}</div></div>"
        f"{render_issue_box(issues, report_type)}"
        '<div style="max-width:900px;margin:0 auto;padding:0 20px 24px;color:#718096">'
        "No sections could be generated this run.</div>"
        "</body></html>\n"
    )
