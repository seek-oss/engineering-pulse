"""Tests for scripts/todo.py — pure functions and mocked HTTP."""

import json
from datetime import UTC
from unittest.mock import MagicMock, patch

from scripts.todo import (
    PRIORITY_MAP,
    PRIORITY_REVERSE,
    _age_days,
    _extract_url,
    _task_created,
    build_parser,
)

# ---------------------------------------------------------------------------
# _age_days
# ---------------------------------------------------------------------------


class TestAgeDays:
    def test_today(self):
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        assert _age_days(now) == 0

    def test_z_suffix(self):
        assert isinstance(_age_days("2020-01-01T00:00:00Z"), int)
        assert _age_days("2020-01-01T00:00:00Z") > 1000


# ---------------------------------------------------------------------------
# _task_created
# ---------------------------------------------------------------------------


class TestTaskCreated:
    def test_v1_added_at(self):
        task = {"added_at": "2026-03-20T10:00:00Z", "content": "x"}
        assert _task_created(task) == "2026-03-20T10:00:00Z"

    def test_v2_created_at_fallback(self):
        task = {"created_at": "2026-03-20T10:00:00Z", "content": "x"}
        assert _task_created(task) == "2026-03-20T10:00:00Z"

    def test_neither(self):
        assert _task_created({"content": "x"}) == ""


# ---------------------------------------------------------------------------
# _extract_url
# ---------------------------------------------------------------------------


class TestExtractUrl:
    def test_markdown_link(self):
        desc = "[Exploring Gen AI](https://martinfowler.com/articles/exploring-gen-ai.html)"
        assert _extract_url(desc) == "https://martinfowler.com/articles/exploring-gen-ai.html"

    def test_raw_url(self):
        assert _extract_url("https://example.com/page") == "https://example.com/page"

    def test_plain_text(self):
        assert _extract_url("just some text") == "just some text"

    def test_empty(self):
        assert _extract_url("") == ""


# ---------------------------------------------------------------------------
# Priority maps
# ---------------------------------------------------------------------------


class TestPriorityMaps:
    def test_map_values(self):
        assert PRIORITY_MAP["high"] == 4
        assert PRIORITY_MAP["medium"] == 3
        assert PRIORITY_MAP["low"] == 2
        assert PRIORITY_MAP["none"] == 1

    def test_reverse_roundtrip(self):
        for name, num in PRIORITY_MAP.items():
            assert PRIORITY_REVERSE[num] == name


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


class TestParser:
    def test_setup(self):
        parser = build_parser()
        args = parser.parse_args(["setup"])
        assert args.command == "setup"

    def test_setup_with_name(self):
        parser = build_parser()
        args = parser.parse_args(["setup", "--name", "My Project"])
        assert args.name == "My Project"

    def test_add_task(self):
        parser = build_parser()
        args = parser.parse_args(["add", "Test task", "--priority", "high"])
        assert args.title == "Test task"
        assert args.priority == "high"
        assert args.type == "task"

    def test_add_read(self):
        parser = build_parser()
        args = parser.parse_args(["add", "Article", "--type", "read", "--url", "https://x.com"])
        assert args.type == "read"
        assert args.url == "https://x.com"

    def test_add_domain_personal(self):
        parser = build_parser()
        args = parser.parse_args(["add", "Dentist", "--domain", "personal"])
        assert args.domain == "personal"

    def test_add_domain_defaults_work(self):
        parser = build_parser()
        args = parser.parse_args(["add", "Work thing"])
        assert args.domain == "work"

    def test_list_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["list"])
        assert args.type is None
        assert args.json is False

    def test_list_json(self):
        parser = build_parser()
        args = parser.parse_args(["list", "--json", "--type", "task"])
        assert args.json is True
        assert args.type == "task"

    def test_done(self):
        parser = build_parser()
        args = parser.parse_args(["done", "abc123", "--comment", "Looks good"])
        assert args.task_id == "abc123"
        assert args.comment == "Looks good"

    def test_cancel(self):
        parser = build_parser()
        args = parser.parse_args(["cancel", "abc123", "--comment", "Not needed"])
        assert args.task_id == "abc123"
        assert args.comment == "Not needed"


# ---------------------------------------------------------------------------
# Mocked HTTP tests for commands
# ---------------------------------------------------------------------------

MOCK_PROJECT = {"id": "proj-123", "name": "Engineering Pulse"}
MOCK_SECTIONS = [
    {"id": "sec-tasks", "name": "Tasks"},
    {"id": "sec-read", "name": "Reading Queue"},
]
MOCK_TASK = {
    "id": "task-001",
    "content": "Test task",
    "project_id": "proj-123",
    "section_id": "sec-tasks",
    "priority": 4,
    "description": "",
    "labels": [],
    "added_at": "2026-03-20T10:00:00Z",
}


