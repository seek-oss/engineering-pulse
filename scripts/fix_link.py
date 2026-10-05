#!/usr/bin/env python3
"""Handle the red box's buttons (engineering-pulse:// links) for the macOS link handler.

  engineering-pulse://auth?agent=cursor&server=GitHub   open Terminal to sign in to an MCP
  engineering-pulse://run?type=pulse                    re-run one report in the background
  engineering-pulse://add-dashboard?agent=cursor        open Terminal with the agent adding a dashboard

Usage (called by "Engineering Pulse.app"; errors go to stderr for its dialog):
  python scripts/fix_link.py handle 'engineering-pulse://auth?agent=cursor&server=GitHub'
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import run_issues
from scripts.issue_box import TYPE_LABELS
from scripts.notify_report import notify

ROOT = Path(__file__).resolve().parent.parent
# The link handler runs with launchd's minimal PATH; agent CLIs live in these.
EXTRA_PATH = ("/usr/local/bin", "/opt/homebrew/bin", "~/.local/bin", "~/bin")
LOCK_DIR = Path(os.environ.get("EP_LOCK_DIR") or "/tmp/engineering-pulse-run.lock")
LOCK_STALE_SECONDS = 3 * 3600
RUN_TYPES = ("pulse", "sprint")
ACTIONS = ("auth", "run", "add-dashboard")
ADD_DASHBOARD_PROMPT = (
    "Follow skills/engineering-pulse/references/add-dashboard.md to add a Datadog "
    "dashboard to my daily report. Start by asking me for the dashboard URL."
)


class LinkError(ValueError):
    pass


def parse(url: str) -> tuple[str, dict[str, str]]:
    parts = urlsplit(url)
    if parts.scheme != "engineering-pulse" or parts.netloc not in ACTIONS:
        raise LinkError("Unsupported link.")
    params = {k: v[0] for k, v in parse_qs(parts.query).items() if v}
    return parts.netloc, params


def runner_path() -> Path:
    override = os.environ.get("EP_RUNNER")
    return Path(override) if override else Path.home() / "bin" / "run-daily-dashboard.sh"


def run_in_progress(now: float | None = None) -> bool:
    if not LOCK_DIR.is_dir():
        return False
    now = time.time() if now is None else now
    return now - LOCK_DIR.stat().st_mtime < LOCK_STALE_SECONDS


def terminal_command(agent: str, server: str, install_dir: Path = ROOT) -> str:
    cd = f"cd {shlex.quote(str(install_dir))}"
    if agent == "cursor":
        return f"{cd} && agent mcp login {shlex.quote(server)}"
    hint = f"In Claude Code, type /mcp, choose {server}, and sign in. Then close this window."
    return f"{cd} && echo {shlex.quote(hint)} && claude"


def add_dashboard_command(agent: str, install_dir: Path = ROOT) -> str:
    cli = "agent" if agent == "cursor" else "claude"
    return f"cd {shlex.quote(str(install_dir))} && {cli} {shlex.quote(ADD_DASHBOARD_PROMPT)}"


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def open_terminal(command: str) -> None:
    script = (
        f'tell application "Terminal"\nactivate\ndo script {_applescript_string(command)}\nend tell'
    )
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)


def handle_auth(params: dict[str, str]) -> str:
    agent, server = params.get("agent", ""), params.get("server", "")
    if agent not in run_issues.MCP_LIST_COMMANDS:
        raise LinkError(f"Unknown agent {agent!r}.")
    servers = run_issues.mcp_status(agent)
    if servers is None:
        raise LinkError(f"Could not list MCP servers for {run_issues.AGENT_LABELS[agent]}.")
    if server not in servers:
        raise LinkError(f"{server!r} is not an MCP server in {run_issues.AGENT_LABELS[agent]}.")
    if servers[server] == run_issues.READY:
        return f"{server} is already signed in."
    open_terminal(terminal_command(agent, server))
    return f"Opened Terminal to sign in to {server}."


def handle_run(params: dict[str, str]) -> str:
    report_type = params.get("type", "")
    if report_type not in RUN_TYPES:
        raise LinkError(f"Unknown report type {report_type!r}.")
    if run_in_progress():
        raise LinkError("A report run is already in progress. Try again when it finishes.")
    runner = runner_path()
    if not runner.is_file():
        raise LinkError(f"Runner not found: {runner}. Re-run install.sh.")
    env = {**os.environ, "ENGINEERING_PULSE_ONLY": report_type}
    subprocess.Popen(
        ["/bin/bash", str(runner)],
        env=env,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    label = TYPE_LABELS[report_type]
    notify(
        f"Re-running {label}",
        "You'll get a notification when the report is ready.",
    )
    return f"Started {label}."


def handle_add_dashboard(params: dict[str, str]) -> str:
    agent = params.get("agent", "")
    if agent not in run_issues.AGENT_LABELS:
        raise LinkError(f"Unknown agent {agent!r}.")
    open_terminal(add_dashboard_command(agent))
    return "Opened Terminal to add a Datadog dashboard."


def handle(url: str) -> str:
    action, params = parse(url)
    if action == "auth":
        return handle_auth(params)
    if action == "add-dashboard":
        return handle_add_dashboard(params)
    return handle_run(params)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "handle":
        print("Usage: fix_link.py handle URL", file=sys.stderr)
        return 2
    extra = [os.path.expanduser(p) for p in EXTRA_PATH]
    os.environ["PATH"] = os.pathsep.join([*extra, os.environ.get("PATH", "")])
    try:
        print(handle(argv[1]))
    except (LinkError, subprocess.SubprocessError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
