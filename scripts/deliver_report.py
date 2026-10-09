#!/usr/bin/env python3
"""Deliver a finished report: archive it, then notify and/or email per DELIVERY.

DELIVERY (from .env): notify (default) | email | both | none (local file only).
Archiving always happens, so every report shows up on the durable report calendar.

Usage:
  # Agent workflow (skill "Deliver" step):
  python scripts/deliver_report.py send --type pulse \
      --subject "Daily dashboard — team — 2026-10-02" output/daily_dashboard_report.html

  # Scheduled runner safety net: deliver if the agent did not; if it wrote nothing,
  # build a report from whatever this run produced, with the problems on top.
  python scripts/deliver_report.py ensure --type pulse --since 1759363200 \
      --agent-exit 0 output/daily_dashboard_report.html

Problems recorded in output/run_issues/<type>.json (scripts/run_issues.py) are shown
in a red box at the top of the delivered report.
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
from scripts import run_issues
from scripts.issue_box import fallback_report, inject, render_issue_box
from scripts.notify_report import notify
from scripts.report_archive import (
    DEFAULT_RETENTION_DAYS,
    ROOT,
    TYPE_LABELS,
    archive,
    entries_since,
    prune,
    reports_dir,
)
from scripts.user_data import env_file

DELIVERY_MODES = ("notify", "email", "both", "none")
RUN_LOGS = {"compare": "/tmp/engineering-pulse-compare.log"}
console = Console()


def run_log(report_type: str) -> str:
    return RUN_LOGS.get(report_type, "/tmp/daily-dashboard.log")


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
    title = f"{TYPE_LABELS[report_type]} ready"
    if count := entry.get("issues"):
        title += f" — {count} problem{'s' if count != 1 else ''}"
    return title, subtitle, entry["title"]


def send_email(subject: str, report: Path) -> int:
    script = Path(__file__).resolve().parent / "send_report_smtp.py"
    return subprocess.run(
        [sys.executable, str(script), subject, str(report)], check=False
    ).returncode


def send(
    report: Path, report_type: str, subject: str | None = None, root: Path | None = None
) -> int:
    root = root or reports_dir()
    issues = run_issues.load(report_type)
    text = report.read_text(encoding="utf-8", errors="replace")
    updated = inject(text, render_issue_box(issues, report_type))
    if updated != text:
        report.write_text(updated, encoding="utf-8")
    entry, created = archive(report, report_type, root=root, issues=len(issues))
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
        if agent_exit != 0:
            run_issues.add(report_type, "agent", agent_message(report_type, agent_exit, True))
        return send(report, report_type, subject, root)

    run_issues.add(report_type, "agent", agent_message(report_type, agent_exit, False))
    fallback = build_fallback(report_type, since)
    console.print(f"[red]Agent wrote no {report_type} report[/red]; delivering {fallback}")
    send(fallback, report_type, subject, root)
    return 1


def agent_message(report_type: str, agent_exit: int, wrote_report: bool) -> str:
    if agent_exit == 130:
        what = "The run was interrupted (exit code 130)"
    elif agent_exit:
        what = f"The agent stopped with exit code {agent_exit}"
    else:
        what = "The agent finished"
    outcome = "; some sections may be missing" if wrote_report else " without writing a report"
    return f"{what}{outcome}. Details: {run_log(report_type)}"


def _render_pulse(since: datetime, out: Path) -> bool:
    script = Path(__file__).resolve().parent / "render_daily_dashboard_html.py"
    cmd = [sys.executable, str(script), "--since", str(since.timestamp()), "--out", str(out)]
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    return result.returncode == 0 and out.is_file()


def build_fallback(report_type: str, since: datetime) -> Path:
    """A report from what this run produced: the pulse renderer on fresh data, else a frame."""
    out_dir = ROOT / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    if report_type == "pulse":
        out = out_dir / "daily_dashboard_report.html"
        if _render_pulse(since, out) and datetime.fromtimestamp(out.stat().st_mtime) >= since:
            return out
    else:
        out = out_dir / f"{report_type}-incomplete-{datetime.now():%Y-%m-%d-%H%M%S}.html"
    out.write_text(fallback_report(report_type, run_issues.load(report_type)), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    load_dotenv(env_file())
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
