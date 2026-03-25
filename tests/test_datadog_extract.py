"""Tests for scripts/datadog_dashboard_extract.py — pure functions only.
HTTP-calling functions (get_dashboard, query_metrics_v1, etc.) are mocked
so no real network traffic is made.
"""
import time
from unittest.mock import MagicMock, patch

import pytest

from scripts.datadog_dashboard_extract import (
    _apply_teams_to_url,
    _extract_time_window,
    _source_style,
    _teams_to_query_value,
    detect_query_source,
    extract_dashboard_id,
    extract_widget_queries,
    flatten_widgets,
    resolve_template_variables,
)


# ---------------------------------------------------------------------------
# extract_dashboard_id
# ---------------------------------------------------------------------------

class TestExtractDashboardId:
    def test_standard_url(self):
        url = "https://app.datadoghq.com/dashboard/abc-123-xyz/my-dashboard"
        assert extract_dashboard_id(url) == "abc-123-xyz"

    def test_url_with_query_params(self):
        url = "https://app.example.com/dashboard/***REMOVED***?from_ts=123&to_ts=456"
        assert extract_dashboard_id(url) == "***REMOVED***"

    def test_url_without_dashboard_raises(self):
        with pytest.raises(ValueError, match="Could not extract dashboard ID"):
            extract_dashboard_id("https://app.datadoghq.com/infrastructure")

    def test_url_empty_string_raises(self):
        with pytest.raises(ValueError):
            extract_dashboard_id("")

    def test_url_with_trailing_slug(self):
        url = "https://app.datadoghq.com/dashboard/***REMOVED***/owner-engineering-metrics"
        assert extract_dashboard_id(url) == "***REMOVED***"


# ---------------------------------------------------------------------------
# flatten_widgets
# ---------------------------------------------------------------------------

class TestFlattenWidgets:
    def test_empty_list(self):
        assert flatten_widgets([]) == []

    def test_flat_widgets_no_nesting(self):
        widgets = [{"definition": {"type": "note"}}, {"definition": {"type": "query_value"}}]
        result = flatten_widgets(widgets)
        assert len(result) == 2

    def test_nested_group_widget(self):
        inner = {"definition": {"type": "query_value"}}
        outer = {"definition": {"type": "group", "widgets": [inner]}}
        result = flatten_widgets([outer])
        # Should contain the group widget AND the inner widget
        assert len(result) == 2
        assert result[0] is outer
        assert result[1] is inner

    def test_deeply_nested_widgets(self):
        deepest = {"definition": {"type": "metric"}}
        middle = {"definition": {"type": "group", "widgets": [deepest]}}
        top = {"definition": {"type": "group", "widgets": [middle]}}
        result = flatten_widgets([top])
        assert len(result) == 3

    def test_widget_without_definition(self):
        widgets = [{"id": 1}, {"definition": {}}]
        result = flatten_widgets(widgets)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# detect_query_source
# ---------------------------------------------------------------------------

class TestDetectQuerySource:
    def test_metrics_via_q_field(self):
        assert detect_query_source({"q": "avg:system.cpu.user{*}"}) == "metrics"
        assert detect_query_source({"q": "sum:requests.count{*}"}) == "metrics"
        assert detect_query_source({"q": "max:disk.usage{host:foo}"}) == "metrics"
        assert detect_query_source({"q": "p99:latency{*}"}) == "metrics"

    def test_unknown_q_for_non_metric_formula(self):
        assert detect_query_source({"q": "some random thing"}) == "unknown_q"

    def test_metrics_formula_from_queries(self):
        req = {"queries": [{"data_source": "metrics", "query": "avg:cpu{*}"}]}
        assert detect_query_source(req) == "metrics_formula"

    def test_logs_from_queries(self):
        req = {"queries": [{"data_source": "logs"}]}
        assert detect_query_source(req) == "logs"

    def test_apm_from_queries(self):
        req = {"queries": [{"data_source": "apm_resource_stats"}]}
        assert detect_query_source(req) == "apm"

    def test_traces_from_queries(self):
        req = {"queries": [{"data_source": "traces"}]}
        assert detect_query_source(req) == "apm"

    def test_rum_from_queries(self):
        req = {"queries": [{"data_source": "rum"}]}
        assert detect_query_source(req) == "rum"

    def test_process_from_queries(self):
        req = {"queries": [{"data_source": "process"}]}
        assert detect_query_source(req) == "process"

    def test_formula_or_other_unknown_source(self):
        req = {"queries": [{"data_source": "slo"}]}
        assert detect_query_source(req) == "formula_or_other"

    def test_log_query_field(self):
        assert detect_query_source({"log_query": {"index": "main"}}) == "logs"

    def test_empty_request_is_unknown(self):
        assert detect_query_source({}) == "unknown"

    def test_empty_queries_list(self):
        assert detect_query_source({"queries": []}) == "unknown"


