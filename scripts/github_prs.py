#!/usr/bin/env python3
"""
GitHub PR Review Queue

Lists open PRs where:
  1. You are a requested reviewer, OR
  2. Your team (GITHUB_TEAM) is a requested reviewer

Two ways to get the data:

  GitHub MCP (default)  The agent runs the two searches with GitHub MCP, saves the raw
                        responses, and this script normalises them:
                          python scripts/github_prs.py --from-mcp output/github_mcp_prs.json
  GitHub token          Without --from-mcp the script queries the GitHub GraphQL API
                        itself; needs GITHUB_TOKEN (PAT with repo + read:org scopes).

Env vars:
    GITHUB_TEAM    — team as org/team (e.g. my-org/platform); a bare team slug
                     plus GITHUB_ORG also works
    GITHUB_TOKEN   — only for the token path

MCP file format: {"username": "<login>", "results": [<search response>, ...]}, where
each search response is the GitHub MCP search_pull_requests output ({"items": [...]}).

Output: saves output/github_prs.json, prints table.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

console = Console()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or ""
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "output" / "github_prs.json"


def team_spec() -> tuple[str, str] | None:
    """Return (org, team) from GITHUB_TEAM=org/team, or the legacy GITHUB_ORG + GITHUB_TEAM."""
    team = os.environ.get("GITHUB_TEAM", "").strip()
    if "/" in team:
        org, _, slug = team.partition("/")
    else:
        org, slug = os.environ.get("GITHUB_ORG", "").strip(), team
    return (org, slug) if org and slug else None


REST_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
GQL_URL = "https://api.github.com/graphql"


# ---------------------------------------------------------------------------
# GraphQL helper
# ---------------------------------------------------------------------------

GQL_SEARCH = """
query($q: String!, $cursor: String) {
  search(query: $q, type: ISSUE, first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        url
        isDraft
        createdAt
        updatedAt
        author { login }
        repository { nameWithOwner }
        labels(first: 10) { nodes { name } }
      }
    }
  }
}
"""


def gql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(
        GQL_URL,
        headers={**REST_HEADERS, "Accept": "application/json"},
        json={"query": query, "variables": variables},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(f"GraphQL errors: {data['errors']}")
    return data["data"]


MAX_PAGES = 4  # cap at 200 PRs per query (4 × 50) to avoid hanging on large teams


def graphql_search_all(q: str) -> list[dict[str, Any]]:
    """Paginate through GraphQL search results for query *q*, capped at MAX_PAGES."""
    results = []
    cursor: str | None = None
    for page_num in range(1, MAX_PAGES + 1):
        data = gql(GQL_SEARCH, {"q": q, "cursor": cursor})
        nodes = data["search"]["nodes"]
        results.extend(nodes)
        page = data["search"]["pageInfo"]
        console.print(
            f"  [dim]  page {page_num}: +{len(nodes)} results ({len(results)} total)[/dim]"
        )
        if not page["hasNextPage"]:
            break
        if page_num == MAX_PAGES:
            console.print(
                f"  [yellow]  ⚠ hit page cap ({MAX_PAGES} pages / {len(results)} PRs) — results truncated[/yellow]"
            )
            break
        cursor = page["endCursor"]
    return results


# ---------------------------------------------------------------------------
# REST fallback — get authenticated user
# ---------------------------------------------------------------------------


def get_authenticated_user() -> str:
    resp = requests.get("https://api.github.com/user", headers=REST_HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()["login"]


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------


def format_pr(node: dict[str, Any]) -> dict[str, Any]:
    created_at = datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00"))
    updated_at = datetime.fromisoformat(node["updatedAt"].replace("Z", "+00:00"))
    now = datetime.now(UTC)
    return {
        "number": node["number"],
        "title": node["title"],
        "repo": node["repository"]["nameWithOwner"],
        "author": (node["author"] or {}).get("login", "unknown"),
        "age_days": (now - created_at).days,
        "updated_days": (now - updated_at).days,
        "url": node["url"],
        "labels": [lbl["name"] for lbl in node["labels"]["nodes"]],
        "draft": node["isDraft"],
    }


def format_rest_pr(item: dict[str, Any]) -> dict[str, Any]:
    """Normalise a REST search item (GitHub MCP search_pull_requests) like format_pr."""
    created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    updated_at = datetime.fromisoformat(
        (item.get("updated_at") or item["created_at"]).replace("Z", "+00:00")
    )
    now = datetime.now(UTC)
    repo_url = item.get("repository_url") or ""
    repo = repo_url.split("/repos/", 1)[1] if "/repos/" in repo_url else repo_url
    return {
        "number": item["number"],
        "title": item["title"],
        "repo": repo,
        "author": (item.get("user") or {}).get("login", "unknown"),
        "age_days": (now - created_at).days,
        "updated_days": (now - updated_at).days,
        "url": item["html_url"],
        "labels": [lbl["name"] for lbl in item.get("labels") or [] if "name" in lbl],
        "draft": bool(item.get("draft")),
    }


def finalize(prs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort newest first and drop automated dependency PRs (not actionable for review)."""
    ordered = sorted(prs, key=lambda x: x["age_days"])
    return [pr for pr in ordered if not pr["author"].lower().startswith("renovate")]


