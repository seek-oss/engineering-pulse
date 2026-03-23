#!/usr/bin/env python3
"""
Datadog Dashboard Extractor — fetches a dashboard definition via the
Datadog API, extracts every widget query, and runs the ones that map
cleanly to an API endpoint (metrics, logs analytics).

Env vars required:
    DD_API_KEY, DD_APP_KEY
    DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY  (default url-env)
    or any other URL env var passed via --url-env
Optional:
    DD_SITE        (default https://api.datadoghq.com)
    DATADOG_TEAMS  (comma-separated team names — overrides tpl_var_team in URL)

CLI args:
    --url           Dashboard URL (pass directly — preferred)
    --url-env       Name of env var holding the dashboard URL (fallback)
    --days          Override time window to past N days (0 = use URL timestamps)
    --focus         Comma-separated widget title substrings to highlight in output
    --output-slug   Prefix for output files (e.g. 'owner_metrics' → owner_metrics_metric_results.json)

Output files (under output/):
    [slug_]dashboard.json                      — full dashboard definition
    [slug_]dashboard_extracted_queries.json    — all extracted widget queries
    [slug_]metric_results.json                — latest metric points per query (for HTML report)
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

console = Console()

DD_API_KEY = os.environ["DD_API_KEY"]
DD_APP_KEY = os.environ["DD_APP_KEY"]
DD_SITE = os.environ.get("DD_SITE", "https://api.datadoghq.com")


def _snapshot_series(series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Latest point per series for persistence / HTML report."""
    rows: List[Dict[str, Any]] = []
    for s in series:
        pointlist = s.get("pointlist") or []
        last_val = pointlist[-1][1] if pointlist else None
        rows.append({"scope": s.get("scope", "—"), "latest": last_val})
    return rows


def _headers() -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "DD-API-KEY": DD_API_KEY,
        "DD-APPLICATION-KEY": DD_APP_KEY,
    }


# ---------------------------------------------------------------------------
# Dashboard fetching & parsing
# ---------------------------------------------------------------------------

def extract_dashboard_id(dashboard_url: str) -> str:
    m = re.search(r"/dashboard/([^/?]+)", dashboard_url)
    if not m:
        raise ValueError(f"Could not extract dashboard ID from URL: {dashboard_url}")
    return m.group(1)


def get_dashboard(dashboard_id: str) -> Dict[str, Any]:
    url = f"{DD_SITE}/api/v1/dashboard/{dashboard_id}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def flatten_widgets(widgets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recursively flatten group widgets that contain nested definition.widgets."""
    flat: List[Dict[str, Any]] = []
    for widget in widgets:
        flat.append(widget)
        nested = widget.get("definition", {}).get("widgets", [])
        if nested:
            flat.extend(flatten_widgets(nested))
    return flat


def detect_query_source(req: Dict[str, Any]) -> str:
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