# ---------------------------------------------------------------------------
# resolve_template_variables
# ---------------------------------------------------------------------------

class TestResolveTemplateVariables:
    def test_basic_substitution(self):
        tvs = [{"name": "team", "prefix": "team", "default": "my-team"}]
        result = resolve_template_variables("avg:cpu{$team}", tvs)
        assert result == "avg:cpu{team:my-team}"

    def test_override_takes_precedence(self):
        tvs = [{"name": "team", "prefix": "team", "default": "original"}]
        result = resolve_template_variables("avg:cpu{$team}", tvs, overrides={"team": "override-team"})
        assert result == "avg:cpu{team:override-team}"

    def test_wildcard_default_when_empty(self):
        tvs = [{"name": "team", "prefix": "team", "default": ""}]
        result = resolve_template_variables("avg:cpu{$team}", tvs)
        assert result == "avg:cpu{team:*}"

    def test_list_default_uses_first_element(self):
        tvs = [{"name": "env", "prefix": "env", "defaults": ["prod", "staging"]}]
        result = resolve_template_variables("avg:cpu{$env}", tvs)
        assert result == "avg:cpu{env:prod}"

    def test_empty_defaults_list_falls_back_to_wildcard(self):
        tvs = [{"name": "env", "prefix": "env", "defaults": []}]
        result = resolve_template_variables("avg:cpu{$env}", tvs)
        assert result == "avg:cpu{env:*}"

    def test_no_prefix_uses_value_directly(self):
        tvs = [{"name": "region", "prefix": "", "default": "us-east-1"}]
        result = resolve_template_variables("sum:requests{$region}", tvs)
        assert result == "sum:requests{us-east-1}"

    def test_multiple_variables(self):
        tvs = [
            {"name": "team", "prefix": "team", "default": "eng"},
            {"name": "env",  "prefix": "env",  "default": "prod"},
        ]
        result = resolve_template_variables("avg:cpu{$team,$env}", tvs)
        assert result == "avg:cpu{team:eng,env:prod}"

    def test_no_template_variables(self):
        result = resolve_template_variables("avg:cpu{host:web}", [])
        assert result == "avg:cpu{host:web}"

    def test_none_overrides_treated_as_empty_dict(self):
        tvs = [{"name": "team", "prefix": "team", "default": "eng"}]
        result = resolve_template_variables("avg:cpu{$team}", tvs, overrides=None)
        assert result == "avg:cpu{team:eng}"


# ---------------------------------------------------------------------------
# _teams_to_query_value
# ---------------------------------------------------------------------------

class TestTeamsToQueryValue:
    def test_empty_string_returns_wildcard(self):
        assert _teams_to_query_value("") == "*"

    def test_whitespace_only_returns_wildcard(self):
        assert _teams_to_query_value("  ,  ") == "*"

    def test_single_team(self):
        assert _teams_to_query_value("team-a") == "team-a"

    def test_single_team_with_spaces(self):
        assert _teams_to_query_value("  team-a  ") == "team-a"

    def test_two_teams(self):
        result = _teams_to_query_value("team-a,team-b")
        assert result == "(team-a OR team-b)"

    def test_three_teams(self):
        result = _teams_to_query_value("team-a,team-b,team-c")
        assert result == "(team-a OR team-b OR team-c)"

    def test_teams_with_extra_spaces(self):
        result = _teams_to_query_value(" team-a , team-b ")
        assert result == "(team-a OR team-b)"


# ---------------------------------------------------------------------------
# _extract_time_window
# ---------------------------------------------------------------------------

