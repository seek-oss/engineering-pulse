#!/usr/bin/env python3
"""
Datadog Dashboard Extractor — build ``output/<slug>_metric_results.json`` for the
daily HTML report.

Agent + Datadog MCP (no API keys):

    1. Agent calls MCP ``get_datadog_dashboard`` → save ``output/<slug>_dashboard.json``
    2. ``--from-dashboard-json`` → ``*_mcp_query_plan.json`` (+ extracted queries)
    3. Agent calls MCP ``get_datadog_metric`` for each planned query →
       ``output/<slug>_mcp_responses.json``
    4. ``--from-mcp-responses`` → ``*_metric_results.json``

Optional:
    DATADOG_TEAMS  (comma-separated — overrides tpl_var_team in URL and query filters)
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

console = Console()


# ---------------------------------------------------------------------------
# Dashboard parsing
# ---------------------------------------------------------------------------


def extract_dashboard_id(dashboard_url: str) -> str:
    m = re.search(r"/dashboard/([^/?]+)", dashboard_url)
    if not m:
        raise ValueError(f"Could not extract dashboard ID from URL: {dashboard_url}")
    return m.group(1)


def flatten_widgets(widgets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recursively flatten group widgets that contain nested definition.widgets."""
    flat: list[dict[str, Any]] = []
    for widget in widgets:
        flat.append(widget)
        nested = widget.get("definition", {}).get("widgets", [])
        if nested:
            flat.extend(flatten_widgets(nested))
    return flat


def detect_query_source(req: dict[str, Any]) -> str:
    if "q" in req and isinstance(req["q"], str):
        q = req["q"].strip()
        if re.match(r"^(avg|min|max|sum|count|p\d{2}|p\d{2}\.\d+):", q):
            return "metrics"
        return "unknown_q"

    if "queries" in req:
        queries = req["queries"]
        if isinstance(queries, list) and queries:
            sources = {q.get("data_source") for q in queries if isinstance(q, dict)}
            if "metrics" in sources:
                return "metrics_formula"
            if "logs" in sources:
                return "logs"
            if sources & {"apm_resource_stats", "traces"}:
                return "apm"
            if "rum" in sources:
                return "rum"
            if "process" in sources:
                return "process"
            return "formula_or_other"

    if "log_query" in req:
        return "logs"

    return "unknown"


def extract_widget_queries(dashboard_json: dict[str, Any]) -> list[dict[str, Any]]:
    widgets = flatten_widgets(dashboard_json.get("widgets", []))
    extracted: list[dict[str, Any]] = []
    for idx, widget in enumerate(widgets):
        definition = widget.get("definition", {})
        for req_idx, req in enumerate(definition.get("requests", [])):
            extracted.append(
                {
                    "widget_index": idx,
                    "request_index": req_idx,
                    "title": definition.get("title"),
                    "widget_type": definition.get("type"),
                    "source": detect_query_source(req),
                    "request": req,
                }
            )
    return extracted


# ---------------------------------------------------------------------------
# Template variable substitution
# ---------------------------------------------------------------------------


def resolve_template_variables(
    query: str,
    template_variables: list[dict[str, Any]],
    overrides: dict[str, str] | None = None,
) -> str:
    """Replace $var placeholders with prefix:value so the Datadog API can
    evaluate the query.  *overrides* maps variable name → value and takes
    precedence over the dashboard default."""
    overrides = overrides or {}
    for tv in template_variables:
        name = tv.get("name", "")
        prefix = tv.get("prefix", "")
        if name in overrides:
            value = overrides[name]
        else:
            default = tv.get("default") or tv.get("defaults", ["*"])
            if isinstance(default, list):
                default = default[0] if default else "*"
            if not default or default == "":
                default = "*"
            value = default
        replacement = f"{prefix}:{value}" if prefix else value
        query = query.replace(f"${name}", replacement)
    return query


def _teams_to_query_value(teams_csv: str) -> str:
    """Convert comma-separated team names to a Datadog metric query value.

    Single team  → ``team-a``
    Multiple     → ``(team-a OR team-b)``
    """
    teams = [t.strip() for t in teams_csv.split(",") if t.strip()]
    if not teams:
        return "*"
    if len(teams) == 1:
        return teams[0]
    return "(" + " OR ".join(teams) + ")"


# ---------------------------------------------------------------------------
# Datadog MCP offline pipeline (no REST keys)
# ---------------------------------------------------------------------------


