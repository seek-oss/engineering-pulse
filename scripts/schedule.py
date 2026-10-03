#!/usr/bin/env python3
"""Show or change when the scheduled Engineering Pulse run fires (macOS LaunchAgent).

The installed plist (``~/Library/LaunchAgents/com.<user>.daily-dashboard.plist``) is the
single source of truth. ``set`` rewrites only its ``StartCalendarInterval`` and reloads
the LaunchAgent; label, runner path and log paths are left untouched.

Usage:
  python scripts/schedule.py show
  python scripts/schedule.py set --days mon-sun --times 10:00
  python scripts/schedule.py set --days mon-fri --times 09:00,12:00,16:00
  python scripts/schedule.py set --days mon,wed,fri --times 8:30 --dry-run

Days accept names (mon..sun), ranges (mon-fri), or the aliases weekdays, weekends, daily.
Override the plist location with SCHEDULE_PLIST.
"""

from __future__ import annotations

import argparse
import getpass
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()

# launchd convention: 0 (or 7) = Sunday, 1 = Monday … 6 = Saturday.
DAY_NAMES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
ORDERED_DAYS = [1, 2, 3, 4, 5, 6, 0]
DAY_ALIASES = {
    "daily": ORDERED_DAYS,
    "everyday": ORDERED_DAYS,
    "weekdays": [1, 2, 3, 4, 5],
    "weekends": [6, 0],
}
MAX_TIMES = 12
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?$")


def default_plist_path() -> Path:
    override = os.environ.get("SCHEDULE_PLIST")
    if override:
        return Path(override).expanduser()
    label = f"com.{getpass.getuser()}.daily-dashboard"
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _day_index(name: str) -> int:
    key = name.strip().lower()[:3]
    if key not in DAY_NAMES:
        raise ValueError(f"unknown day: {name!r} (use mon..sun)")
    return DAY_NAMES.index(key)


def parse_days(spec: str) -> list[int]:
    """Parse a day spec into launchd weekday numbers, ordered Monday first."""
    chosen: set[int] = set()
    for part in spec.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part in DAY_ALIASES:
            chosen.update(DAY_ALIASES[part])
        elif "-" in part:
            start, end = (_day_index(p) for p in part.split("-", 1))
            i, j = ORDERED_DAYS.index(start), ORDERED_DAYS.index(end)
            if j < i:
                raise ValueError(f"day range must run Monday→Sunday: {part!r}")
            chosen.update(ORDERED_DAYS[i : j + 1])
        else:
            chosen.add(_day_index(part))
    if not chosen:
        raise ValueError("no days given")
    return [d for d in ORDERED_DAYS if d in chosen]


def parse_times(spec: str) -> list[tuple[int, int]]:
    """Parse ``09:00,12:30`` (or bare hours like ``9``) into sorted (hour, minute) pairs."""
    times: set[tuple[int, int]] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = _TIME_RE.match(part)
        if not m:
            raise ValueError(f"bad time: {part!r} (use HH:MM)")
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if hour > 23 or minute > 59:
            raise ValueError(f"time out of range: {part!r}")
        times.add((hour, minute))
    if not times:
        raise ValueError("no times given")
    if len(times) > MAX_TIMES:
        raise ValueError(f"at most {MAX_TIMES} run times per day")
    return sorted(times)


def build_intervals(days: list[int], times: list[tuple[int, int]]) -> list[dict]:
    """Build StartCalendarInterval dicts; every-day schedules omit Weekday."""
    every_day = set(days) == set(ORDERED_DAYS)
    intervals = []
    for hour, minute in times:
        if every_day:
            intervals.append({"Hour": hour, "Minute": minute})
            continue
        for day in days:
            intervals.append({"Weekday": day, "Hour": hour, "Minute": minute})
    return intervals


def describe(intervals: list[dict] | dict) -> dict:
    """Summarise intervals as {days: [launchd ints], times: ["HH:MM"], irregular: bool}."""
    if isinstance(intervals, dict):
        intervals = [intervals]
    pairs = set()
    for item in intervals:
        hour, minute = int(item.get("Hour", 0)), int(item.get("Minute", 0))
        weekday = item.get("Weekday")
        for day in ORDERED_DAYS if weekday is None else [int(weekday) % 7]:
            pairs.add((day, hour, minute))
    days = [d for d in ORDERED_DAYS if any(p[0] == d for p in pairs)]
    times = sorted({(p[1], p[2]) for p in pairs})
    irregular = len(pairs) != len(days) * len(times)
    return {
        "days": days,
        "times": [f"{h:02d}:{m:02d}" for h, m in times],
        "irregular": irregular,
    }