class TestExtractTimeWindow:
    def test_returns_none_when_no_timestamps(self):
        assert _extract_time_window("https://app.datadoghq.com/dashboard/abc") is None

    def test_extracts_from_and_to_in_seconds(self):
        url = "https://app.datadoghq.com/dashboard/abc?from_ts=1700000000000&to_ts=1700086400000"
        result = _extract_time_window(url)
        assert result is not None
        from_sec, to_sec = result
        assert from_sec == 1700000000
        assert to_sec == 1700086400

    def test_live_true_snaps_to_sec_to_now(self):
        before = int(time.time())
        url = "https://app.datadoghq.com/dashboard/abc?from_ts=1700000000000&to_ts=9999999999999&live=true"
        result = _extract_time_window(url)
        after = int(time.time())
        assert result is not None
        _, to_sec = result
        assert before <= to_sec <= after

    def test_live_false_uses_url_to_ts(self):
        url = "https://app.datadoghq.com/dashboard/abc?from_ts=1700000000000&to_ts=1700086400000&live=false"
        result = _extract_time_window(url)
        assert result is not None
        assert result[1] == 1700086400

    def test_missing_from_ts_returns_none(self):
        url = "https://app.datadoghq.com/dashboard/abc?to_ts=1700086400000"
        assert _extract_time_window(url) is None

    def test_missing_to_ts_returns_none(self):
        url = "https://app.datadoghq.com/dashboard/abc?from_ts=1700000000000"
        assert _extract_time_window(url) is None


# ---------------------------------------------------------------------------
# _apply_teams_to_url
# ---------------------------------------------------------------------------

class TestApplyTeamsToUrl:
    def test_replaces_existing_team_params(self):
        url = "https://app.datadoghq.com/dashboard/abc?tpl_var_team[0]=old-team&tpl_var_team[1]=other"
        result = _apply_teams_to_url(url, "new-team")
        assert "new-team" in result
        assert "old-team" not in result
        assert "other" not in result

    def test_adds_team_params_when_none_exist(self):
        url = "https://app.datadoghq.com/dashboard/abc?from_ts=1000"
        result = _apply_teams_to_url(url, "my-team")
        assert "my-team" in result
        assert "from_ts=1000" in result

    def test_multiple_teams_creates_indexed_params(self):
        url = "https://app.datadoghq.com/dashboard/abc"
        result = _apply_teams_to_url(url, "team-a,team-b")
        assert "team-a" in result
        assert "team-b" in result

    def test_preserves_non_team_params(self):
        url = "https://app.datadoghq.com/dashboard/abc?from_ts=111&tpl_var_team[0]=old"
        result = _apply_teams_to_url(url, "new-team")
        assert "from_ts=111" in result
        assert "new-team" in result


# ---------------------------------------------------------------------------
# _source_style
# ---------------------------------------------------------------------------

class TestSourceStyle:
    def test_known_sources_return_colour(self):
        assert _source_style("metrics") == "green"
        assert _source_style("metrics_formula") == "green"
        assert _source_style("logs") == "yellow"
        assert _source_style("apm") == "yellow"
        assert _source_style("rum") == "cyan"
        assert _source_style("process") == "cyan"

    def test_unknown_source_returns_red(self):
        assert _source_style("unknown") == "red"
        assert _source_style("something_else") == "red"


# ---------------------------------------------------------------------------
# extract_widget_queries
# ---------------------------------------------------------------------------

class TestExtractWidgetQueries:
    def test_extracts_requests_from_widgets(self):
        dashboard = {
            "widgets": [
                {
                    "definition": {
                        "type": "query_value",
                        "title": "CPU Usage",
                        "requests": [{"q": "avg:system.cpu.user{*}"}],
                    }
                }
            ]
        }
        result = extract_widget_queries(dashboard)
        assert len(result) == 1
        assert result[0]["title"] == "CPU Usage"
        assert result[0]["source"] == "metrics"
        assert result[0]["widget_index"] == 0

    def test_empty_dashboard_returns_empty_list(self):
        assert extract_widget_queries({"widgets": []}) == []
        assert extract_widget_queries({}) == []

    def test_widget_without_requests_is_skipped(self):
        dashboard = {"widgets": [{"definition": {"type": "note", "title": "Note"}}]}
        assert extract_widget_queries(dashboard) == []
