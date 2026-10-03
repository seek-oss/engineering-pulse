#!/usr/bin/env python3
"""Keep every generated report and rebuild the calendar index.

Layout under REPORTS_DIR (default ``output/reports``)::

  2026/10/02/pulse-090012.html     archived copy, never overwritten
  manifest.json                    one entry per archived report or failed run
  index.html                       calendar + day viewer (manifest embedded inline)
  latest.html                      copy of the newest report
  latest-day.html                  redirect to the newest report's day view

Usage:
  python scripts/report_archive.py archive --type pulse output/daily_dashboard_report.html
  python scripts/report_archive.py record-failure --type sprint --note "agent exit 1"
  python scripts/report_archive.py backfill
  python scripts/report_archive.py prune --days 90
  python scripts/report_archive.py build-index
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
TEMPLATE = Path(__file__).resolve().parent / "templates" / "report_index.html.tmpl"
TYPE_LABELS = {"pulse": "Engineering Pulse", "sprint": "Sprint report"}
DEFAULT_RETENTION_DAYS = 90

_TITLE_RE = re.compile(r"<title[^>]*>([\s\S]*?)</title>", re.IGNORECASE)
_SPRINT_NAME_RE = re.compile(
    r"^sprint-report-.+?-(?:run(?P<run>\d{4}|\d{6})-)?(?P<date>\d{4}-\d{2}-\d{2})\.html$"
)

console = Console(stderr=True)


def reports_dir() -> Path:
    load_dotenv(ROOT / ".env")
    override = os.environ.get("REPORTS_DIR")
    return Path(override).expanduser() if override else OUTPUT / "reports"


def manifest_path(root: Path) -> Path:
    return root / "manifest.json"


def load_manifest(root: Path) -> list[dict]:
    path = manifest_path(root)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("entries", [])


def save_manifest(root: Path, entries: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    entries.sort(key=lambda e: e["timestamp"])
    tmp = manifest_path(root).with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"entries": entries}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(manifest_path(root))


def extract_title(body: str, fallback: str) -> str:
    m = _TITLE_RE.search(body)
    if not m:
        return fallback
    title = " ".join(html.unescape(m.group(1)).split())
    return title or fallback


def _check_type(report_type: str) -> None:
    if report_type not in TYPE_LABELS:
        raise ValueError(f"unknown report type {report_type!r} (use {', '.join(TYPE_LABELS)})")


def _entry_base(report_type: str, when: datetime) -> dict:
    when = when.astimezone()
    return {
        "type": report_type,
        "date": when.strftime("%Y-%m-%d"),
        "time": when.strftime("%H:%M"),
        "timestamp": when.isoformat(timespec="seconds"),
    }


def _unique_id(entries: list[dict], base: str) -> str:
    ids = {e["id"] for e in entries}
    candidate, n = base, 2
    while candidate in ids:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def archive(
    src: Path,
    report_type: str,
    *,
    root: Path | None = None,
    when: datetime | None = None,
    rebuild: bool = True,
) -> tuple[dict, bool]:
    """Copy ``src`` into the archive. Returns (entry, created); identical content is not re-added."""
    _check_type(report_type)
    root = root or reports_dir()
    data = src.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    entries = load_manifest(root)
    for entry in entries:
        if entry.get("sha256") == digest and entry["type"] == report_type:
            return entry, False

    when = when or datetime.now()
    entry = _entry_base(report_type, when)
    local = when.astimezone()
    entry["id"] = _unique_id(entries, f"{report_type}-{local:%Y%m%d-%H%M%S}")
    rel = Path(*entry["date"].split("-")) / f"{report_type}-{local:%H%M%S}.html"
    if (root / rel).exists():
        rel = rel.with_name(f"{entry['id']}.html")
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_bytes(data)

    entry.update(
        {
            "status": "ok",
            "title": extract_title(data.decode("utf-8", "replace"), TYPE_LABELS[report_type]),
            "path": rel.as_posix(),
            "sha256": digest,
            "source": src.name,
        }
    )
    entries.append(entry)
    save_manifest(root, entries)
    if rebuild:
        build_index(root)
    return entry, True


def record_failure(
    report_type: str,
    *,
    root: Path | None = None,
    when: datetime | None = None,
    note: str = "",
    rebuild: bool = True,
) -> dict:
    _check_type(report_type)
    root = root or reports_dir()
    entries = load_manifest(root)
    when = when or datetime.now()
    entry = _entry_base(report_type, when)
    stamp = when.astimezone().strftime("%Y%m%d-%H%M%S")
    entry.update(
        {
            "id": _unique_id(entries, f"{report_type}-{stamp}-failed"),
            "status": "failed",
            "title": f"{TYPE_LABELS[report_type]} run failed",
            "note": note,
        }
    )
    entries.append(entry)
    save_manifest(root, entries)
    if rebuild:
        build_index(root)
    return entry


def entries_since(root: Path, report_type: str, since: datetime) -> list[dict]:
    since = since.astimezone()
    return [
        e
        for e in load_manifest(root)
        if e["type"] == report_type and datetime.fromisoformat(e["timestamp"]) >= since
    ]


def _sprint_time(path: Path, date: str, run: str | None) -> datetime:
    day = datetime.strptime(date, "%Y-%m-%d")
    if run:
        hour, minute = int(run[:2]), int(run[2:4])
        second = int(run[4:6]) if len(run) == 6 else 0
        if hour < 24 and minute < 60 and second < 60:
            return day.replace(hour=hour, minute=minute, second=second)
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    if mtime.date() == day.date():
        return mtime
    return day.replace(hour=12)


def backfill(output_dir: Path | None = None, root: Path | None = None) -> int:
    """Import existing sprint reports and the current pulse report. Returns entries added."""
    output_dir = output_dir or OUTPUT
    root = root or reports_dir()
    added = 0
    for path in sorted(output_dir.glob("sprint-report-*.html")):
        m = _SPRINT_NAME_RE.match(path.name)
        if not m:
            continue
        when = _sprint_time(path, m.group("date"), m.group("run"))
        _, created = archive(path, "sprint", root=root, when=when, rebuild=False)
        added += created
    pulse = output_dir / "daily_dashboard_report.html"
    if pulse.is_file():
        when = datetime.fromtimestamp(pulse.stat().st_mtime)
        _, created = archive(pulse, "pulse", root=root, when=when, rebuild=False)
        added += created
    build_index(root)
    return added


def prune(root: Path | None = None, days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Delete reports older than ``days`` (0 keeps everything). Returns entries removed."""
    root = root or reports_dir()
    if days <= 0:
        return 0
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    entries = load_manifest(root)
    keep, removed = [], 0
    for entry in entries:
        if entry["date"] >= cutoff:
            keep.append(entry)
            continue
        removed += 1
        if entry.get("path"):
            (root / entry["path"]).unlink(missing_ok=True)
    if removed:
        save_manifest(root, keep)
        for folder in sorted(root.glob("*/*/*"), reverse=True):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        build_index(root)
    return removed