def _mock_get(url, **kwargs):
    """Route mocked GET requests based on URL path."""
    resp = MagicMock()
    resp.status_code = 200

    if "/projects" in url:
        resp.json.return_value = {"results": [MOCK_PROJECT], "next_cursor": None}
    elif "/sections" in url:
        resp.json.return_value = {"results": MOCK_SECTIONS, "next_cursor": None}
    elif "/tasks/" in url and "/close" not in url:
        resp.json.return_value = MOCK_TASK
    elif "/tasks" in url:
        resp.json.return_value = {"results": [MOCK_TASK], "next_cursor": None}
    else:
        resp.json.return_value = {}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_post(url, **kwargs):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = "{}"

    if "/projects" in url:
        resp.json.return_value = MOCK_PROJECT
    elif "/sections" in url:
        resp.json.return_value = {"id": "sec-new", "name": "new"}
    elif "/comments" in url:
        resp.json.return_value = {"id": "comment-1"}
    elif "/close" in url:
        resp.status_code = 204
        resp.text = ""
        resp.json.return_value = {}
    elif "/tasks" in url:
        resp.json.return_value = MOCK_TASK
    else:
        resp.json.return_value = {}
    resp.raise_for_status = MagicMock()
    return resp


class TestCmdAdd:
    @patch("scripts.todo.requests.post", side_effect=_mock_post)
    @patch("scripts.todo.requests.get", side_effect=_mock_get)
    @patch.dict("os.environ", {"TODOIST_API_TOKEN": "test", "TODOIST_PROJECT_ID": "proj-123"})
    def test_add_task(self, mock_get, mock_post, capsys):
        from scripts.todo import cmd_add

        parser = build_parser()
        args = parser.parse_args(["add", "Hello world", "--priority", "high"])
        cmd_add(args)
        out = capsys.readouterr().out
        assert "Added task" in out

    @patch("scripts.todo.requests.post", side_effect=_mock_post)
    @patch("scripts.todo.requests.get", side_effect=_mock_get)
    @patch.dict("os.environ", {"TODOIST_API_TOKEN": "test", "TODOIST_PROJECT_ID": "proj-123"})
    def test_add_read(self, mock_get, mock_post, capsys):
        from scripts.todo import cmd_add

        parser = build_parser()
        args = parser.parse_args(["add", "Article", "--type", "read", "--url", "https://x.com"])
        cmd_add(args)
        out = capsys.readouterr().out
        assert "Added read" in out


class TestCmdList:
    @patch("scripts.todo.requests.get", side_effect=_mock_get)
    @patch.dict("os.environ", {"TODOIST_API_TOKEN": "test", "TODOIST_PROJECT_ID": "proj-123"})
    def test_list_json(self, mock_get, capsys):
        from scripts.todo import cmd_list

        parser = build_parser()
        args = parser.parse_args(["list", "--json"])
        cmd_list(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) == 1
        assert data[0]["id"] == "task-001"
        assert data[0]["type"] == "task"
        assert data[0]["view_url"] == "https://app.todoist.com/app/task/task-001"
        assert "done_url" not in data[0]
        assert data[0]["domain"] == "work"

    @patch("scripts.todo.requests.get", side_effect=_mock_get)
    @patch.dict("os.environ", {"TODOIST_API_TOKEN": "test", "TODOIST_PROJECT_ID": "proj-123"})
    def test_list_table(self, mock_get, capsys):
        from scripts.todo import cmd_list

        parser = build_parser()
        args = parser.parse_args(["list"])
        cmd_list(args)
        out = capsys.readouterr().out
        assert "1 item(s)" in out


class TestCmdDone:
    @patch("scripts.todo.requests.post", side_effect=_mock_post)
    @patch("scripts.todo.requests.get", side_effect=_mock_get)
    @patch.dict("os.environ", {"TODOIST_API_TOKEN": "test"})
    def test_done_with_comment(self, mock_get, mock_post, capsys):
        from scripts.todo import cmd_done

        parser = build_parser()
        args = parser.parse_args(["done", "task-001", "--comment", "All good"])
        cmd_done(args)
        out = capsys.readouterr().out
        assert "Marked done" in out


class TestCmdCancel:
    @patch("scripts.todo.requests.post", side_effect=_mock_post)
    @patch("scripts.todo.requests.get", side_effect=_mock_get)
    @patch.dict("os.environ", {"TODOIST_API_TOKEN": "test"})
    def test_cancel_with_comment(self, mock_get, mock_post, capsys):
        from scripts.todo import cmd_cancel

        parser = build_parser()
        args = parser.parse_args(["cancel", "task-001", "--comment", "Not needed"])
        cmd_cancel(args)
        out = capsys.readouterr().out
        assert "Cancelled" in out


class TestCmdSetup:
    @patch("scripts.todo.requests.post", side_effect=_mock_post)
    @patch("scripts.todo.requests.get", side_effect=_mock_get)
    @patch.dict("os.environ", {"TODOIST_API_TOKEN": "test"})
    def test_setup_writes_env(self, mock_get, mock_post, capsys, tmp_path):
        from scripts.todo import cmd_setup

        env_file = tmp_path / ".env"
        env_file.write_text("TODOIST_API_TOKEN=test\n")

        parser = build_parser()
        args = parser.parse_args(["setup"])

        with patch("scripts.todo._env_path", return_value=env_file):
            cmd_setup(args)

        out = capsys.readouterr().out
        assert "reusing" in out or "Created" in out
        assert "TODOIST_PROJECT_ID=proj-123" in env_file.read_text()