def extract_widget_queries(dashboard_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    widgets = flatten_widgets(dashboard_json.get("widgets", []))
    extracted: List[Dict[str, Any]] = []
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
    template_variables: List[Dict[str, Any]],
    overrides: Optional[Dict[str, str]] = None,
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
# Query execution
# ---------------------------------------------------------------------------

def query_metrics_v1(query: str, from_ts: int, to_ts: int) -> Dict[str, Any]:
    url = f"{DD_SITE}/api/v1/query"
    params = {"from": from_ts, "to": to_ts, "query": query}
    resp = requests.get(url, headers=_headers(), params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def query_logs_aggregate(
    search_query: str,
    from_iso: str,
    to_iso: str,
    compute_aggregation: str = "count",
    compute_metric: Optional[str] = None,
    group_by_facet: Optional[str] = None,
    interval: Optional[str] = None,
) -> Dict[str, Any]:
    url = f"{DD_SITE}/api/v2/logs/analytics/aggregate"
    compute_obj: Dict[str, Any] = {"aggregation": compute_aggregation}
    if compute_metric:
        compute_obj["metric"] = compute_metric
    if interval:
        compute_obj["interval"] = interval
        compute_obj["type"] = "timeseries"

    payload: Dict[str, Any] = {
        "filter": {"from": from_iso, "to": to_iso, "query": search_query},
        "compute": [compute_obj],
    }
    if group_by_facet:
        payload["group_by"] = [{"facet": group_by_facet, "limit": 10}]

    resp = requests.post(url, headers=_headers(), json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Rich output helpers
# ---------------------------------------------------------------------------

def _source_style(source: str) -> str:
    mapping = {
        "metrics": "green",
        "metrics_formula": "green",
        "logs": "yellow",
        "apm": "yellow",
        "rum": "cyan",
        "process": "cyan",
    }
    return mapping.get(source, "red")


def print_extraction_summary(extracted: List[Dict[str, Any]]) -> None:
    source_counts: Dict[str, int] = {}
    for item in extracted:
        source_counts[item["source"]] = source_counts.get(item["source"], 0) + 1

    table = Table(title="Widget Query Sources", show_header=True, header_style="bold")
    table.add_column("Source", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("API Support")
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        style = _source_style(source)
        if source in ("metrics", "metrics_formula"):
            support = Text("auto-queryable", style="green")
        elif source == "logs":
            support = Text("partial (needs mapping)", style="yellow")
        else:
            support = Text("manual only", style="red")
        table.add_row(Text(source, style=style), str(count), support)
    console.print(table)


def print_extracted_requests(extracted: List[Dict[str, Any]]) -> None:
    table = Table(
        title="Extracted Widget Requests",
        show_header=True,
        header_style="bold",
        show_lines=True,
    )
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Title", max_width=40)
    table.add_column("Type", style="dim")
    table.add_column("Source")
    table.add_column("Request Keys", style="dim", max_width=40)

    for i, item in enumerate(extracted):
        style = _source_style(item["source"])
        table.add_row(
            str(i),
            (item["title"] or "—")[:40],
            item["widget_type"] or "—",
            Text(item["source"], style=style),
            ", ".join(sorted(item["request"].keys())),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Team URL helpers
# ---------------------------------------------------------------------------

def _extract_time_window(url: str) -> Optional[tuple]:
    """Extract from_ts / to_ts from the dashboard URL (both in milliseconds).

    Returns (from_epoch_sec, to_epoch_sec) as ints, or None if not present.
    When live=true is set the dashboard snaps to_ts to *now* — we honour that.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    raw_from = params.get("from_ts", [None])[0]
    raw_to   = params.get("to_ts",   [None])[0]
    if not raw_from or not raw_to:
        return None

    from_sec = int(raw_from) // 1000
    to_sec   = int(raw_to)   // 1000

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
        help="Dashboard URL (pass directly instead of via env var)",
    )
    parser.add_argument(
        "--url-env",
        default="",
        help="Name of the env var that holds the dashboard URL (fallback if --url not given)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="Override time window to past N days (0 = use URL timestamps)",
    )
    parser.add_argument(
        "--focus",
        default="",
        help="Comma-separated widget title substrings to highlight (case-insensitive)",
    )
    parser.add_argument(
        "--output-slug",
        default="",
        help="Slug prefix for output files (e.g. 'catalogue_quality' → output/catalogue_quality_metric_results.json)",
    )
    args = parser.parse_args()

    if args.url:
        dashboard_url = args.url
        console.print(f"[dim]URL: [cyan]{dashboard_url[:80]}…[/cyan][/dim]")
    else:
        url_env = args.url_env or "DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY"
        if url_env not in os.environ:
            console.print(f"[red]Error: env var '{url_env}' is not set.[/red]")
            sys.exit(1)
        dashboard_url = os.environ[url_env]
        console.print(f"[dim]URL env: [cyan]{url_env}[/cyan][/dim]")

    focus_terms = [t.strip().lower() for t in args.focus.split(",") if t.strip()]

    teams_csv = os.environ.get("DATADOG_TEAMS", "").strip()
    # Build overrides dict used when resolving template variables in queries
    query_overrides: Dict[str, str] = {}
    if teams_csv:
        dashboard_url = _apply_teams_to_url(dashboard_url, teams_csv)
        query_overrides["team"] = _teams_to_query_value(teams_csv)
        console.print(
            f"[dim]Using DATADOG_TEAMS override: "
            f"[cyan]{teams_csv}[/cyan] "
            f"→ query filter [cyan]team:{query_overrides['team']}[/cyan][/dim]"
        )

    # Time window: --days flag takes priority, then URL timestamps, then 30-day fallback.
    now = int(time.time())
    if args.days > 0:
        lookback = now - args.days * 86400
        console.print(
            f"[dim]Time window: past [cyan]{args.days}[/cyan] days "
            f"({round(args.days, 1)}d)[/dim]"
        )
    else:
        time_window = _extract_time_window(dashboard_url)
        if time_window:
            lookback, now = time_window
            console.print(
                f"[dim]Time window from URL: "
                f"[cyan]{lookback}[/cyan] → [cyan]{now}[/cyan] "
                f"({round((now - lookback) / 86400, 1)} days)[/dim]"
            )
        else:
            lookback = now - 2592000  # 30-day fallback
            console.print("[dim]No from_ts/to_ts in URL — using 30-day fallback window[/dim]")

    dashboard_id = extract_dashboard_id(dashboard_url)

    console.print(Panel(
        f"[bold]Datadog Dashboard Review[/bold]\nDashboard ID: [cyan]{dashboard_id}[/cyan]",
        border_style="blue",
    ))

    console.print("[dim]Fetching dashboard definition…[/dim]")
    dashboard = get_dashboard(dashboard_id)
    title = dashboard.get("title", "Untitled")
    total_widgets = len(flatten_widgets(dashboard.get("widgets", [])))

    console.print(f"  Title: [bold]{title}[/bold]")
    console.print(f"  Widgets (flat): [bold]{total_widgets}[/bold]")
    console.print()

    extracted = extract_widget_queries(dashboard)
    template_vars = dashboard.get("template_variables", [])

    if template_vars:
        console.print("[dim]Template variables (effective values for queries):[/dim]")
        for tv in template_vars:
            name = tv.get("name", "")
            prefix = tv.get("prefix", "")
            if name in query_overrides:
                value = query_overrides[name]
                source_note = "[yellow](from DATADOG_TEAMS)[/yellow]"
            else:
                default = tv.get("default") or tv.get("defaults", ["*"])
                if isinstance(default, list):
                    default = default[0] if default else "*"
                value = default or "*"
                source_note = "[dim](dashboard default)[/dim]"
            console.print(f"  ${name} → {prefix}:{value}  {source_note}")
        console.print()

    # --- Summary tables ---
    print_extraction_summary(extracted)
    console.print()
    print_extracted_requests(extracted)
    console.print()

    # --- Execute metric queries ---
    metric_results: List[Dict[str, Any]] = []
    errors: List[str] = []
    skipped: List[str] = []

    for item in extracted:
        req = item["request"]
        source = item["source"]
        widget_label = item["title"] or f"widget#{item['widget_index']}"

        is_focused = focus_terms and any(
            t in widget_label.lower() for t in focus_terms
        )
        label_styled = (
            f"[bold yellow]{widget_label}[/bold yellow] [yellow]★ focus[/yellow]"
            if is_focused else f"[bold]{widget_label}[/bold]"
        )

        if source == "metrics" and isinstance(req.get("q"), str):
            q = resolve_template_variables(req["q"], template_vars, query_overrides)
            console.print(f"[green]▶[/green] Metric query — {label_styled}")
            console.print(f"  [dim]{q}[/dim]")
            try:
                result = query_metrics_v1(q, lookback, now)
                series = result.get("series", [])
                snap = _snapshot_series(series)
                metric_results.append(
                    {
                        "widget_title": widget_label,
                        "kind": "metrics",
                        "query": q,
                        "series": snap,
                    }
                )
                console.print(f"  → {len(series)} series returned")

                for row in snap[:3]:
                    scope = row["scope"]
                    last_val = row["latest"]
                    val_str = f"{last_val:.2f}" if last_val is not None else "null"
                    console.print(f"    [dim]{scope}[/dim]  latest={val_str}")
                if len(snap) > 3:
                    console.print(f"    [dim]… +{len(snap) - 3} more series[/dim]")
            except requests.HTTPError as e:
                msg = f"Metric query failed for '{widget_label}': {e}"
                errors.append(msg)
                console.print(f"  [red]✗ {e}[/red]")
            console.print()

        elif source == "metrics_formula":
            queries = req.get("queries", [])
            for qobj in queries:
                metric_query = qobj.get("query")
                if not metric_query:
                    continue
                metric_query = resolve_template_variables(metric_query, template_vars, query_overrides)
                console.print(f"[green]▶[/green] Formula base query — {label_styled}")
                console.print(f"  [dim]{metric_query}[/dim]")
                try:
                    result = query_metrics_v1(metric_query, lookback, now)
                    series = result.get("series", [])
                    snap = _snapshot_series(series)
                    metric_results.append(
                        {
                            "widget_title": widget_label,
                            "kind": "metrics_formula_base",
                            "subquery": qobj.get("name"),
                            "query": metric_query,
                            "series": snap,
                        }
                    )
                    console.print(f"  → {len(series)} series returned")

                    for row in snap[:3]:
                        scope = row["scope"]
                        last_val = row["latest"]
                        val_str = f"{last_val:.2f}" if last_val is not None else "null"
                        console.print(f"    [dim]{scope}[/dim]  latest={val_str}")
                    if len(snap) > 3:
                        console.print(f"    [dim]… +{len(snap) - 3} more series[/dim]")
                except requests.HTTPError as e:
                    msg = f"Formula base query failed for '{widget_label}': {e}"
                    errors.append(msg)
                    console.print(f"  [red]✗ {e}[/red]")
                console.print()

        elif source == "logs":
            skipped.append(f"Logs widget '{widget_label}' — saved for manual mapping")

        elif source not in ("metrics", "metrics_formula"):
            skipped.append(f"{source} widget '{widget_label}' — no auto handler")

    # --- Final summary panel ---
    console.print()
    summary_parts = []
    summary_parts.append(f"[bold]Dashboard:[/bold] {title}")
    summary_parts.append(f"[bold]Total widgets:[/bold] {total_widgets}")
    summary_parts.append(f"[bold]Extracted requests:[/bold] {len(extracted)}")
    summary_parts.append(f"[bold]Metric queries executed:[/bold] {len(metric_results)}")  # rows, not unique widgets

    if errors:
        summary_parts.append("")
        summary_parts.append("[red bold]Errors:[/red bold]")
        for err in errors:
            summary_parts.append(f"  [red]• {err}[/red]")

    if skipped:
        summary_parts.append("")
        summary_parts.append("[yellow bold]Skipped (no auto handler):[/yellow bold]")
        for s in skipped:
            summary_parts.append(f"  [yellow]• {s}[/yellow]")

    border = "green" if not errors else "red" if len(errors) > 2 else "yellow"
    console.print(Panel("\n".join(summary_parts), title="Summary", border_style=border))

    # --- Write output files ---
    out_dir = Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    prefix = f"{args.output_slug}_" if args.output_slug else ""

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
                "generated_at": datetime.now(timezone.utc).isoformat(),
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


if __name__ == "__main__":
    main()