def normalize_mcp_dashboard(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept REST dashboard JSON or MCP ``get_datadog_dashboard`` payload."""
    if not isinstance(raw, dict):
        raise ValueError("Dashboard JSON must be an object")
    if "widgets" not in raw:
        raise ValueError("Dashboard JSON missing 'widgets'")
    return {
        "title": raw.get("title", "Untitled"),
        "widgets": raw.get("widgets") or [],
        "template_variables": raw.get("template_variables") or [],
    }


def iter_metric_query_jobs(
    extracted: list[dict[str, Any]],
    template_vars: list[dict[str, Any]],
    query_overrides: dict[str, str],
) -> list[dict[str, Any]]:
    """Resolved metric queries for MCP ``get_datadog_metric``."""
    jobs: list[dict[str, Any]] = []
    for item in extracted:
        req = item["request"]
        source = item["source"]
        widget_label = item["title"] or f"widget#{item['widget_index']}"

        if source == "metrics" and isinstance(req.get("q"), str):
            q = resolve_template_variables(req["q"], template_vars, query_overrides)
            jobs.append({"widget_title": widget_label, "kind": "metrics", "query": q})
        elif source == "metrics_formula":
            for qobj in req.get("queries", []):
                metric_query = qobj.get("query")
                if not metric_query:
                    continue
                metric_query = resolve_template_variables(
                    metric_query, template_vars, query_overrides
                )
                jobs.append(
                    {
                        "widget_title": widget_label,
                        "kind": "metrics_formula_base",
                        "subquery": qobj.get("name"),
                        "query": metric_query,
                    }
                )
    return jobs


def snapshot_from_mcp_metric_data(data: Any) -> list[dict[str, Any]]:
    """Convert MCP ``get_datadog_metric`` JSON_DATA to ``{scope, latest}`` rows."""
    if data is None:
        return [{"scope": "—", "latest": None}]

    parsed: Any = data
    if isinstance(parsed, str):
        parsed = json.loads(parsed.strip())
    if isinstance(parsed, dict) and "values" in parsed:
        parsed = [parsed]
    if not isinstance(parsed, list):
        return [{"scope": "—", "latest": None}]

    rows: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("values"), dict):
            for scope, val in item["values"].items():
                rows.append(
                    {
                        "scope": str(scope),
                        "latest": float(val) if val is not None else None,
                    }
                )
            continue

        scope = item.get("scope") or item.get("expression") or "—"
        latest: float | None = None
        binned = item.get("binned")
        if isinstance(binned, list) and binned:
            last_bin = binned[-1]
            if isinstance(last_bin, dict):
                latest = last_bin.get("avg")
                if latest is None:
                    latest = last_bin.get("max")
        if latest is None:
            stats = item.get("overall_stats")
            if isinstance(stats, dict):
                latest = stats.get("avg")
        if latest is not None:
            latest = float(latest)
        rows.append({"scope": str(scope), "latest": latest})

    return rows or [{"scope": "—", "latest": None}]


def build_metric_results_from_mcp_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    metric_results: list[dict[str, Any]] = []
    for entry in bundle.get("responses") or []:
        if not isinstance(entry, dict):
            continue
        snap = snapshot_from_mcp_metric_data(entry.get("data"))
        row: dict[str, Any] = {
            "widget_title": entry.get("widget_title") or "—",
            "kind": entry.get("kind") or "metrics",
            "query": entry.get("query") or "",
            "series": snap,
        }
        sub = entry.get("subquery")
        if sub:
            row["subquery"] = sub
            row["kind"] = "metrics_formula_base"
        metric_results.append(row)
    return metric_results


def resolve_query_overrides_and_url(dashboard_url: str) -> tuple[str, dict[str, str]]:
    teams_csv = os.environ.get("DATADOG_TEAMS", "").strip()
    query_overrides: dict[str, str] = {}
    url = dashboard_url
    if teams_csv:
        url = _apply_teams_to_url(url, teams_csv)
        query_overrides["team"] = _teams_to_query_value(teams_csv)
        console.print(
            f"[dim]Using DATADOG_TEAMS override: "
            f"[cyan]{teams_csv}[/cyan] "
            f"→ query filter [cyan]team:{query_overrides['team']}[/cyan][/dim]"
        )
    return url, query_overrides


def resolve_lookback_window(days: int, dashboard_url: str) -> tuple[int, int]:
    now = int(time.time())
    if days > 0:
        lookback = now - days * 86400
        console.print(f"[dim]Time window: past [cyan]{days}[/cyan] days ({round(days, 1)}d)[/dim]")
        return lookback, now

    time_window = _extract_time_window(dashboard_url)
    if time_window:
        lookback, end = time_window
        console.print(
            f"[dim]Time window from URL: "
            f"[cyan]{lookback}[/cyan] → [cyan]{end}[/cyan] "
            f"({round((end - lookback) / 86400, 1)} days)[/dim]"
        )
        return lookback, end

    lookback = now - 2592000
    console.print("[dim]No from_ts/to_ts in URL — using 30-day fallback window[/dim]")
    return lookback, now


def _output_prefix(slug: str) -> str:
    return f"{slug}_" if slug else ""


def _write_metric_snapshot(
    out_dir: Path,
    prefix: str,
    *,
    title: str,
    dashboard_url: str,
    dashboard: dict[str, Any],
    extracted: list[dict[str, Any]],
    metric_results: list[dict[str, Any]],
) -> None:
    out_dir.mkdir(exist_ok=True)
    fname_dash = f"{prefix}dashboard.json"
    fname_queries = f"{prefix}dashboard_extracted_queries.json"
    fname_results = f"{prefix}metric_results.json"

    with open(out_dir / fname_dash, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)

    with open(out_dir / fname_queries, "w", encoding="utf-8") as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)

    with open(out_dir / fname_results, "w", encoding="utf-8") as f:
        json.dump(
            {
                "dashboard_title": title,
                "source_url": dashboard_url,
                "generated_at": datetime.now(UTC).isoformat(),
                "results": metric_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    console.print()
    console.print("[dim]Saved:[/dim]")
    console.print(f"  • output/{fname_dash}")
    console.print(f"  • output/{fname_queries}")
    console.print(f"  • output/{fname_results}")


def run_mcp_query_plan(
    dashboard_path: Path,
    dashboard_url: str,
    output_slug: str,
    days: int,
) -> None:
    raw = json.loads(dashboard_path.read_text(encoding="utf-8"))
    dashboard = normalize_mcp_dashboard(raw)
    dashboard_url, query_overrides = resolve_query_overrides_and_url(dashboard_url)
    resolve_lookback_window(days, dashboard_url)

    title = dashboard.get("title", "Untitled")
    extracted = extract_widget_queries(dashboard)
    jobs = iter_metric_query_jobs(
        extracted,
        dashboard.get("template_variables") or [],
        query_overrides,
    )

    for i, job in enumerate(jobs):
        job["id"] = str(i)

    out_dir = Path(__file__).resolve().parent.parent / "output"
    prefix = _output_prefix(output_slug)
    plan = {
        "dashboard_title": title,
        "source_url": dashboard_url,
        "generated_at": datetime.now(UTC).isoformat(),
        "time_window": {"from": f"now-{days}d" if days > 0 else "now-7d", "to": "now"},
        "mcp_tool": "get_datadog_metric",
        "mcp_recommended_args": {
            "response_format": "scalar",
            "queries": "one plan entry per call; use structured query with query + aggregator last",
        },
        "queries": jobs,
    }

    out_dir.mkdir(exist_ok=True)
    fname_dash = f"{prefix}dashboard.json"
    fname_queries = f"{prefix}dashboard_extracted_queries.json"
    with open(out_dir / fname_dash, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)
    with open(out_dir / fname_queries, "w", encoding="utf-8") as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)

    plan_path = out_dir / f"{prefix}mcp_query_plan.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    console.print("[dim]Saved:[/dim]")
    console.print(f"  • output/{fname_dash}")
    console.print(f"  • output/{fname_queries}")
    console.print(f"  • output/{prefix}mcp_query_plan.json")
    console.print(
        f"[green]Planned {len(jobs)} metric queries[/green] — fetch via Datadog MCP, "
        f"then run with --from-mcp-responses"
    )


def run_mcp_build_results(
    responses_path: Path,
    dashboard_url: str,
    output_slug: str,
) -> None:
    bundle = json.loads(responses_path.read_text(encoding="utf-8"))
    metric_results = build_metric_results_from_mcp_bundle(bundle)
    title = bundle.get("dashboard_title") or "Untitled"
    dashboard_url = bundle.get("source_url") or dashboard_url

    out_dir = Path(__file__).resolve().parent.parent / "output"
    prefix = _output_prefix(output_slug)
    dash_path = out_dir / f"{prefix}dashboard.json"
    queries_path = out_dir / f"{prefix}dashboard_extracted_queries.json"

    dashboard: dict[str, Any] = {"title": title, "widgets": [], "template_variables": []}
    extracted: list[dict[str, Any]] = []
    if dash_path.is_file():
        dashboard = normalize_mcp_dashboard(json.loads(dash_path.read_text(encoding="utf-8")))
    if queries_path.is_file():
        extracted = json.loads(queries_path.read_text(encoding="utf-8"))

    _write_metric_snapshot(
        out_dir,
        prefix,
        title=title,
        dashboard_url=dashboard_url,
        dashboard=dashboard,
        extracted=extracted,
        metric_results=metric_results,
    )
    console.print(
        f"[green]Built {len(metric_results)} metric result rows from MCP responses[/green]"
    )


# ---------------------------------------------------------------------------
# Team URL helpers
# ---------------------------------------------------------------------------


def _extract_time_window(url: str) -> tuple | None:
    """Extract from_ts / to_ts from the dashboard URL (both in milliseconds).

    Returns (from_epoch_sec, to_epoch_sec) as ints, or None if not present.
    When live=true is set the dashboard snaps to_ts to *now* — we honour that.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    raw_from = params.get("from_ts", [None])[0]
    raw_to = params.get("to_ts", [None])[0]
    if not raw_from or not raw_to:
        return None

    from_sec = int(raw_from) // 1000
    to_sec = int(raw_to) // 1000

    live = params.get("live", ["false"])[0].lower() == "true"
    if live:
        to_sec = int(time.time())

    return from_sec, to_sec


def _apply_teams_to_url(url: str, teams_csv: str) -> str:
    """Replace all tpl_var_team query parameters in *url* with the teams
    listed in *teams_csv* (comma-separated).  All other params are preserved."""
    teams = [t.strip() for t in teams_csv.split(",") if t.strip()]
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    # Drop every existing tpl_var_team[*] key
    params = {k: v for k, v in params.items() if not re.match(r"tpl_var_team\[", k)}

    # Add new indexed keys
    for i, team in enumerate(teams):
        params[f"tpl_var_team[{i}]"] = [team]

    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Datadog Dashboard Extractor")
    parser.add_argument(
        "--url",
        default="",
        help="Dashboard URL (required with --from-dashboard-json; optional metadata for --from-mcp-responses)",
    )
    parser.add_argument(
        "--from-dashboard-json",
        default="",
        metavar="FILE",
        help="MCP mode: build query plan from saved get_datadog_dashboard JSON (requires --url, --output-slug)",
    )
    parser.add_argument(
        "--from-mcp-responses",
        default="",
        metavar="FILE",
        help="MCP mode: build metric_results.json from agent MCP response bundle",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="Override time window to past N days (0 = use URL timestamps; MCP plan defaults to 7)",
    )
    parser.add_argument(
        "--output-slug",
        default="",
        help="Slug prefix for output files (e.g. 'my_dashboard' → output/my_dashboard_metric_results.json)",
    )
    args = parser.parse_args()

    if args.from_mcp_responses:
        if not args.output_slug:
            console.print("[red]Error: --from-mcp-responses requires --output-slug.[/red]")
            sys.exit(1)
        path = Path(args.from_mcp_responses)
        if not path.is_file():
            console.print(f"[red]Error: MCP responses file not found: {path}[/red]")
            sys.exit(1)
        url = args.url or ""
        run_mcp_build_results(path, url, args.output_slug)
        return

    if args.from_dashboard_json:
        if not args.url or not args.output_slug:
            console.print(
                "[red]Error: --from-dashboard-json requires --url and --output-slug.[/red]"
            )
            sys.exit(1)
        path = Path(args.from_dashboard_json)
        if not path.is_file():
            console.print(f"[red]Error: dashboard JSON not found: {path}[/red]")
            sys.exit(1)
        days = args.days if args.days > 0 else 7
        run_mcp_query_plan(path, args.url, args.output_slug, days)
        return

    console.print(
        "[red]Error: Datadog extract is MCP-only.[/red]\n"
        "[dim]Use --from-dashboard-json or --from-mcp-responses "
        "(see skills/engineering-pulse/references/datadog-mcp-extract.md). "
        "Fetch dashboard JSON and metrics via Datadog MCP in the agent session.[/dim]"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