def _python_cmd() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    return ".venv/bin/python" if venv.exists() else "python3"


def _schedule_summary() -> dict | None:
    try:
        from scripts.schedule import read_schedule

        return read_schedule()
    except Exception:
        return None


def index_data(root: Path) -> dict:
    return {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "entries": load_manifest(root),
        "types": TYPE_LABELS,
        "schedule": _schedule_summary(),
        "install_dir": str(ROOT),
        "python": _python_cmd(),
        "delivery": os.environ.get("DELIVERY", "notify"),
        "retention_days": int(os.environ.get("REPORT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)),
    }


def render_index(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("__REPORT_DATA__", payload)


def build_index(root: Path | None = None) -> Path:
    root = root or reports_dir()
    root.mkdir(parents=True, exist_ok=True)
    data = index_data(root)
    index = root / "index.html"
    index.write_text(render_index(data), encoding="utf-8")

    ok = [e for e in data["entries"] if e.get("status") == "ok" and e.get("path")]
    if ok:
        newest = ok[-1]
        shutil.copyfile(root / newest["path"], root / "latest.html")
        target = f"index.html#/day/{newest['date']}/{newest['id']}"
        (root / "latest-day.html").write_text(
            "<!doctype html><meta charset='utf-8'>"
            f"<meta http-equiv='refresh' content='0; url={target}'>"
            f"<script>location.replace({json.dumps(target)})</script>"
            f"<a href='{target}'>Open latest report</a>\n",
            encoding="utf-8",
        )
    return index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Archive reports and rebuild the calendar index")
    ap.add_argument("--reports-dir", type=Path, help="Archive root (default: REPORTS_DIR)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_arc = sub.add_parser("archive", help="Archive one report")
    p_arc.add_argument("--type", required=True, choices=sorted(TYPE_LABELS))
    p_arc.add_argument("report", type=Path)
    p_fail = sub.add_parser("record-failure", help="Record a failed run on the calendar")
    p_fail.add_argument("--type", required=True, choices=sorted(TYPE_LABELS))
    p_fail.add_argument("--note", default="")
    p_back = sub.add_parser("backfill", help="Import existing output/*.html reports")
    p_back.add_argument("--output-dir", type=Path, default=OUTPUT)
    p_prune = sub.add_parser("prune", help="Delete reports older than N days")
    p_prune.add_argument("--days", type=int, default=None)
    sub.add_parser("build-index", help="Rebuild index.html from the manifest")
    args = ap.parse_args(argv)

    root = args.reports_dir or reports_dir()

    if args.cmd == "archive":
        if not args.report.is_file():
            console.print(f"[red]Report not found: {args.report}[/red]")
            return 1
        entry, created = archive(args.report, args.type, root=root)
        verb = "Archived" if created else "Already archived"
        console.print(f"[green]{verb}[/green] {root / entry['path']}")
    elif args.cmd == "record-failure":
        record_failure(args.type, root=root, note=args.note)
        console.print(f"[red]Recorded failed {args.type} run[/red]")
    elif args.cmd == "backfill":
        added = backfill(args.output_dir, root)
        console.print(f"[green]Backfilled {added} report(s)[/green] into {root}")
    elif args.cmd == "prune":
        days = args.days
        if days is None:
            days = int(os.environ.get("REPORT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS))
        removed = prune(root, days)
        console.print(
            f"Pruned {removed} entr{'y' if removed == 1 else 'ies'} older than {days} days"
        )
    else:
        console.print(f"Wrote {build_index(root)}")
    console.print(f"Calendar: file://{root / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
