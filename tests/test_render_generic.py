"""Tests for the generic dashboard rendering in render_daily_dashboard_html.py."""
import html as html_mod

import pytest

from scripts.render_daily_dashboard_html import _render_generic_section


class TestRenderGenericSection:
    def test_empty_results_shows_no_data(self):
        data = {"results": []}
        html = _render_generic_section("My Dashboard", data)
        assert "No metric data" in html
        assert "My Dashboard" in html

    def test_missing_results_key_shows_no_data(self):
        html = _render_generic_section("Empty", {})
        assert "No metric data" in html

    def test_single_widget_renders_tile(self):
        data = {
            "results": [
                {
                    "widget_title": "Error Rate",
                    "kind": "metrics",
                    "series": [{"scope": "env:prod", "latest": 3.5}],
                }
            ]
        }
        html = _render_generic_section("DORA", data)
        assert "Error Rate" in html
        assert "3.5" in html
        assert "DORA" in html

    def test_null_value_shows_dash(self):
        data = {
            "results": [
                {
                    "widget_title": "Unknown Widget",
                    "kind": "metrics",
                    "series": [{"scope": "*", "latest": None}],
                }
            ]
        }
        html = _render_generic_section("Test", data)
        assert "—" in html
        assert "tile-grey" in html

    def test_empty_series_shows_dash(self):
        data = {
            "results": [
                {
                    "widget_title": "No Data Widget",
                    "kind": "metrics",
                    "series": [],
                }
            ]
        }
        html = _render_generic_section("Test", data)
        assert "—" in html

    def test_multiple_widgets_grouped_by_title(self):
        data = {
            "results": [
                {
                    "widget_title": "CPU",
                    "kind": "metrics_formula_base",
                    "subquery": "query1",
                    "series": [{"scope": "*", "latest": 80.0}],
                },
                {
                    "widget_title": "CPU",
                    "kind": "metrics_formula_base",
                    "subquery": "query2",
                    "series": [{"scope": "*", "latest": 100.0}],
                },
                {
                    "widget_title": "Memory",
                    "kind": "metrics",
                    "series": [{"scope": "*", "latest": 60.0}],
                },
            ]
        }
        html = _render_generic_section("Infra", data)
        # Should show two tiles: CPU (first occurrence) and Memory
        assert "CPU" in html
        assert "Memory" in html
        assert "80.0" in html  # first series value for CPU
        assert "60.0" in html

    def test_label_is_html_escaped(self):
        html = _render_generic_section("<script>alert(1)</script>", {"results": []})
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
