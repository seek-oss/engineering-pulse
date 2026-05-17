"""Tests for scripts/todo_report.py."""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import todo_report as tr  # noqa: E402


class TestBuildViewUrl:
    def test_task_id(self):
        assert tr.build_view_url("abc123") == "https://app.todoist.com/app/task/abc123"

    def test_strips_whitespace(self):
        assert tr.build_view_url("  x  ") == "https://app.todoist.com/app/task/x"

    def test_empty(self):
        assert tr.build_view_url("") == ""
        assert tr.build_view_url("   ") == ""


class TestEnrichJsonItems:
    def test_adds_view_url(self):
        items = [{"id": "t1", "title": "A"}]
        out = tr.enrich_json_items(items)
        assert out[0]["view_url"] == "https://app.todoist.com/app/task/t1"
        assert out[0]["title"] == "A"

    def test_does_not_mutate_input(self):
        items = [{"id": "t1"}]
        tr.enrich_json_items(items)
        assert "view_url" not in items[0]


class TestFormatViewActionHtml:
    def test_link(self):
        html = tr.format_view_action_html(
            {"id": "x", "view_url": "https://app.todoist.com/app/task/x"}
        )
        assert 'href="https://app.todoist.com/app/task/x"' in html
        assert ">View</a>" in html

    def test_falls_back_to_id(self):
        html = tr.format_view_action_html({"id": "yz"})
        assert "app.todoist.com/app/task/yz" in html

    def test_empty(self):
        assert "—" in tr.format_view_action_html({})
