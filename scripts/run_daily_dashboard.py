#!/usr/bin/env python3
"""Run the dashboard end-to-end without an agent (schedule / ~/bin/runner).

Loads `.env`, extracts each declared Datadog dashboard, refreshes Todoist JSON,
GitHub PRs, renders HTML at repo root, and sends SMTP (unless --no-email).
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

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
OUT = ROOT / "output"


def _run_logged(cmd: list[str]) -> None:
    print("+ " + subprocess.list2cmdline(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def _parse_days(raw: str) -> int:
    try:
        d = int(raw.strip())
    except ValueError:
        return 7
    return max(1, min(d, 90))


def main() -> int:
    ap = argparse.ArgumentParser(description="Engineering Pulse daily dashboard pipeline")
    ap.add_argument(
        "--no-email",
        action="store_true",
        help="Skip send_report_smtp.py (SMTP env not required)",
    )
    args = ap.parse_args()

    os.chdir(ROOT)
    load_dotenv(ROOT / ".env")
    OUT.mkdir(parents=True, exist_ok=True)

    py = sys.executable

    sys.path.insert(0, str(SCRIPTS))
    from dashboards_plugin import discover_dashboards, parse_dashboard

    days = _parse_days(os.environ.get("DASHBOARD_DAYS", "7"))

    for path in discover_dashboards(ROOT / "prompts" / "dashboards"):
        d = parse_dashboard(path)
        if not d.url.strip():
            print(f"skip {path.name}: no URL", flush=True)
            continue
        cmd: list[str] = [
            py,
            str(SCRIPTS / "datadog_dashboard_extract.py"),
            "--url",
            d.url,
            "--output-slug",
            d.slug,
            "--days",
            str(days),
        ]
        foc = d.focus.strip()
        if foc:
            cmd.extend(["--focus", foc])
        try:
            _run_logged(cmd)
        except subprocess.CalledProcessError as e:
            print(
                f"ERROR: Datadog extract failed for slug={d.slug!r}: {e}",
                file=sys.stderr,
                flush=True,
            )
            return int(e.returncode or 1)

    todos_path = OUT / "todos.json"
    try:
        proc = subprocess.run(
            [py, str(SCRIPTS / "todo.py"), "list", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        body = proc.stdout.strip()
        todos_path.write_text((body + "\n") if body else "[]\n", encoding="utf-8")
    except subprocess.CalledProcessError:
        print("WARN: todo.py failed; writing empty todos.json", flush=True)
        todos_path.write_text("[]\n", encoding="utf-8")

    try:
        _run_logged([py, str(SCRIPTS / "github_prs.py")])
    except subprocess.CalledProcessError as e:
        print(f"ERROR: github_prs failed: {e}", file=sys.stderr, flush=True)
        return int(e.returncode or 1)

    try:
        _run_logged([py, str(SCRIPTS / "render_daily_dashboard_html.py")])
    except subprocess.CalledProcessError as e:
        print(f"ERROR: render_daily_dashboard_html failed: {e}", file=sys.stderr, flush=True)
        return int(e.returncode or 1)

    report = ROOT / "daily_dashboard_report.html"
    if not report.is_file():
        print(f"ERROR: expected report missing: {report}", file=sys.stderr, flush=True)
        return 1

    if args.no_email:
        print("skip email (--no-email)", flush=True)
        return 0

    team = (os.environ.get("DATADOG_TEAMS") or "engineering").split(",")[0].strip() or "engineering"
    subject = f"Daily dashboard — {team} — {datetime.now():%Y-%m-%d}"
    try:
        _run_logged([py, str(SCRIPTS / "send_report_smtp.py"), subject, str(report)])
    except subprocess.CalledProcessError as e:
        print(f"ERROR: send_report_smtp failed: {e}", file=sys.stderr, flush=True)
        return int(e.returncode or 1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
