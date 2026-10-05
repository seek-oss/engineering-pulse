#!/usr/bin/env python3
"""Show a macOS notification that a report is ready.

Uses terminal-notifier when installed (clicking the banner opens the report's day
view); otherwise falls back to a plain ``osascript`` banner. It never opens a browser
without a user action. On non-macOS systems it only prints the link.

Usage:
  python scripts/notify_report.py --title "Engineering Pulse" --message "Report ready" \
      --open output/reports/latest-day.html
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
from pathlib import Path

NOTIFIER_FALLBACK_PATHS = (
    "/opt/homebrew/bin/terminal-notifier",
    "/usr/local/bin/terminal-notifier",
)
_OSASCRIPT = (
    "on run argv\n"
    "display notification (item 1 of argv) with title (item 2 of argv) "
    'subtitle (item 3 of argv) sound name "Glass"\n'
    "end run"
)


def find_terminal_notifier() -> str | None:
    found = shutil.which("terminal-notifier")
    if found:
        return found
    for candidate in NOTIFIER_FALLBACK_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


def to_url(target: str | Path) -> str:
    text = str(target)
    if "://" in text:
        return text
    return Path(text).expanduser().resolve().as_uri()


def notify(
    title: str,
    message: str,
    *,
    subtitle: str = "",
    open_target: str | Path | None = None,
    group: str = "engineering-pulse",
) -> str:
    """Send the notification. Returns the method used: terminal-notifier, osascript or print."""
    url = to_url(open_target) if open_target else None

    if platform.system() != "Darwin":
        print(f"{title}: {message}" + (f" — {url}" if url else ""))
        return "print"

    notifier = find_terminal_notifier()
    if notifier:
        cmd = [notifier, "-title", title, "-message", message, "-group", group, "-sound", "Glass"]
        if subtitle:
            cmd += ["-subtitle", subtitle]
        if url:
            cmd += ["-open", url]
        subprocess.run(cmd, capture_output=True, check=False)
        method = "terminal-notifier"
    else:
        subprocess.run(
            ["osascript", "-e", _OSASCRIPT, message, title, subtitle],
            capture_output=True,
            check=False,
        )
        method = "osascript"

    return method


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Show a macOS 'report ready' notification")
    ap.add_argument("--title", default="Engineering Pulse")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--message", required=True)
    ap.add_argument("--open", dest="open_target", help="File path or URL to open on click")
    args = ap.parse_args(argv)
    method = notify(args.title, args.message, subtitle=args.subtitle, open_target=args.open_target)
    print(f"Notified via {method}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