def format_days(days: list[int]) -> str:
    if set(days) == set(ORDERED_DAYS):
        return "every day"
    if days == [1, 2, 3, 4, 5]:
        return "Mon–Fri"
    return ", ".join(DAY_NAMES[d].capitalize() for d in days)


def read_schedule(path: Path | None = None) -> dict | None:
    """Return the current schedule summary, or None when no plist is installed."""
    path = path or default_plist_path()
    if not path.is_file():
        return None
    with path.open("rb") as fh:
        data = plistlib.load(fh)
    summary = describe(data.get("StartCalendarInterval", []))
    summary["label"] = data.get("Label", "")
    summary["plist"] = str(path)
    return summary


def write_schedule(path: Path, intervals: list[dict]) -> None:
    with path.open("rb") as fh:
        data = plistlib.load(fh)
    data["StartCalendarInterval"] = intervals
    tmp = path.with_suffix(".plist.tmp")
    with tmp.open("wb") as fh:
        plistlib.dump(data, fh)
    tmp.replace(path)


def reload_agent(path: Path) -> None:
    subprocess.run(["launchctl", "unload", str(path)], capture_output=True, check=False)
    subprocess.run(["launchctl", "load", str(path)], capture_output=True, check=True)


def _print_schedule(summary: dict) -> None:
    console.print(f"[bold]Schedule[/bold] ({summary.get('label') or 'LaunchAgent'})")
    console.print(f"  Days:  [green]{format_days(summary['days'])}[/green]")
    console.print(f"  Times: [green]{', '.join(summary['times']) or '—'}[/green]")
    if summary.get("irregular"):
        console.print(
            "  [yellow]Note: not every time runs on every day (hand-edited plist).[/yellow]"
        )
    if summary.get("plist"):
        console.print(f"  Plist: {summary['plist']}")


def _refresh_index() -> None:
    try:
        from scripts.report_archive import build_index, reports_dir

        root = reports_dir()
        if (root / "manifest.json").is_file():
            build_index(root)
    except Exception as exc:  # the schedule change already succeeded
        console.print(f"[yellow]Could not refresh report index: {exc}[/yellow]")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Show or change the Engineering Pulse schedule")
    ap.add_argument("--plist", type=Path, help="LaunchAgent plist (default: installed one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="Print the current schedule")
    p_set = sub.add_parser("set", help="Replace the schedule and reload the LaunchAgent")
    p_set.add_argument("--days", required=True, help="e.g. mon-fri, mon-sun, mon,wed,fri")
    p_set.add_argument("--times", required=True, help="e.g. 10:00 or 09:00,12:00,16:00")
    p_set.add_argument("--dry-run", action="store_true", help="Print without writing")
    p_set.add_argument("--no-reload", action="store_true", help="Write plist, skip launchctl")
    args = ap.parse_args(argv)

    path = args.plist or default_plist_path()

    if args.cmd == "show":
        summary = read_schedule(path)
        if summary is None:
            console.print(f"[red]No LaunchAgent plist at {path}[/red] — run install.sh first.")
            return 1
        _print_schedule(summary)
        return 0

    try:
        days, times = parse_days(args.days), parse_times(args.times)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    intervals = build_intervals(days, times)
    summary = describe(intervals)

    if args.dry_run:
        _print_schedule(summary)
        console.print("[yellow]Dry run — plist not changed.[/yellow]")
        return 0
    if not path.is_file():
        console.print(f"[red]No LaunchAgent plist at {path}[/red] — run install.sh first.")
        return 1

    write_schedule(path, intervals)
    if not args.no_reload:
        try:
            reload_agent(path)
        except subprocess.CalledProcessError as exc:
            console.print(f"[red]launchctl load failed: {exc}[/red]")
            return 1
    _print_schedule(read_schedule(path) or summary)
    console.print("[green]Schedule updated.[/green]")
    _refresh_index()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    raise SystemExit(main())
