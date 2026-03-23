#!/usr/bin/env python3
"""
GitHub PR Review Queue

Fetches open PRs where:
  1. The authenticated user is a requested reviewer, OR
  2. GITHUB_ORG/GITHUB_TEAM is a requested reviewer

Uses the GitHub GraphQL API (more reliable for org-level team queries
than the REST search endpoint which requires additional org scopes).

Env vars required:
    GITHUB_TOKEN   — PAT with repo + read:org scopes
    GITHUB_ORG     — GitHub org slug  (e.g. my-org)
    GITHUB_TEAM    — team slug (e.g. my-team)

Output: saves github_prs.json, prints table.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

console = Console()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or ""
GITHUB_ORG   = os.environ.get("GITHUB_ORG", "")
TEAM_SLUG    = os.environ.get("GITHUB_TEAM", "")

if not GITHUB_TOKEN:
    print("Error: GITHUB_TOKEN is required. Set it in .env.", file=sys.stderr)
    sys.exit(1)
if not GITHUB_ORG or not TEAM_SLUG:
    print("Warning: GITHUB_ORG and GITHUB_TEAM are not set — team PR search will be skipped.", file=sys.stderr)

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


def gql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
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


def graphql_search_all(q: str) -> List[Dict[str, Any]]:
    """Paginate through GraphQL search results for query *q*, capped at MAX_PAGES."""
    results = []
    cursor: Optional[str] = None
    for page_num in range(1, MAX_PAGES + 1):
        data = gql(GQL_SEARCH, {"q": q, "cursor": cursor})
        nodes = data["search"]["nodes"]
        results.extend(nodes)
        page = data["search"]["pageInfo"]
        console.print(f"  [dim]  page {page_num}: +{len(nodes)} results ({len(results)} total)[/dim]")
        if not page["hasNextPage"]:
            break
        if page_num == MAX_PAGES:
            console.print(f"  [yellow]  ⚠ hit page cap ({MAX_PAGES} pages / {len(results)} PRs) — results truncated[/yellow]")
            break
        cursor = page["endCursor"]
    return results


# ---------------------------------------------------------------------------
# REST fallback — get authenticated user
# ---------------------------------------------------------------------------

def get_authenticated_user() -> str:
    resp = requests.get(
        "https://api.github.com/user", headers=REST_HEADERS, timeout=10
    )
    resp.raise_for_status()
    return resp.json()["login"]


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------

def format_pr(node: Dict[str, Any]) -> Dict[str, Any]:
    created_at = datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00"))
    updated_at = datetime.fromisoformat(node["updatedAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return {
        "number":       node["number"],
        "title":        node["title"],
        "repo":         node["repository"]["nameWithOwner"],
        "author":       (node["author"] or {}).get("login", "unknown"),
        "age_days":     (now - created_at).days,
        "updated_days": (now - updated_at).days,
        "url":          node["url"],
        "labels":       [lbl["name"] for lbl in node["labels"]["nodes"]],
        "draft":        node["isDraft"],
    }


# ---------------------------------------------------------------------------
# Main fetch
# ---------------------------------------------------------------------------

def fetch_review_prs(username: str) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}

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
    if GITHUB_ORG and TEAM_SLUG:
        q2 = f"is:open is:pr team-review-requested:{GITHUB_ORG}/{TEAM_SLUG}"
        console.print(f"[dim]GraphQL search: {q2}[/dim]")
        before = len(seen)
        try:
            for node in graphql_search_all(q2):
                if node:
                    seen[node["url"]] = format_pr(node)
            console.print(f"  [dim]→ {len(seen) - before} new PR(s)[/dim]")
        except Exception as e:
            console.print(f"  [yellow]Warning (team search): {e}[/yellow]")

    all_prs = sorted(seen.values(), key=lambda x: x["age_days"], reverse=False)
    # Exclude automated dependency PRs — not actionable for human review
    return [pr for pr in all_prs if not pr["author"].lower().startswith("renovate")]


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_table(prs: List[Dict[str, Any]]) -> None:
    if not prs:
        console.print("[green]✓ No PRs awaiting review.[/green]")
        return

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("#",        style="dim", width=6)
    table.add_column("Repo",     width=32)
    table.add_column("Title",    width=48)
    table.add_column("Author",   width=16)
    table.add_column("Age",      width=5)
    table.add_column("Updated",  width=9)

    for pr in prs:
        age_str = f"{pr['age_days']}d"
        upd_str = f"{pr['updated_days']}d ago"
        age_col = (
            f"[red]{age_str}[/red]"    if pr["age_days"] >= 5 else
            f"[yellow]{age_str}[/yellow]" if pr["age_days"] >= 2 else age_str
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

if __name__ == "__main__":
    username = get_authenticated_user()
    console.print(f"[dim]Authenticated as: [cyan]{username}[/cyan][/dim]")

    prs = fetch_review_prs(username)

    console.print(f"\n[bold]{len(prs)} PR(s) awaiting review[/bold]\n")
    print_table(prs)

    out_dir = Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "github_prs.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"username": username, "prs": prs}, f, indent=2)
    console.print(f"\n[dim]Saved → output/github_prs.json[/dim]")
