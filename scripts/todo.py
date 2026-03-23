#!/usr/bin/env python3
"""
Todoist-backed tasks and reading queue.

Env vars required:
    TODOIST_API_TOKEN  — API token from Settings → Integrations → Developer

Optional (auto-populated by `setup`):
    TODOIST_PROJECT_ID — project ID (skips name lookup)

Usage:
    python scripts/todo.py setup
    python scripts/todo.py add "Fix deploy pipeline" --priority high
    python scripts/todo.py add "Book dentist" --domain personal
    python scripts/todo.py add "Fowler article" --type read --url "https://..."
    python scripts/todo.py list
    python scripts/todo.py list --type task
    python scripts/todo.py list --type task --domain personal
    python scripts/todo.py list --type read
    python scripts/todo.py list --json   # includes view_url for HTML reports (see todo_report)
    python scripts/todo.py done <task-id> --comment "Merged"
    python scripts/todo.py cancel <task-id> --comment "No longer needed"
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

console = Console()

BASE_URL = "https://api.todoist.com/api/v1"
DEFAULT_PROJECT_NAME = "Engineering Pulse"
SECTION_TASKS = "Tasks"  # work
SECTION_PERSONAL = "Personal"
SECTION_READING = "Reading Queue"

PRIORITY_MAP = {"high": 4, "medium": 3, "low": 2, "none": 1}
PRIORITY_REVERSE = {4: "high", 3: "medium", 2: "low", 1: "none"}


# ---------------------------------------------------------------------------
# HTTP helpers  (Todoist API v1 — cursor-based pagination)
# ---------------------------------------------------------------------------

def _headers() -> Dict[str, str]:
    token = os.environ.get("TODOIST_API_TOKEN", "")
    if not token:
        console.print("[red]Error: TODOIST_API_TOKEN is required. Set it in .env.[/red]")
        sys.exit(1)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get(path: str, params: Optional[Dict] = None) -> Any:
    resp = requests.get(f"{BASE_URL}{path}", headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _get_all(path: str, params: Optional[Dict] = None) -> List[Dict]:
    """Paginate through a v1 endpoint that returns {results, next_cursor}."""
    all_results: List[Dict] = []
    cursor: Optional[str] = None
    p = dict(params or {})
    p["limit"] = 200
    while True:
        if cursor:
            p["cursor"] = cursor
        data = _get(path, p)
        if isinstance(data, list):
            return data
        all_results.extend(data.get("results", []))
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return all_results


def _post(path: str, body: Optional[Dict] = None) -> Any:
    resp = requests.post(f"{BASE_URL}{path}", headers=_headers(), json=body or {}, timeout=15)
    resp.raise_for_status()
    if resp.status_code == 204 or not resp.text:
        return {}
    return resp.json()


# ---------------------------------------------------------------------------
# Project / section resolution
# ---------------------------------------------------------------------------

def _find_project_by_name(name: str) -> Optional[Dict]:
    for p in _get_all("/projects"):
        if p["name"].lower() == name.lower():
            return p
    return None


def _get_project_id() -> str:
    pid = os.environ.get("TODOIST_PROJECT_ID", "")
    if pid:
        return pid
    project = _find_project_by_name(DEFAULT_PROJECT_NAME)
    if project:
        return project["id"]
    console.print(f"[red]Project '{DEFAULT_PROJECT_NAME}' not found. Run: python scripts/todo.py setup[/red]")
    sys.exit(1)


def _get_sections(project_id: str) -> Dict[str, str]:
    """Return {section_name: section_id} for the project."""
    sections = _get_all("/sections", {"project_id": project_id})
    return {s["name"]: s["id"] for s in sections}


def _ensure_section(project_id: str, name: str, existing: Dict[str, str]) -> str:
    if name in existing:
        return existing[name]
    section = _post("/sections", {"project_id": project_id, "name": name})
    return section["id"]


def _env_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".env"


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

def cmd_setup(args: argparse.Namespace) -> None:
    name = args.name or DEFAULT_PROJECT_NAME
    console.print(f"[bold]Setting up Todoist project: {name}[/bold]")

    project = _find_project_by_name(name)
    if project:
        console.print(f"  Project already exists (id={project['id']}), reusing.")
    else:
        project = _post("/projects", {"name": name})
        console.print(f"  Created project '{name}' (id={project['id']})")

    pid = project["id"]
    sections = _get_sections(pid)

    for section_name in [SECTION_TASKS, SECTION_PERSONAL, SECTION_READING]:
        sid = _ensure_section(pid, section_name, sections)
        console.print(f"  Section '{section_name}' → {sid}")
        sections[section_name] = sid

    env_path = _env_path()
    env_text = env_path.read_text() if env_path.exists() else ""
    if "TODOIST_PROJECT_ID" in env_text:
        env_text = re.sub(r"TODOIST_PROJECT_ID=.*", f"TODOIST_PROJECT_ID={pid}", env_text)
    else:
        env_text = env_text.rstrip() + f"\nTODOIST_PROJECT_ID={pid}\n"
    env_path.write_text(env_text)

    console.print(f"\n[green]✓ Done. TODOIST_PROJECT_ID={pid} saved to .env[/green]")
    console.print("  You can now use: python scripts/todo.py add \"My first task\"")


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

def cmd_add(args: argparse.Namespace) -> None:
    project_id = _get_project_id()
    sections = _get_sections(project_id)

    item_type = args.type or "task"
    if item_type == "read":
        section_name = SECTION_READING
    else:
        domain = getattr(args, "domain", None) or "work"
        section_name = SECTION_PERSONAL if domain == "personal" else SECTION_TASKS
    section_id = _ensure_section(project_id, section_name, sections)

    priority = PRIORITY_MAP.get(args.priority or "none", 1)

    body: Dict[str, Any] = {
        "content": args.title,
        "project_id": project_id,
        "section_id": section_id,
        "priority": priority,
    }

    if args.url:
        body["description"] = args.url

    task = _post("/tasks", body)
    console.print(f"[green]✓ Added {item_type}: \"{task['content']}\" (id={task['id']})[/green]")
    if args.url:
        console.print(f"  URL: {args.url}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def _age_days(ts: str) -> int:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days


def _task_created(task: Dict) -> str:
    """Return the creation timestamp — v1 uses 'added_at', v2 used 'created_at'."""
    return task.get("added_at") or task.get("created_at", "")


def _extract_url(desc: str) -> str:
    """Extract raw URL from a Todoist description (may be markdown-linked)."""
    m = re.search(r"\((https?://[^)]+)\)", desc)
    if m:
        return m.group(1)
    m = re.search(r"(https?://\S+)", desc)
    if m:
        return m.group(1)
    return desc


def cmd_list(args: argparse.Namespace) -> None:
    project_id = _get_project_id()
    sections = _get_sections(project_id)
    section_id_to_name = {v: k for k, v in sections.items()}

    tasks = _get_all("/tasks", {"project_id": project_id})

    type_filter = args.type
    domain_filter = getattr(args, "domain", None)
    if domain_filter and type_filter is None:
        type_filter = "task"

    if type_filter == "task":
        if domain_filter == "personal":
            allowed = {sections.get(SECTION_PERSONAL)}
        elif domain_filter == "work":
            allowed = {sections.get(SECTION_TASKS)}
        else:
            allowed = {sections.get(SECTION_TASKS), sections.get(SECTION_PERSONAL)}
        allowed.discard(None)
        tasks = [t for t in tasks if t.get("section_id") in allowed]
    elif type_filter == "read":
        allowed_section = sections.get(SECTION_READING)
        tasks = [t for t in tasks if t.get("section_id") == allowed_section]
    else:
        allowed_ids = [
            sections.get(SECTION_TASKS),
            sections.get(SECTION_PERSONAL),
            sections.get(SECTION_READING),
        ]
        allowed_ids = [x for x in allowed_ids if x]
        tasks = [t for t in tasks if t.get("section_id") in allowed_ids]

    tasks.sort(key=lambda t: t.get("priority", 1), reverse=True)

    if args.json:
        out = []
        for t in tasks:
            sec_name = section_id_to_name.get(t.get("section_id", ""), "")
            if sec_name == SECTION_READING:
                json_type = "read"
                domain = "read"
            elif sec_name == SECTION_PERSONAL:
                json_type = "task"
                domain = "personal"
            else:
                json_type = "task"
                domain = "work"
            out.append({
                "id": t["id"],
                "title": t["content"],
                "type": json_type,
                "domain": domain,
                "priority": PRIORITY_REVERSE.get(t.get("priority", 1), "none"),
                "url": _extract_url(t.get("description", "")),
                "age_days": _age_days(_task_created(t)),
                "created_at": _task_created(t),
            })
        _scripts = Path(__file__).resolve().parent
        if str(_scripts) not in sys.path:
            sys.path.insert(0, str(_scripts))
        from todo_report import enrich_json_items

        out = enrich_json_items(out)
        print(json.dumps(out, indent=2))
        return

    if not tasks:
        console.print("[green]✓ Queue is empty — nothing to do![/green]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("ID", style="dim", width=20)
    table.add_column("Pri", width=6)
    table.add_column("Cat", width=10)
    table.add_column("Type", width=6)
    table.add_column("Title", width=36)
    table.add_column("Age", width=5)

    for t in tasks:
        sec_name = section_id_to_name.get(t.get("section_id", ""), "")
        if sec_name == SECTION_READING:
            item_type = "read"
            cat = "read"
        elif sec_name == SECTION_PERSONAL:
            item_type = "task"
            cat = "personal"
        else:
            item_type = "task"
            cat = "work"
        pri = PRIORITY_REVERSE.get(t.get("priority", 1), "none")
        age = _age_days(_task_created(t))

        pri_styled = (
            f"[red bold]{pri}[/red bold]" if pri == "high" else
            f"[yellow]{pri}[/yellow]" if pri == "medium" else
            f"[dim]{pri}[/dim]"
        )
        age_styled = (
            f"[red]{age}d[/red]" if age >= 7 else
            f"[yellow]{age}d[/yellow]" if age >= 3 else
            f"{age}d"
        )

        title = t["content"]
        desc = t.get("description", "")
        if desc and item_type == "read":
            title = f"{title} [dim]→ {desc[:40]}[/dim]"

        table.add_row(t["id"], pri_styled, cat, item_type, title, age_styled)

    console.print(f"\n[bold]{len(tasks)} item(s)[/bold]\n")
    console.print(table)


# ---------------------------------------------------------------------------
# done / cancel
# ---------------------------------------------------------------------------

def _add_comment(task_id: str, text: str) -> None:
    _post("/comments", {"task_id": task_id, "content": text})


def cmd_done(args: argparse.Namespace) -> None:
    task_id = args.task_id
    if args.comment:
        _add_comment(task_id, f"Done: {args.comment}")
    _post(f"/tasks/{task_id}/close")
    console.print(f"[green]✓ Marked done: {task_id}[/green]")


def cmd_cancel(args: argparse.Namespace) -> None:
    task_id = args.task_id
    comment = args.comment or "Cancelled"
    _add_comment(task_id, f"Cancelled: {comment}")

    try:
        task = _get(f"/tasks/{task_id}")
        labels = task.get("labels", [])
        if "cancelled" not in labels:
            labels.append("cancelled")
            _post(f"/tasks/{task_id}", {"labels": labels})
    except requests.HTTPError:
        pass

    _post(f"/tasks/{task_id}/close")
    console.print(f"[yellow]✗ Cancelled: {task_id}[/yellow]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="todo.py",
        description="Todoist-backed tasks and reading queue",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sp_setup = sub.add_parser("setup", help="Create Todoist project and sections")
    sp_setup.add_argument("--name", default=None, help=f"Project name (default: {DEFAULT_PROJECT_NAME})")
    sp_setup.set_defaults(func=cmd_setup)

    sp_add = sub.add_parser("add", help="Add a task or reading item")
    sp_add.add_argument("title", help="Task title")
    sp_add.add_argument("--type", choices=["task", "read"], default="task", help="Item type")
    sp_add.add_argument(
        "--domain",
        choices=["work", "personal"],
        default="work",
        help="Task section: work → Tasks, personal → Personal (ignored for --type read)",
    )
    sp_add.add_argument("--priority", choices=["high", "medium", "low"], default=None)
    sp_add.add_argument("--url", default=None, help="URL (for reading items)")
    sp_add.set_defaults(func=cmd_add)

    sp_list = sub.add_parser("list", help="List open items")
    sp_list.add_argument("--type", choices=["task", "read"], default=None)
    sp_list.add_argument(
        "--domain",
        choices=["work", "personal"],
        default=None,
        help="With --type task: filter to work or personal only (default: both)",
    )
    sp_list.add_argument("--all", action="store_true", help="Include completed items")
    sp_list.add_argument("--json", action="store_true", help="Output as JSON (includes view_url per item)")
    sp_list.set_defaults(func=cmd_list)

    sp_done = sub.add_parser("done", help="Mark a task as done")
    sp_done.add_argument("task_id", help="Todoist task ID")
    sp_done.add_argument("--comment", default=None)
    sp_done.set_defaults(func=cmd_done)

    sp_cancel = sub.add_parser("cancel", help="Cancel a task")
    sp_cancel.add_argument("task_id", help="Todoist task ID")
    sp_cancel.add_argument("--comment", default=None, help="Reason for cancellation")
    sp_cancel.set_defaults(func=cmd_cancel)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
