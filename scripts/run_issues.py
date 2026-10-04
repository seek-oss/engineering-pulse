#!/usr/bin/env python3
"""Problems found during a report run, shown in the red box at the top of the report.

One file per report type: output/run_issues/<type>.json
  {"run_id": "...", "run_started": <epoch>, "issues": [{"source", "message", "fix"}]}
``fix`` is {"kind": "mcp_login", "agent": "cursor", "server": "GitHub"} or null.

Usage:
  python scripts/run_issues.py reset --type pulse            # runner: new run
  python scripts/run_issues.py start --type pulse            # agent: new run unless the runner began one
  python scripts/run_issues.py preflight --type pulse --agent cursor
  python scripts/run_issues.py add --type pulse --source github \
      --message "GitHub MCP search failed: ..." [--server GitHub --agent cursor]
  python scripts/run_issues.py show --type pulse
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ISSUES_DIR = ROOT / "output" / "run_issues"
REPORT_TYPES = ("pulse", "sprint", "compare")
MAX_AGE_SECONDS = 12 * 3600
MCP_LIST_TIMEOUT = 60

AGENT_LABELS = {"cursor": "Cursor CLI", "claude": "Claude Code"}
MCP_LIST_COMMANDS = {"cursor": ["agent", "mcp", "list"], "claude": ["claude", "mcp", "list"]}

SOURCES = {
    "datadog": ("Datadog", ("datadog",)),
    "github": ("GitHub", ("github",)),
    "atlassian": ("Jira", ("atlassian", "jira")),
    "glean": ("Glean", ("glean",)),
}

READY, NEEDS_AUTH, ERROR = "ready", "needs_auth", "error"

_CLAUDE_LINE = re.compile(r"^(?P<name>[^:\s][^:]*):\s.*\s-\s(?P<status>.+)$")
_CURSOR_LINE = re.compile(r"^(?P<name>[^:\s][^:]*):\s*(?P<status>[\w\s-]+)$")


def issues_path(report_type: str, root: Path | None = None) -> Path:
    return (root or ISSUES_DIR) / f"{report_type}.json"


def _read(report_type: str, root: Path | None = None) -> dict:
    path = issues_path(report_type, root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(report_type: str, data: dict, root: Path | None = None) -> None:
    path = issues_path(report_type, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def reset(report_type: str, root: Path | None = None) -> None:
    run_id = os.environ.get("EP_RUN_ID") or ""
    _write(report_type, {"run_id": run_id, "run_started": time.time(), "issues": []}, root)


def start(report_type: str, root: Path | None = None) -> bool:
    """Begin a run unless the runner already began this one. Returns True if reset."""
    run_id = os.environ.get("EP_RUN_ID")
    if run_id and _read(report_type, root).get("run_id") == run_id:
        return False
    reset(report_type, root)
    return True


def load(report_type: str, root: Path | None = None, now: float | None = None) -> list[dict]:
    """Issues of the current run; a file left over from an old run counts as empty."""
    data = _read(report_type, root)
    started = data.get("run_started")
    now = time.time() if now is None else now
    if not isinstance(started, int | float) or now - started > MAX_AGE_SECONDS:
        return []
    return [i for i in data.get("issues") or [] if isinstance(i, dict) and i.get("message")]


def add(
    report_type: str,
    source: str,
    message: str,
    *,
    server: str | None = None,
    agent: str | None = None,
    kind: str | None = None,
    root: Path | None = None,
) -> dict:
    data = _read(report_type, root)
    if not isinstance(data.get("run_started"), int | float):
        data = {"run_id": os.environ.get("EP_RUN_ID") or "", "run_started": time.time()}
    fix = None
    if server and agent in AGENT_LABELS:
        fix = {"kind": "mcp_login", "agent": agent, "server": server}
    elif kind == "add_dashboard" and agent in AGENT_LABELS:
        fix = {"kind": "add_dashboard", "agent": agent}
    issues = [i for i in data.get("issues") or [] if isinstance(i, dict)]
    existing = next((i for i in issues if i.get("source") == source), None)
    if existing is not None:
        # One row per source: the first (usually preflight's) wording stays; a sign-in
        # fix found later is kept.
        if fix and not existing.get("fix"):
            existing["fix"] = fix
        issue = existing
    else:
        issue = {"source": source, "message": message, "fix": fix}
        issues.append(issue)
    data["issues"] = issues
    _write(report_type, data, root)
    return issue


# ---------------------------------------------------------------------------
# MCP status from the agent CLI
# ---------------------------------------------------------------------------


def _normalise(status: str) -> str:
    s = status.lower()
    if "auth" in s:
        return NEEDS_AUTH
    if "ready" in s or "connected" in s or "✓" in s:
        return READY
    return ERROR


def parse_mcp_list(agent: str, text: str) -> dict[str, str]:
    """Server name -> ready | needs_auth | error, from `agent mcp list` / `claude mcp list`."""
    pattern = _CLAUDE_LINE if agent == "claude" else _CURSOR_LINE
    servers: dict[str, str] = {}
    for line in text.splitlines():
        m = pattern.match(line.strip())
        if m:
            servers[m.group("name").strip()] = _normalise(m.group("status"))
    return servers


def mcp_status(agent: str, timeout: int = MCP_LIST_TIMEOUT) -> dict[str, str] | None:
    """Ask the agent CLI for its MCP servers; None when it cannot be asked."""
    cmd = MCP_LIST_COMMANDS.get(agent)
    if not cmd:
        return None
    try:
        out = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return parse_mcp_list(agent, out.stdout)


def _dotenv() -> dict[str, str]:
    path = ROOT / ".env"
    vals = dotenv_values(path) if path.is_file() else {}
    return {k: v or "" for k, v in vals.items()}


def has_dashboards(dashboards_dir: Path | None = None) -> bool:
    folder = dashboards_dir or ROOT / "prompts" / "dashboards"
    return any(not p.name.startswith("_") for p in folder.glob("*.md"))


def needed_sources(
    report_type: str, env: dict[str, str] | None = None, dashboards: bool | None = None
) -> list[str]:
    env = _dotenv() if env is None else env
    if report_type == "sprint":
        return ["atlassian"]
    if report_type != "pulse":
        return []
    needed = []
    if has_dashboards() if dashboards is None else dashboards:
        needed.append("datadog")
    if not (env.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        needed.append("github")
    if (env.get("STAKEHOLDERS") or "").strip():
        needed.append("glean")
    return needed


def preflight_issues(
    report_type: str,
    agent: str,
    servers: dict[str, str] | None,
    *,
    env: dict[str, str] | None = None,
    dashboards: bool | None = None,
) -> list[dict]:
    """Problems we can see before the agent starts (no files written)."""
    found: list[dict] = []
    dashboards = has_dashboards() if dashboards is None else dashboards
    if report_type == "pulse" and not dashboards:
        found.append(
            {
                "source": "datadog",
                "message": "No Datadog dashboards are set up yet, so this report has no metrics.",
                "fix": {"kind": "add_dashboard", "agent": agent} if agent in AGENT_LABELS else None,
            }
        )
    if servers is None:
        return found
    label = AGENT_LABELS.get(agent, agent)
    for key in needed_sources(report_type, env, dashboards):
        name, fragments = SOURCES[key]
        matches = {s: st for s, st in servers.items() if any(f in s.lower() for f in fragments)}
        if any(st == READY for st in matches.values()):
            continue
        auth = next((s for s, st in matches.items() if st == NEEDS_AUTH), None)
        if auth:
            server = "" if auth.lower() == name.lower() else f" ({auth})"
            found.append(
                {
                    "source": key,
                    "message": f"{name} MCP{server} needs you to sign in ({label}).",
                    "fix": {"kind": "mcp_login", "agent": agent, "server": auth},
                }
            )
        elif matches:
            listed = ", ".join(sorted(matches))
            found.append(
                {
                    "source": key,
                    "message": f"{name} MCP ({listed}) did not connect in {label}. "
                    f"Check the server in your {label} MCP settings.",
                    "fix": None,
                }
            )
        else:
            found.append(
                {
                    "source": key,
                    "message": f"{name} MCP is not set up in {label}. Add the {name} "
                    f"MCP server to {label}, then re-run.",
                    "fix": None,
                }
            )
    return found


def preflight(report_type: str, agent: str, root: Path | None = None) -> list[dict]:
    found = preflight_issues(report_type, agent, mcp_status(agent))
    for issue in found:
        fix = issue["fix"] or {}
        add(
            report_type,
            issue["source"],
            issue["message"],
            server=fix.get("server"),
            agent=fix.get("agent"),
            kind=fix.get("kind"),
            root=root,
        )
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Problems shown in the report's red box")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("reset", "start", "show"):
        sub.add_parser(name).add_argument("--type", required=True, choices=REPORT_TYPES)
    p_pre = sub.add_parser("preflight")
    p_pre.add_argument("--type", required=True, choices=REPORT_TYPES)
    p_pre.add_argument("--agent", required=True)
    p_add = sub.add_parser("add")
    p_add.add_argument("--type", required=True, choices=REPORT_TYPES)
    p_add.add_argument("--source", required=True)
    p_add.add_argument("--message", required=True)
    p_add.add_argument("--server")
    p_add.add_argument("--agent", default=os.environ.get("AGENT_CLI"))
    args = ap.parse_args(argv)

    if args.cmd == "reset":
        reset(args.type)
    elif args.cmd == "start":
        print("new run" if start(args.type) else "continuing runner's run")
    elif args.cmd == "preflight":
        for issue in preflight(args.type, args.agent):
            print(f"Problem: {issue['message']}")
    elif args.cmd == "add":
        add(args.type, args.source, args.message, server=args.server, agent=args.agent)
    else:
        print(json.dumps(load(args.type), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
