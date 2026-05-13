"""Tests for the dashboards plugin (file-driven dashboard discovery + parsing)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dashboards_plugin import (
    Dashboard,
    discover_dashboards,
    load_snapshot,
    parse_dashboard,
)


# ── discover_dashboards ────────────────────────────────────────────────────


class TestDiscoverDashboards:
    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        assert discover_dashboards(tmp_path / "missing") == []

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert discover_dashboards(tmp_path) == []

    def test_discovers_md_files(self, tmp_path: Path) -> None:
        (tmp_path / "alpha.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "beta.md").write_text("# B\n", encoding="utf-8")
        names = [p.name for p in discover_dashboards(tmp_path)]
        assert names == ["alpha.md", "beta.md"]

    def test_skips_underscore_templates(self, tmp_path: Path) -> None:
        (tmp_path / "real.md").write_text("# real\n", encoding="utf-8")
        (tmp_path / "_example.md").write_text("# ex\n", encoding="utf-8")
        (tmp_path / "_template.md").write_text("# tpl\n", encoding="utf-8")
        names = [p.name for p in discover_dashboards(tmp_path)]
        assert names == ["real.md"]

    def test_ignores_non_md_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "b.txt").write_text("ignored", encoding="utf-8")
        (tmp_path / "c.json").write_text("{}", encoding="utf-8")
        names = [p.name for p in discover_dashboards(tmp_path)]
        assert names == ["a.md"]

    def test_returns_sorted_by_filename(self, tmp_path: Path) -> None:
        (tmp_path / "zebra.md").write_text("# z\n", encoding="utf-8")
        (tmp_path / "alpha.md").write_text("# a\n", encoding="utf-8")
        (tmp_path / "mango.md").write_text("# m\n", encoding="utf-8")
        names = [p.name for p in discover_dashboards(tmp_path)]
        assert names == ["alpha.md", "mango.md", "zebra.md"]


# ── parse_dashboard ────────────────────────────────────────────────────────


class TestParseDashboard:
    def test_extracts_all_fields(self, tmp_path: Path) -> None:
        f = tmp_path / "dora.md"
        f.write_text(
            "# DORA Metrics\n"
            "\n"
            "- **URL:** `https://app.datadoghq.com/dashboard/abc-123/dora`\n"
            "- **Slug:** `dora`\n"
            "- **Focus:** `Deployment Frequency, Change Failure Rate`\n",
            encoding="utf-8",
        )
        d = parse_dashboard(f)
        assert d.title == "DORA Metrics"
        assert d.slug == "dora"
        assert d.url == "https://app.datadoghq.com/dashboard/abc-123/dora"
        assert d.source == f

    def test_missing_title_falls_back_to_filename(self, tmp_path: Path) -> None:
        f = tmp_path / "my-dashboard.md"
        f.write_text("- **Slug:** `my-dashboard`\n", encoding="utf-8")
        d = parse_dashboard(f)
        assert d.title == "my-dashboard"

    def test_missing_slug_falls_back_to_filename_stem(self, tmp_path: Path) -> None:
        f = tmp_path / "perf-dashboard.md"
        f.write_text("# Perf\n", encoding="utf-8")
        d = parse_dashboard(f)
        assert d.slug == "perf-dashboard"

    def test_missing_url_defaults_to_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text("# X\n", encoding="utf-8")
        assert parse_dashboard(f).url == ""

    def test_keys_are_case_insensitive(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text(
            "# X\n"
            "- **url:** `https://example.com`\n"
            "- **SLUG:** `x`\n",
            encoding="utf-8",
        )
        d = parse_dashboard(f)
        assert d.url == "https://example.com"
        assert d.slug == "x"

    def test_value_unwrapping_strips_quotes_and_backticks(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text(
            "# X\n"
            "- **URL:** `https://example.com`\n"
            "- **Slug:** \"my-slug\"\n",
            encoding="utf-8",
        )
        d = parse_dashboard(f)
        assert d.url == "https://example.com"
        assert d.slug == "my-slug"

    def test_value_with_no_decoration(self, tmp_path: Path) -> None:
        f = tmp_path / "x.md"
        f.write_text(
            "# X\n- **URL:** https://plain.example.com\n- **Slug:** plain\n",
            encoding="utf-8",
        )
        d = parse_dashboard(f)
        assert d.url == "https://plain.example.com"
        assert d.slug == "plain"


# ── load_snapshot ──────────────────────────────────────────────────────────


class TestLoadSnapshot:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert load_snapshot("nonexistent", tmp_path) is None

    def test_existing_file_returns_parsed_json(self, tmp_path: Path) -> None:
        payload = {
            "dashboard_title": "T",
            "source_url": "https://example.com",
            "results": [{"widget_title": "x", "series": []}],
        }
        (tmp_path / "foo_metric_results.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        out = load_snapshot("foo", tmp_path)
        assert out == payload

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "bad_metric_results.json").write_text("not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_snapshot("bad", tmp_path)
