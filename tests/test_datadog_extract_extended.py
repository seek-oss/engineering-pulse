"""Extended tests for datadog_dashboard_extract.py — covers HTTP helpers,
display functions, and the main() orchestration flow (fully mocked).
"""
import io
import sys
from unittest.mock import MagicMock, patch, call

import pytest
import requests as req_lib

from scripts.datadog_dashboard_extract import (
    _headers,
    get_dashboard,
    query_metrics_v1,
    query_logs_aggregate,
    print_extraction_summary,
    print_extracted_requests,
)


# ---------------------------------------------------------------------------
# _headers
# ---------------------------------------------------------------------------

class TestHeaders:
    def test_returns_required_keys(self):
        h = _headers()
        assert "DD-API-KEY" in h
        assert "DD-APPLICATION-KEY" in h
        assert "Accept" in h
        assert "Content-Type" in h

    def test_accept_is_json(self):
        assert _headers()["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# get_dashboard (mocked HTTP)
# ---------------------------------------------------------------------------

class TestGetDashboard:
    @patch("scripts.datadog_dashboard_extract.requests.get")
    def test_returns_parsed_json(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "abc-123", "title": "My Dashboard"}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = get_dashboard("abc-123")
        assert result["id"] == "abc-123"
        assert result["title"] == "My Dashboard"

    @patch("scripts.datadog_dashboard_extract.requests.get")
    def test_raises_on_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError("403 Forbidden")
        mock_get.return_value = mock_resp

        with pytest.raises(req_lib.HTTPError):
            get_dashboard("bad-id")

    @patch("scripts.datadog_dashboard_extract.requests.get")
    def test_calls_correct_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        get_dashboard("xyz-789")
        call_url = mock_get.call_args[0][0]
        assert "xyz-789" in call_url


# ---------------------------------------------------------------------------
# query_metrics_v1 (mocked HTTP)
# ---------------------------------------------------------------------------

class TestQueryMetricsV1:
    @patch("scripts.datadog_dashboard_extract.requests.get")
    def test_returns_parsed_json(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"series": [{"pointlist": [[1000, 5.0]]}]}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        result = query_metrics_v1("avg:cpu{*}", 1000, 2000)
        assert "series" in result

    @patch("scripts.datadog_dashboard_extract.requests.get")
    def test_passes_query_params(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        query_metrics_v1("sum:requests{*}", 1000, 2000)
        kwargs = mock_get.call_args[1]
        params = kwargs.get("params", {})
        assert params["query"] == "sum:requests{*}"
        assert params["from"] == 1000
        assert params["to"] == 2000

    @patch("scripts.datadog_dashboard_extract.requests.get")
    def test_raises_on_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError("429 Rate Limited")
        mock_get.return_value = mock_resp

        with pytest.raises(req_lib.HTTPError):
            query_metrics_v1("avg:cpu{*}", 1000, 2000)


# ---------------------------------------------------------------------------
# query_logs_aggregate (mocked HTTP)
# ---------------------------------------------------------------------------

class TestQueryLogsAggregate:
    @patch("scripts.datadog_dashboard_extract.requests.post")
    def test_returns_parsed_json(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"buckets": []}}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = query_logs_aggregate("error", "2024-01-01", "2024-01-02")
        assert "data" in result

    @patch("scripts.datadog_dashboard_extract.requests.post")
    def test_includes_group_by_when_facet_provided(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        query_logs_aggregate("error", "2024-01-01", "2024-01-02", group_by_facet="service")
        payload = mock_post.call_args[1]["json"]
        assert "group_by" in payload
        assert payload["group_by"][0]["facet"] == "service"

    @patch("scripts.datadog_dashboard_extract.requests.post")
    def test_no_group_by_when_facet_is_none(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        query_logs_aggregate("error", "2024-01-01", "2024-01-02")
        payload = mock_post.call_args[1]["json"]
        assert "group_by" not in payload

    @patch("scripts.datadog_dashboard_extract.requests.post")
    def test_timeseries_includes_interval_and_type(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        query_logs_aggregate("error", "2024-01-01", "2024-01-02", interval="1h")
        payload = mock_post.call_args[1]["json"]
        compute = payload["compute"][0]
        assert compute["interval"] == "1h"
        assert compute["type"] == "timeseries"


# ---------------------------------------------------------------------------
# Display functions — just verify they run without raising
# ---------------------------------------------------------------------------

class TestDisplayFunctions:
    def test_print_extraction_summary_empty(self):
        print_extraction_summary([])  # should not raise

    def test_print_extraction_summary_with_items(self):
        items = [
            {"source": "metrics"},
            {"source": "metrics"},
            {"source": "logs"},
            {"source": "unknown"},
        ]
        print_extraction_summary(items)  # should not raise

    def test_print_extracted_requests_empty(self):
        print_extracted_requests([])  # should not raise

    def test_print_extracted_requests_with_items(self):
        items = [
            {
                "widget_index": 0,
                "request_index": 0,
                "title": "CPU Usage",
                "widget_type": "query_value",
                "source": "metrics",
                "request": {"q": "avg:cpu{*}"},
            }
        ]
        print_extracted_requests(items)  # should not raise


# ---------------------------------------------------------------------------
# main() — argument parsing and env-var guard
# ---------------------------------------------------------------------------

class TestMain:
    @patch("scripts.datadog_dashboard_extract.get_dashboard")
    @patch("scripts.datadog_dashboard_extract.requests.get")
    def test_main_exits_when_url_env_not_set(self, mock_get, mock_dash):
        with patch.dict("os.environ", {}, clear=False):
            import os
            # Remove any dashboard URL env var
            for key in list(os.environ.keys()):
                if "DATADOG_DASHBOARD_URL" in key:
                    del os.environ[key]
            with patch.object(sys, "argv", ["dd_extract.py", "--url-env", "MISSING_ENV_VAR"]):
                with pytest.raises(SystemExit):
                    from importlib import reload
                    import scripts.datadog_dashboard_extract as mod
                    mod.main()

    @patch("scripts.datadog_dashboard_extract.get_dashboard")
    @patch("scripts.datadog_dashboard_extract.requests.get")
    @patch("scripts.datadog_dashboard_extract.requests.post")
    def test_main_runs_with_valid_env(self, mock_post, mock_http_get, mock_dash):
        """Smoke-test main() with a minimal mocked dashboard."""
        fake_dashboard = {
            "title": "Test Dashboard",
            "template_variables": [],
            "widgets": [
                {
                    "definition": {
                        "type": "query_value",
                        "title": "CPU",
                        "requests": [{"queries": [{"data_source": "metrics", "query": "avg:cpu{*}"}]}],
                    }
                }
            ],
        }
        mock_dash.return_value = fake_dashboard

        # Mock metric query response
        mock_metric_resp = MagicMock()
        mock_metric_resp.json.return_value = {
            "series": [{"scope": "team:eng", "pointlist": [[1000000, 5.0]]}]
        }
        mock_metric_resp.raise_for_status.return_value = None
        mock_http_get.return_value = mock_metric_resp

        test_env = {
            "DD_API_KEY": "test-key",
            "DD_APP_KEY": "test-app-key",
            "MY_TEST_DASH_URL": "https://app.datadoghq.com/dashboard/abc-123?from_ts=1000000000000&to_ts=1001000000000",
        }
        with patch.dict("os.environ", test_env):
            with patch.object(sys, "argv", ["dd_extract.py", "--url-env", "MY_TEST_DASH_URL", "--days", "2"]):
                with patch("builtins.open", MagicMock()):
                    from scripts.datadog_dashboard_extract import main
                    main()  # should not raise

    @patch("scripts.datadog_dashboard_extract.get_dashboard")
    @patch("scripts.datadog_dashboard_extract.requests.get")
    @patch("scripts.datadog_dashboard_extract.requests.post")
    def test_main_output_slug_changes_filenames(self, mock_post, mock_http_get, mock_dash):
        """When --output-slug is provided, output files use the slug prefix."""
        fake_dashboard = {
            "title": "DORA Dashboard",
            "template_variables": [],
            "widgets": [],
        }
        mock_dash.return_value = fake_dashboard

        test_env = {
            "DD_API_KEY": "test-key",
            "DD_APP_KEY": "test-app-key",
            "MY_DORA_URL": "https://app.datadoghq.com/dashboard/xyz-789?from_ts=1000000000000&to_ts=1001000000000",
        }
        opened_files = []
        real_open = open

        def tracking_open(path, *a, **kw):
            opened_files.append(str(path))
            return MagicMock()

        with patch.dict("os.environ", test_env):
            with patch.object(
                sys, "argv",
                ["dd_extract.py", "--url-env", "MY_DORA_URL", "--days", "1", "--output-slug", "dora"],
            ):
                with patch("builtins.open", tracking_open):
                    from scripts.datadog_dashboard_extract import main
                    main()

        filenames = [f.split("/")[-1] for f in opened_files]
        assert "dora_dashboard.json" in filenames
        assert "dora_dashboard_extracted_queries.json" in filenames
        assert "dora_metric_results.json" in filenames

    @patch("scripts.datadog_dashboard_extract.get_dashboard")
    @patch("scripts.datadog_dashboard_extract.requests.get")
    @patch("scripts.datadog_dashboard_extract.requests.post")
    def test_main_no_slug_uses_default_filenames(self, mock_post, mock_http_get, mock_dash):
        """Without --output-slug, output files have no prefix (backward compat)."""
        fake_dashboard = {
            "title": "Test Dashboard",
            "template_variables": [],
            "widgets": [],
        }
        mock_dash.return_value = fake_dashboard

        test_env = {
            "DD_API_KEY": "test-key",
            "DD_APP_KEY": "test-app-key",
            "MY_TEST_URL": "https://app.datadoghq.com/dashboard/abc-123?from_ts=1000000000000&to_ts=1001000000000",
        }
        opened_files = []

        def tracking_open(path, *a, **kw):
            opened_files.append(str(path))
            return MagicMock()

        with patch.dict("os.environ", test_env):
            with patch.object(sys, "argv", ["dd_extract.py", "--url-env", "MY_TEST_URL", "--days", "1"]):
                with patch("builtins.open", tracking_open):
                    from scripts.datadog_dashboard_extract import main
                    main()

        filenames = [f.split("/")[-1] for f in opened_files]
        assert "dashboard.json" in filenames
        assert "dashboard_extracted_queries.json" in filenames
        assert "metric_results.json" in filenames
