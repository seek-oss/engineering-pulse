"""Tests for Datadog MCP offline pipeline helpers."""

from scripts.datadog_dashboard_extract import (
    build_metric_results_from_mcp_bundle,
    iter_metric_query_jobs,
    normalize_mcp_dashboard,
    snapshot_from_mcp_metric_data,
)


def test_normalize_mcp_dashboard_minimal():
    raw = {"title": "T", "widgets": [{"definition": {"type": "note"}}]}
    out = normalize_mcp_dashboard(raw)
    assert out["title"] == "T"
    assert len(out["widgets"]) == 1
    assert out["template_variables"] == []


def test_snapshot_scalar_values():
    data = [{"values": {"avg:foo{*}": 42.5}}]
    rows = snapshot_from_mcp_metric_data(data)
    assert rows == [{"scope": "avg:foo{*}", "latest": 42.5}]


def test_snapshot_timeseries_binned():
    data = [
        {
            "expression": "avg:cpu{*}",
            "scope": "*",
            "binned": [{"avg": 1.0}, {"avg": 9.0}],
            "overall_stats": {"avg": 5.0},
        }
    ]
    rows = snapshot_from_mcp_metric_data(data)
    assert rows[0]["scope"] == "*"
    assert rows[0]["latest"] == 9.0


def test_build_metric_results_from_bundle():
    bundle = {
        "responses": [
            {
                "widget_title": "CPU",
                "kind": "metrics",
                "query": "avg:system.cpu.user{*}",
                "data": [{"values": {"avg:system.cpu.user{*}": 7.0}}],
            }
        ]
    }
    results = build_metric_results_from_mcp_bundle(bundle)
    assert len(results) == 1
    assert results[0]["widget_title"] == "CPU"
    assert results[0]["series"][0]["latest"] == 7.0


def test_iter_metric_query_jobs_resolves_team():
    dashboard = {
        "widgets": [
            {
                "definition": {
                    "title": "Score",
                    "type": "query_value",
                    "requests": [{"q": "avg:foo{team:$team}"}],
                }
            }
        ],
        "template_variables": [{"name": "team", "prefix": "team", "default": "*"}],
    }
    from scripts.datadog_dashboard_extract import extract_widget_queries

    extracted = extract_widget_queries(dashboard)
    jobs = iter_metric_query_jobs(
        extracted, dashboard["template_variables"], {"team": "talent-search"}
    )
    assert len(jobs) == 1
    assert "team:talent-search" in jobs[0]["query"]