def load_mcp_results(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Read saved GitHub MCP search responses; return (username, normalised PRs)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"results": data}
    seen: dict[str, dict[str, Any]] = {}
    for result in data.get("results") or []:
        items = result.get("items", []) if isinstance(result, dict) else result
        for item in items or []:
            if isinstance(item, dict) and item.get("html_url") and item.get("created_at"):
                seen[item["html_url"]] = format_rest_pr(item)
    return data.get("username") or "", finalize(list(seen.values()))


# ---------------------------------------------------------------------------
# Main fetch
# ---------------------------------------------------------------------------


def fetch_review_prs(username: str) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}

    # 1. PRs where I am a requested reviewer (GraphQL search)
    q1 = f"is:open is:pr review-requested:{username}"
    console.print(f"[dim]GraphQL search: {q1}[/dim]")
    try:
        for node in graphql_search_all(q1):
            if node:  # skip nulls (non-PR search hits)
                seen[node["url"]] = format_pr(node)
        console.print(f"  [dim]→ {len(seen)} PR(s)[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Warning (user search): {e}[/yellow]")

    # 2. PRs where the team is a requested reviewer (GraphQL search)
    team = team_spec()
    if team:
        q2 = f"is:open is:pr team-review-requested:{team[0]}/{team[1]}"
        console.print(f"[dim]GraphQL search: {q2}[/dim]")
        before = len(seen)
        try:
            for node in graphql_search_all(q2):
                if node:
                    seen[node["url"]] = format_pr(node)
            console.print(f"  [dim]→ {len(seen) - before} new PR(s)[/dim]")
        except Exception as e:
            console.print(f"  [yellow]Warning (team search): {e}[/yellow]")

    return finalize(list(seen.values()))


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def print_table(prs: list[dict[str, Any]]) -> None:
    if not prs:
        console.print("[green]✓ No PRs awaiting review.[/green]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("#", style="dim", width=6)
    table.add_column("Repo", width=32)
    table.add_column("Title", width=48)
    table.add_column("Author", width=16)
    table.add_column("Age", width=5)
    table.add_column("Updated", width=9)

    for pr in prs:
        age_str = f"{pr['age_days']}d"
        upd_str = f"{pr['updated_days']}d ago"
        age_col = (
            f"[red]{age_str}[/red]"
            if pr["age_days"] >= 5
            else f"[yellow]{age_str}[/yellow]"
            if pr["age_days"] >= 2
            else age_str
        )
        draft = " [dim](draft)[/dim]" if pr["draft"] else ""
        table.add_row(
            str(pr["number"]),
            pr["repo"],
            pr["title"][:47] + draft,
            pr["author"],
            age_col,
            upd_str,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the PR review queue (output/github_prs.json)")
    ap.add_argument("--from-mcp", type=Path, help="saved GitHub MCP search responses")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    if args.from_mcp:
        try:
            username, prs = load_mcp_results(args.from_mcp)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            console.print(f"[red]Could not read GitHub MCP results {args.from_mcp}: {exc}[/red]")
            return 1
    elif GITHUB_TOKEN:
        if not team_spec():
            console.print("[yellow]GITHUB_TEAM is not set — team PR search skipped.[/yellow]")
        username = get_authenticated_user()
        console.print(f"[dim]Authenticated as: [cyan]{username}[/cyan][/dim]")
        prs = fetch_review_prs(username)
    else:
        console.print(
            "[red]No PR data source.[/red] Fetch PRs with GitHub MCP and pass "
            "--from-mcp FILE (see skills/engineering-pulse/references/daily-workflow.md "
            "Step 2C), or set GITHUB_TOKEN in .env."
        )
        return 2

    console.print(f"\n[bold]{len(prs)} PR(s) awaiting review[/bold]\n")
    print_table(prs)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"username": username, "prs": prs}, indent=2), encoding="utf-8")
    console.print(f"\n[dim]Saved → {args.out}[/dim]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
