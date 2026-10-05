#!/usr/bin/env python3
"""Change Engineering Pulse settings from the report calendar or the command line.

Editable settings (secrets are never editable here):

  days / times   LaunchAgent schedule (via scripts/schedule.py)
  reports        which reports scheduled runs produce: pulse, sprint, both, or none (paused)
  retention      REPORT_RETENTION_DAYS — days to keep archived reports (0 = forever)

The calendar's Settings panel opens ``engineering-pulse://settings?days=…&times=…``;
the link handler app runs ``describe-url`` to show a confirmation dialog built from the
validated values, then ``apply-url`` after the user confirms.

Usage:
  python scripts/settings.py show
  python scripts/settings.py set --reports sprint --retention 30
  python scripts/settings.py describe-url 'engineering-pulse://settings?reports=none'
  python scripts/settings.py apply-url 'engineering-pulse://settings?reports=none'
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import dotenv_values
from scripts import schedule

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
URL_SCHEME = "engineering-pulse"
REPORT_TYPES = ("pulse", "sprint")
REPORT_LABELS = {"pulse": "Engineering Pulse", "sprint": "Sprint report"}
DEFAULT_REPORTS = "pulse,sprint"
DEFAULT_RETENTION = 90
MAX_RETENTION = 3650
FIELDS = ("days", "times", "reports", "retention")
_INT_RE = re.compile(r"^\d{1,4}$")


class SettingsError(ValueError):
    pass


def parse_reports(spec: str) -> list[str]:
    spec = spec.strip().lower()
    if spec in ("none", "paused", ""):
        return []
    chosen = set()
    for part in spec.split(","):
        part = part.strip()
        if part not in REPORT_TYPES:
            raise SettingsError(f"unknown report: {part!r} (use pulse, sprint or none)")
        chosen.add(part)
    return [t for t in REPORT_TYPES if t in chosen]


def parse_retention(spec: str) -> int:
    if not _INT_RE.fullmatch(spec) or int(spec) > MAX_RETENTION:
        raise SettingsError(f"retention must be 0–{MAX_RETENTION} days, got {spec!r}")
    return int(spec)


def parse_changes(raw: dict[str, str]) -> dict:
    """Validate raw string values into typed changes; unknown keys are rejected."""
    unknown = set(raw) - set(FIELDS)
    if unknown:
        raise SettingsError(f"unknown setting: {sorted(unknown)[0]!r}")
    changes: dict = {}
    try:
        if "days" in raw:
            changes["days"] = schedule.parse_days(raw["days"])
        if "times" in raw:
            changes["times"] = [f"{h:02d}:{m:02d}" for h, m in schedule.parse_times(raw["times"])]
    except ValueError as exc:
        raise SettingsError(str(exc)) from exc
    if "reports" in raw:
        changes["reports"] = parse_reports(raw["reports"])
    if "retention" in raw:
        changes["retention"] = parse_retention(raw["retention"])
    return changes


def parse_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != URL_SCHEME or parsed.netloc != "settings":
        raise SettingsError("unsupported link")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if any(len(v) > 1 for v in query.values()):
        raise SettingsError("each setting may appear only once")
    return parse_changes({k: v[0] for k, v in query.items()})


def current_settings(plist: Path | None = None, env_file: Path = ENV_FILE) -> dict:
    env = dotenv_values(env_file) if env_file.is_file() else {}
    sched = schedule.read_schedule(plist)
    try:
        reports = parse_reports(env.get("SCHEDULED_REPORTS") or DEFAULT_REPORTS)
    except SettingsError:
        reports = list(REPORT_TYPES)
    try:
        retention = int(env.get("REPORT_RETENTION_DAYS") or DEFAULT_RETENTION)
    except ValueError:
        retention = DEFAULT_RETENTION
    return {
        "days": sched["days"] if sched else None,
        "times": sched["times"] if sched else None,
        "reports": reports,
        "retention": retention,
    }


def _fmt(field: str, value) -> str:
    if value is None:
        return "—"
    if field == "days":
        return schedule.format_days(value)
    if field == "times":
        return ", ".join(value)
    if field == "reports":
        return " + ".join(REPORT_LABELS[t] for t in value) if value else "none (paused)"
    return "forever" if value == 0 else f"{value} days"


_FIELD_LABELS = {
    "days": "Run days",
    "times": "Run times",
    "reports": "Scheduled reports",
    "retention": "Keep reports",
}


def describe(current: dict, changes: dict) -> list[str]:
    """Human-readable lines for each setting that would change."""
    lines = []
    for field in FIELDS:
        if field in changes and changes[field] != current[field]:
            label = _FIELD_LABELS[field]
            lines.append(f"{label}: {_fmt(field, current[field])} → {_fmt(field, changes[field])}")
    return lines


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    """Set KEY=value lines in a dotenv file, keeping every other line and the file mode."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    pending = dict(updates)
    for i, line in enumerate(lines):
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in pending:
            lines[i] = f"{m.group(1)}={pending.pop(m.group(1))}"
    lines.extend(f"{k}={v}" for k, v in pending.items())
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if path.exists():
        os.chmod(tmp, path.stat().st_mode & 0o777)
    else:
        os.chmod(tmp, 0o600)
    tmp.replace(path)


