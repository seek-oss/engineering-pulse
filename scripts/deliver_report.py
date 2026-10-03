#!/usr/bin/env python3
"""Deliver a finished report: archive it, then notify and/or email per DELIVERY.

DELIVERY (from .env): notify (default) | email | both | none (local file only).
Archiving always happens, so every report shows up on the calendar at
output/reports/index.html.

Usage:
  # Agent workflow (skill "Deliver" step):
  python scripts/deliver_report.py send --type pulse \
      --subject "Daily dashboard — team — 2026-10-02" output/daily_dashboard_report.html

  # Scheduled runner safety net: deliver if the agent did not, else record a failed run.
  python scripts/deliver_report.py ensure --type pulse --since 1759363200 \
      --agent-exit 0 output/daily_dashboard_report.html
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from rich.console import Console
from scripts.notify_report import notify
from scripts.report_archive import (
    DEFAULT_RETENTION_DAYS,
    ROOT,
    TYPE_LABELS,
    archive,
    entries_since,
    prune,
    record_failure,
    reports_dir,
)

DELIVERY_MODES = ("notify", "email", "both", "none")
console = Console()


def delivery_mode() -> str:
    mode = os.environ.get("DELIVERY", "notify").strip().lower() or "notify"
    if mode not in DELIVERY_MODES:
        console.print(f"[yellow]Unknown DELIVERY={mode!r}; using notify[/yellow]")
        return "notify"
    return mode


def _retention_days() -> int:
    try:
        return int(os.environ.get("REPORT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
    except ValueError:
        return DEFAULT_RETENTION_DAYS


def notification_text(entry: dict, report_type: str) -> tuple[str, str, str]:
    """Return (title, subtitle, message), e.g. ("Engineering Pulse ready", "Sat 3 Oct · 18:22", <report title>)."""
    day = datetime.strptime(entry["date"], "%Y-%m-%d")
    subtitle = f"{day:%a} {day.day} {day:%b} · {entry['time']}"
    return f"{TYPE_LABELS[report_type]} ready", subtitle, entry["title"]


def send_email(subject: str, report: Path) -> int:
    script = Path(__file__).resolve().parent / "send_report_smtp.py"
    return subprocess.run(
        [sys.executable, str(script), subject, str(report)], check=False
    ).returncode


def send(
    report: Path, report_type: str, subject: str | None = None, root: Path | None = None
) -> int:
    root = root or reports_dir()
    entry, created = archive(report, report_type, root=root)
    console.print(f"[green]Archived[/green] {root / entry['path']}")
    prune(root, _retention_days())
    if not created:
        console.print("Report already delivered (identical content); skipping notify/email.")
        return 0

    mode = delivery_mode()
    if mode in ("notify", "both"):
        title, subtitle, message = notification_text(entry, report_type)
        method = notify(
            title,
            message,
            subtitle=subtitle,
            open_target=root / "latest-day.html",
            group=f"engineering-pulse-{report_type}",
        )
        console.print(f"[green]Notified[/green] via {method}")
    if mode in ("email", "both"):
        code = send_email(subject or entry["title"], report)
        if code != 0:
            console.print("[red]Email failed[/red] (report is still archived)")
            return code
    console.print(f"Calendar: {(root / 'index.html').as_uri()}")
    return 0


def ensure(
    report_type: str,
    since: datetime,
    report: Path | None,
    agent_exit: int = 0,
    subject: str | None = None,
    root: Path | None = None,
) -> int:
    root = root or reports_dir()
    if any(e.get("status") == "ok" for e in entries_since(root, report_type, since)):
        console.print(f"{TYPE_LABELS[report_type]} already delivered this run.")
        return 0
    if report and report.is_file() and datetime.fromtimestamp(report.stat().st_mtime) >= since:
        return send(report, report_type, subject, root)

    note = f"Agent exited with code {agent_exit}; no new report was written."
    record_failure(report_type, root=root, note=note)
    console.print(f"[red]Recorded failed {report_type} run[/red]: {note}")
    if delivery_mode() in ("notify", "both"):
        notify(
            f"{TYPE_LABELS[report_type]} run failed",
            "No report was produced — check /tmp/daily-dashboard.log",
            open_target=root / "index.html",
            group=f"engineering-pulse-{report_type}",
        )
    return 1


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Archive + notify/email a finished report")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_send = sub.add_parser("send", help="Deliver a report now")
    p_send.add_argument("--type", required=True, choices=sorted(TYPE_LABELS))
    p_send.add_argument("--subject", help="Email subject (default: report <title>)")
    p_send.add_argument("report", type=Path)
    p_ens = sub.add_parser("ensure", help="Runner safety net after an agent step")
    p_ens.add_argument("--type", required=True, choices=sorted(TYPE_LABELS))
    p_ens.add_argument("--since", required=True, type=float, help="Run start (epoch seconds)")
    p_ens.add_argument("--agent-exit", type=int, default=0)
    p_ens.add_argument("--subject")
    p_ens.add_argument("report", type=Path, nargs="?")
    args = ap.parse_args(argv)

    if args.cmd == "send":
        if not args.report.is_file():
            console.print(f"[red]Report not found: {args.report}[/red]")
            return 1
        return send(args.report, args.type, args.subject)
    return ensure(
        args.type,
        datetime.fromtimestamp(args.since),
        args.report,
        agent_exit=args.agent_exit,
        subject=args.subject,
    )


if __name__ == "__main__":
    raise SystemExit(main())
