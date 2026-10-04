"""Tests for scripts/run_issues.py — the problems list behind the report's red box."""

import json
import subprocess
import time
from unittest.mock import patch

import pytest
from scripts import run_issues
from scripts.run_issues import (
    NEEDS_AUTH,
    READY,
    add,
    issues_path,
    load,
    needed_sources,
    parse_mcp_list,
    preflight,
    preflight_issues,
    reset,
    start,
)

CURSOR_LIST = """Atlassian: ready
Backstage: requires_authentication
GitHub: requires_authentication
Glean: ready
Datadog: error
"""

CLAUDE_LIST = """Checking MCP server health…

acme-jira: https://mcp.example.com/jira (HTTP) - ✓ Connected
acme-github-mcp: https://mcp.example.com/github (HTTP) - ! Needs authentication
datadog: npx -y @example/datadog-mcp - ✗ Failed to connect
"""

ENV_MIN = {"STAKEHOLDERS": ""}


class TestStore:
    def test_add_then_load(self):
        reset("pulse")
        add("pulse", "github", "GitHub search failed")
        assert load("pulse") == [
            {"source": "github", "message": "GitHub search failed", "fix": None}
        ]

    def test_reset_clears(self):
        add("pulse", "github", "x")
        reset("pulse")
        assert load("pulse") == []

    def test_add_without_reset_starts_a_run(self):
        add("sprint", "atlassian", "Jira down")
        assert len(load("sprint")) == 1

    def test_types_are_separate(self):
        add("pulse", "github", "x")
        assert load("sprint") == []

    def test_duplicate_add_is_kept_once(self):
        add("pulse", "github", "same")
        add("pulse", "github", "same")
        assert len(load("pulse")) == 1

    def test_one_row_per_source_keeps_first_wording(self):
        add("pulse", "github", "GitHub MCP needs you to sign in (Cursor CLI).")
        add("pulse", "github", "GitHub MCP not signed in; PR queue not fetched")
        add("pulse", "datadog", "No dashboards")
        stored = load("pulse")
        assert [i["source"] for i in stored] == ["github", "datadog"]
        assert stored[0]["message"] == "GitHub MCP needs you to sign in (Cursor CLI)."

    def test_merge_keeps_a_later_sign_in_fix(self):
        add("pulse", "github", "first")
        add("pulse", "github", "second", server="GitHub", agent="cursor")
        (issue,) = load("pulse")
        assert issue["message"] == "first"
        assert issue["fix"]["server"] == "GitHub"

    def test_merge_does_not_drop_existing_fix(self):
        add("pulse", "github", "first", server="GitHub", agent="cursor")
        add("pulse", "github", "second")
        assert load("pulse")[0]["fix"]["server"] == "GitHub"

    def test_server_with_known_agent_gets_login_fix(self):
        issue = add("pulse", "github", "sign in", server="GitHub", agent="cursor")
        assert issue["fix"] == {"kind": "mcp_login", "agent": "cursor", "server": "GitHub"}

    def test_server_with_unknown_agent_has_no_fix(self):
        assert add("pulse", "github", "sign in", server="GitHub", agent="pi")["fix"] is None

    def test_old_file_counts_as_empty(self):
        add("pulse", "github", "x")
        assert load("pulse", now=time.time() + run_issues.MAX_AGE_SECONDS + 1) == []

    @pytest.mark.parametrize("content", ["not json", "[]", '{"issues": [{"message": "x"}]}'])
    def test_unreadable_or_unstarted_file_is_empty(self, content):
        path = issues_path("pulse")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        assert load("pulse") == []

    def test_start_keeps_runner_run(self, monkeypatch):
        monkeypatch.setenv("EP_RUN_ID", "run-1")
        reset("pulse")
        add("pulse", "github", "from preflight")
        assert start("pulse") is False
        assert len(load("pulse")) == 1

    def test_start_resets_other_runs(self, monkeypatch):
        add("pulse", "github", "from an earlier run")
        monkeypatch.setenv("EP_RUN_ID", "run-2")
        assert start("pulse") is True
        assert load("pulse") == []

    def test_start_without_runner_resets(self):
        add("pulse", "github", "old")
        assert start("pulse") is True
        assert load("pulse") == []


class TestParseMcpList:
    def test_cursor_format(self):
        assert parse_mcp_list("cursor", CURSOR_LIST) == {
            "Atlassian": READY,
            "Backstage": NEEDS_AUTH,
            "GitHub": NEEDS_AUTH,
            "Glean": READY,
            "Datadog": "error",
        }

    def test_claude_format(self):
        assert parse_mcp_list("claude", CLAUDE_LIST) == {
            "acme-jira": READY,
            "acme-github-mcp": NEEDS_AUTH,
            "datadog": "error",
        }

    def test_empty_output(self):
        assert parse_mcp_list("cursor", "") == {}


