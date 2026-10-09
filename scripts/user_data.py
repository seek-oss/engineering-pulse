#!/usr/bin/env python3
"""Resolve and migrate durable Engineering Pulse user data.

The git checkout is replaceable. User-owned configuration and history live under
``ENGINEERING_PULSE_DATA_DIR`` (default: ``~/.engineering-pulse-data``).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR_ENV = "ENGINEERING_PULSE_DATA_DIR"
DEFAULT_DATA_DIR = Path.home() / ".engineering-pulse-data"


def data_dir() -> Path:
    if override := os.environ.get(DATA_DIR_ENV):
        return Path(override).expanduser().resolve()
    legacy = ROOT / ".env"
    if legacy.is_symlink():
        target = legacy.resolve()
        if target.name == ".env":
            return target.parent
    return DEFAULT_DATA_DIR


def durable_env_file() -> Path:
    return data_dir() / ".env"


def env_file() -> Path:
    """Return the durable env file, falling back to a pre-migration checkout."""
    durable = durable_env_file()
    legacy = ROOT / ".env"
    return durable if durable.exists() else legacy


def reports_dir() -> Path:
    values = dotenv_values(env_file()) if env_file().is_file() else {}
    override = os.environ.get("REPORTS_DIR") or values.get("REPORTS_DIR")
    return Path(override).expanduser() if override else data_dir() / "reports"


def dashboards_dir() -> Path:
    return data_dir() / "dashboards"


def extras_dir() -> Path:
    return data_dir() / "extras"


def ensure_layout() -> Path:
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    for folder in (dashboards_dir(), extras_dir(), root / "reports"):
        folder.mkdir(parents=True, exist_ok=True)
    return root


def _copy_user_markdown(src: Path, dst: Path) -> int:
    copied = 0
    if not src.is_dir():
        return copied
    dst.mkdir(parents=True, exist_ok=True)
    for path in src.glob("*.md"):
        if path.name.startswith("_") or not path.is_file():
            continue
        target = dst / path.name
        if not target.exists():
            shutil.copy2(path, target)
            copied += 1
    return copied


def _load_entries(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return []


def _merge_report_archive(src: Path, dst: Path) -> int:
    """Copy legacy reports and merge manifest entries without overwriting data."""
    if not src.is_dir():
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    source_entries = _load_entries(src / "manifest.json")
    dest_entries = _load_entries(dst / "manifest.json")
    known = {entry.get("id") for entry in dest_entries}
    added = 0
    for entry in source_entries:
        migrated = dict(entry)
        report_id = entry.get("id")
        rel = entry.get("path")
        if rel:
            source_report = src / rel
            target_report = dst / rel
            if source_report.is_file():
                if (
                    target_report.exists()
                    and target_report.read_bytes() != source_report.read_bytes()
                ):
                    target_report = target_report.with_name(f"{report_id}.html")
                    migrated["path"] = target_report.relative_to(dst).as_posix()
                if not target_report.exists():
                    target_report.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_report, target_report)
        if report_id and report_id not in known:
            dest_entries.append(migrated)
            known.add(report_id)
            added += 1
    if added or (source_entries and not (dst / "manifest.json").exists()):
        dest_entries.sort(key=lambda entry: entry.get("timestamp", ""))
        (dst / "manifest.json").write_text(
            json.dumps({"entries": dest_entries}, indent=2) + "\n", encoding="utf-8"
        )
    return added


def _install_env_link(legacy: Path, durable: Path) -> str:
    if legacy.is_symlink() and legacy.resolve() == durable.resolve():
        return "Configuration link already installed"
    if legacy.exists() or legacy.is_symlink():
        if legacy.is_symlink():
            legacy.unlink()
        else:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = data_dir() / f".env.legacy-{stamp}"
            shutil.copy2(legacy, backup)
            legacy.unlink()
    legacy.symlink_to(durable)
    return f"Configuration: {durable}"


def migrate(root: Path = ROOT) -> list[str]:
    """Migrate legacy repo-local user data, preserving every source file."""
    ensure_layout()
    messages: list[str] = []
    legacy_env = root / ".env"
    durable_env = durable_env_file()
    if not durable_env.exists():
        if legacy_env.is_file():
            shutil.copy2(legacy_env, durable_env)
        else:
            shutil.copy2(root / ".env.example", durable_env)
        os.chmod(durable_env, 0o600)
        messages.append(f"Created durable configuration: {durable_env}")
    else:
        os.chmod(durable_env, 0o600)

    values = dotenv_values(durable_env)
    if not (os.environ.get("REPORTS_DIR") or values.get("REPORTS_DIR")):
        count = _merge_report_archive(root / "output" / "reports", data_dir() / "reports")
        if count:
            messages.append(f"Migrated {count} archived report(s)")

    dashboards = _copy_user_markdown(root / "prompts" / "dashboards", dashboards_dir())
    extras = _copy_user_markdown(root / "prompts" / "extras", extras_dir())
    if dashboards:
        messages.append(f"Migrated {dashboards} custom dashboard(s)")
    if extras:
        messages.append(f"Migrated {extras} extra card(s)")
    messages.append(_install_env_link(legacy_env, durable_env))
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("path").add_argument(
        "kind", choices=("root", "env", "reports", "dashboards", "extras", "index")
    )
    args = parser.parse_args()
    if args.command == "migrate":
        for message in migrate():
            print(message)
        return 0
    paths = {
        "root": data_dir(),
        "env": env_file(),
        "reports": reports_dir(),
        "dashboards": dashboards_dir(),
        "extras": extras_dir(),
        "index": reports_dir() / "index.html",
    }
    print(paths[args.kind])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
