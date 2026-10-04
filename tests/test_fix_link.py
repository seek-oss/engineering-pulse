"""Tests for scripts/fix_link.py — the red box's Sign in and Re-run buttons."""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts import fix_link
from scripts.fix_link import LinkError, handle, parse, terminal_command
from scripts.run_issues import NEEDS_AUTH, READY


@pytest.fixture(autouse=True)
def _lock(tmp_path, monkeypatch):
    monkeypatch.setattr(fix_link, "LOCK_DIR", tmp_path / "run.lock")


@pytest.fixture
def servers():
    with patch(
        "scripts.fix_link.run_issues.mcp_status",
        return_value={"GitHub": NEEDS_AUTH, "Glean": READY},
    ) as mock:
        yield mock


@pytest.fixture
def terminal():
    with patch("scripts.fix_link.open_terminal") as mock:
        yield mock


class TestParse:
    def test_auth(self):
        assert parse("engineering-pulse://auth?agent=cursor&server=GitHub") == (
            "auth",
            {"agent": "cursor", "server": "GitHub"},
        )

    @pytest.mark.parametrize(
        "url",
        [
            "https://auth?agent=cursor",
            "engineering-pulse://settings?x=1",
            "engineering-pulse://delete?type=pulse",
            "",
        ],
    )
    def test_rejects_other_links(self, url):
        with pytest.raises(LinkError):
            parse(url)


class TestAuth:
    def test_cursor_opens_login(self, servers, terminal):
        msg = handle("engineering-pulse://auth?agent=cursor&server=GitHub")
        assert msg == "Opened Terminal to sign in to GitHub."
        assert terminal.call_args.args[0].endswith("agent mcp login GitHub")
        servers.assert_called_once_with("cursor")

    def test_unknown_agent(self, servers, terminal):
        with pytest.raises(LinkError, match="Unknown agent"):
            handle("engineering-pulse://auth?agent=pi&server=GitHub")
        terminal.assert_not_called()

    def test_server_must_be_listed(self, servers, terminal):
        with pytest.raises(LinkError, match="not an MCP server"):
            handle("engineering-pulse://auth?agent=cursor&server=GitHub%3B%20rm%20-rf")
        terminal.assert_not_called()

    def test_cli_unavailable(self, terminal):
        with patch("scripts.fix_link.run_issues.mcp_status", return_value=None):
            with pytest.raises(LinkError, match="Could not list"):
                handle("engineering-pulse://auth?agent=claude&server=GitHub")

    def test_already_signed_in(self, servers, terminal):
        assert "already signed in" in handle("engineering-pulse://auth?agent=cursor&server=Glean")
        terminal.assert_not_called()


class TestTerminalCommand:
    def test_cursor(self):
        cmd = terminal_command("cursor", "GitHub", Path("/opt/ep dir"))
        assert cmd == "cd '/opt/ep dir' && agent mcp login GitHub"

    def test_claude_starts_claude_with_hint(self):
        cmd = terminal_command("claude", "acme-github-mcp", Path("/opt/ep"))
        assert cmd.startswith("cd /opt/ep && echo ")
        assert "/mcp" in cmd and "acme-github-mcp" in cmd
        assert cmd.endswith("&& claude")

    def test_quotes_odd_server_names(self):
        cmd = terminal_command("cursor", "a b'c", Path("/opt/ep"))
        assert cmd.endswith("agent mcp login 'a b'\"'\"'c'")

    def test_applescript_string_escapes(self):
        assert fix_link._applescript_string('say "hi" \\ there') == '"say \\"hi\\" \\\\ there"'


class TestRun:
    @pytest.fixture
    def runner(self, tmp_path, monkeypatch):
        path = tmp_path / "run-daily-dashboard.sh"
        path.write_text("#!/bin/bash\n")
        monkeypatch.setenv("EP_RUNNER", str(path))
        return path

    def test_starts_runner_for_one_report(self, runner):
        with (
            patch("scripts.fix_link.subprocess.Popen") as popen,
            patch("scripts.fix_link.notify") as notify,
        ):
            assert handle("engineering-pulse://run?type=sprint") == "Started Sprint report."
        assert popen.call_args.args[0] == ["/bin/bash", str(runner)]
        assert popen.call_args.kwargs["env"]["ENGINEERING_PULSE_ONLY"] == "sprint"
        assert popen.call_args.kwargs["start_new_session"] is True
        assert notify.call_args.args[0] == "Re-running Sprint report"

    @pytest.mark.parametrize("value", ["compare", "", "pulse;rm"])
    def test_rejects_unknown_type(self, runner, value):
        with patch("scripts.fix_link.subprocess.Popen") as popen:
            with pytest.raises(LinkError, match="Unknown report type"):
                handle(f"engineering-pulse://run?type={value}")
        popen.assert_not_called()

    def test_refuses_while_running(self, runner):
        fix_link.LOCK_DIR.mkdir()
        with patch("scripts.fix_link.subprocess.Popen") as popen:
            with pytest.raises(LinkError, match="already in progress"):
                handle("engineering-pulse://run?type=pulse")
        popen.assert_not_called()

    def test_stale_lock_is_ignored(self, runner):
        fix_link.LOCK_DIR.mkdir()
        old = time.time() - fix_link.LOCK_STALE_SECONDS - 60
        os.utime(fix_link.LOCK_DIR, (old, old))
        assert fix_link.run_in_progress() is False

    def test_missing_runner(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EP_RUNNER", str(tmp_path / "missing.sh"))
        with pytest.raises(LinkError, match="Runner not found"):
            handle("engineering-pulse://run?type=pulse")


class TestMain:
    def test_error_goes_to_stderr(self, capsys):
        assert fix_link.main(["handle", "engineering-pulse://nope"]) == 1
        assert "Unsupported link." in capsys.readouterr().err

    def test_usage(self):
        assert fix_link.main([]) == 2

    def test_success_prints_message(self, servers, terminal, capsys):
        assert fix_link.main(["handle", "engineering-pulse://auth?agent=cursor&server=GitHub"]) == 0
        assert "Opened Terminal" in capsys.readouterr().out