class TestNeededSources:
    def test_pulse_defaults(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert needed_sources("pulse", ENV_MIN, dashboards=True) == ["datadog", "github"]

    def test_github_token_skips_github(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        env = {"GITHUB_TOKEN": "abc"}
        assert "github" not in needed_sources("pulse", env, dashboards=True)

    def test_stakeholders_need_glean(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        env = {"STAKEHOLDERS": "Jane Doe"}
        assert needed_sources("pulse", env, dashboards=False) == ["github", "glean"]

    def test_sprint_needs_atlassian(self):
        assert needed_sources("sprint", ENV_MIN) == ["atlassian"]

    def test_compare_needs_nothing(self):
        assert needed_sources("compare", ENV_MIN) == []


class TestPreflightIssues:
    @pytest.fixture(autouse=True)
    def _no_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def test_needs_sign_in_gets_button(self):
        servers = parse_mcp_list("cursor", CURSOR_LIST)
        found = preflight_issues("pulse", "cursor", servers, env=ENV_MIN, dashboards=True)
        github = next(i for i in found if i["source"] == "github")
        assert github["fix"] == {"kind": "mcp_login", "agent": "cursor", "server": "GitHub"}
        assert github["message"] == "GitHub MCP needs you to sign in (Cursor CLI)."

    def test_sign_in_message_names_server_when_different(self):
        servers = parse_mcp_list("claude", CLAUDE_LIST)
        found = preflight_issues("pulse", "claude", servers, env=ENV_MIN, dashboards=False)
        github = next(i for i in found if i["source"] == "github")
        assert (
            github["message"] == "GitHub MCP (acme-github-mcp) needs you to sign in (Claude Code)."
        )

    def test_failed_server_explains_without_button(self):
        servers = parse_mcp_list("cursor", CURSOR_LIST)
        found = preflight_issues("pulse", "cursor", servers, env=ENV_MIN, dashboards=True)
        datadog = next(i for i in found if i["source"] == "datadog")
        assert datadog["fix"] is None
        assert "did not connect" in datadog["message"]

    def test_not_configured(self):
        found = preflight_issues("pulse", "claude", {}, env=ENV_MIN, dashboards=True)
        assert {i["source"] for i in found} == {"datadog", "github"}
        assert all("not set up in Claude Code" in i["message"] for i in found)
        assert all(i["fix"] is None for i in found)

    def test_ready_servers_have_no_issue(self):
        servers = {"Datadog": READY, "GitHub": READY}
        assert preflight_issues("pulse", "cursor", servers, env=ENV_MIN, dashboards=True) == []

    def test_one_ready_match_is_enough(self):
        servers = {"github-old": NEEDS_AUTH, "GitHub": READY, "Datadog": READY}
        assert preflight_issues("pulse", "cursor", servers, env=ENV_MIN, dashboards=True) == []

    def test_jira_name_matches_atlassian(self):
        servers = parse_mcp_list("claude", CLAUDE_LIST)
        assert preflight_issues("sprint", "claude", servers, env=ENV_MIN) == []

    def test_no_dashboards(self):
        servers = {"GitHub": READY}
        found = preflight_issues("pulse", "cursor", servers, env=ENV_MIN, dashboards=False)
        assert len(found) == 1
        assert "/add-dashboard" in found[0]["message"]

    def test_cli_unavailable_only_checks_config(self):
        found = preflight_issues("pulse", "cursor", None, env=ENV_MIN, dashboards=False)
        assert [i["source"] for i in found] == ["datadog"]
        assert preflight_issues("pulse", "cursor", None, env=ENV_MIN, dashboards=True) == []


class TestMcpStatus:
    def test_pi_is_skipped(self):
        assert run_issues.mcp_status("pi") is None

    @patch("scripts.run_issues.subprocess.run")
    def test_parses_cli_output(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout=CURSOR_LIST)
        assert run_issues.mcp_status("cursor")["GitHub"] == NEEDS_AUTH
        assert mock_run.call_args.args[0] == ["agent", "mcp", "list"]
        assert mock_run.call_args.kwargs["timeout"] == run_issues.MCP_LIST_TIMEOUT

    @patch("scripts.run_issues.subprocess.run")
    def test_nonzero_exit_is_none(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 1, stdout="")
        assert run_issues.mcp_status("claude") is None

    @patch("scripts.run_issues.subprocess.run", side_effect=subprocess.TimeoutExpired("x", 1))
    def test_timeout_is_none(self, _run):
        assert run_issues.mcp_status("cursor") is None

    @patch("scripts.run_issues.subprocess.run", side_effect=FileNotFoundError("agent"))
    def test_missing_cli_is_none(self, _run):
        assert run_issues.mcp_status("cursor") is None


class TestPreflightWrites:
    def test_records_problems(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr(run_issues, "_dotenv", lambda: ENV_MIN)
        monkeypatch.setattr(run_issues, "has_dashboards", lambda *a: True)
        monkeypatch.setattr(
            run_issues, "mcp_status", lambda agent: parse_mcp_list("cursor", CURSOR_LIST)
        )
        reset("pulse")
        preflight("pulse", "cursor")
        stored = load("pulse")
        assert {i["source"] for i in stored} == {"datadog", "github"}
        assert json.loads(issues_path("pulse").read_text())["run_started"] > 0


class TestCli:
    def test_add_and_show(self, capsys):
        assert run_issues.main(["reset", "--type", "pulse"]) == 0
        args = ["add", "--type", "pulse", "--source", "github", "--message", "boom"]
        assert run_issues.main([*args, "--server", "GitHub", "--agent", "cursor"]) == 0
        assert run_issues.main(["show", "--type", "pulse"]) == 0
        shown = json.loads(capsys.readouterr().out)
        assert shown[0]["fix"]["server"] == "GitHub"

    def test_rejects_unknown_type(self):
        with pytest.raises(SystemExit):
            run_issues.main(["reset", "--type", "weekly"])