def apply(
    changes: dict,
    *,
    plist: Path | None = None,
    env_file: Path = ENV_FILE,
    reload: bool = True,
    rebuild: bool = True,
) -> list[str]:
    """Apply validated changes; return the description of what changed."""
    current = current_settings(plist, env_file)
    lines = describe(current, changes)
    if not lines:
        return []

    if any(f in changes and changes[f] != current[f] for f in ("days", "times")):
        plist = plist or schedule.default_plist_path()
        if not plist.is_file():
            raise SettingsError("no LaunchAgent installed — run install.sh first")
        days = changes.get("days", current["days"])
        times = schedule.parse_times(",".join(changes.get("times", current["times"])))
        schedule.write_schedule(plist, schedule.build_intervals(days, times))
        if reload:
            try:
                schedule.reload_agent(plist)
            except subprocess.CalledProcessError as exc:
                raise SettingsError("launchctl could not reload the schedule") from exc

    env_updates = {}
    if "reports" in changes:
        env_updates["SCHEDULED_REPORTS"] = ",".join(changes["reports"]) or "none"
    if "retention" in changes:
        env_updates["REPORT_RETENTION_DAYS"] = str(changes["retention"])
    if env_updates:
        upsert_env(env_file, env_updates)
        os.environ.update(env_updates)

    if rebuild:
        _rebuild_index()
    return lines


def _rebuild_index() -> None:
    from scripts.report_archive import build_index, reports_dir

    root = reports_dir()
    if (root / "manifest.json").is_file():
        build_index(root)


def _print_settings(current: dict) -> None:
    for field in FIELDS:
        print(f"{_FIELD_LABELS[field]:<24} {_fmt(field, current[field])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Show or change Engineering Pulse settings")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="print the current settings")
    p_set = sub.add_parser("set", help="change settings")
    p_set.add_argument("--days", help="e.g. mon-fri, mon-sun")
    p_set.add_argument("--times", help="e.g. 09:00,12:00")
    p_set.add_argument("--reports", help="pulse, sprint, pulse,sprint, or none (pause)")
    p_set.add_argument("--retention", help="days to keep reports (0 = forever)")
    for name in ("describe-url", "apply-url"):
        sub.add_parser(name).add_argument("url")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "show":
            _print_settings(current_settings())
            return 0
        if args.cmd == "set":
            raw = {f: getattr(args, f) for f in FIELDS if getattr(args, f) is not None}
            changes = parse_changes(raw)
        else:
            changes = parse_url(args.url)
        if args.cmd == "describe-url":
            lines = describe(current_settings(), changes)
            if "reports" in changes and not runner_supports_pause():
                lines.append(
                    "Note: re-run install.sh once so scheduled runs honour paused reports."
                )
            print("\n".join(lines) or "No changes.")
            return 0
        lines = apply(changes)
    except SettingsError as exc:
        print(f"Settings not applied: {exc}", file=sys.stderr)
        return 2

    print("\n".join(lines) or "No changes.")
    if lines and args.cmd == "apply-url":
        from scripts.notify_report import notify

        notify("Settings applied", "\n".join(lines), open_target=_index_path())
    return 0


def runner_supports_pause(runner: Path | None = None) -> bool:
    runner = runner or Path.home() / "bin" / "run-daily-dashboard.sh"
    try:
        return "report_enabled" in runner.read_text(encoding="utf-8")
    except OSError:
        return True


def _index_path() -> Path:
    from scripts.report_archive import reports_dir

    return reports_dir() / "index.html"


if __name__ == "__main__":
    sys.exit(main())
