"""Tests for scripts/deliver_report.py."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from scripts import deliver_report, run_issues
from scripts.deliver_report import agent_message, delivery_mode, ensure, notification_text, send
from scripts.issue_box import MARKER
from scripts.report_archive import load_manifest


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHEDULE_PLIST", str(tmp_path / "no-agent.plist"))
    monkeypatch.setenv("REPORT_RETENTION_DAYS", "0")
    monkeypatch.setenv("DELIVERY", "notify")


@pytest.fixture
def notify():
    with patch("scripts.deliver_report.notify", return_value="osascript") as mock:
        yield mock


@pytest.fixture
def email():
    with patch("scripts.deliver_report.send_email", return_value=0) as mock:
        yield mock


def _report(tmp_path, body="x"):
    path = tmp_path / "daily_dashboard_report.html"
    path.write_text(f"<html><title>Daily Dashboard</title><body>{body}</body></html>")
    return path


@pytest.mark.parametrize(
    ("value", "expected"),
    [("", "notify"), ("EMAIL", "email"), ("both", "both"), ("none", "none"), ("slack", "notify")],
)
def test_delivery_mode(monkeypatch, value, expected):
    monkeypatch.setenv("DELIVERY", value)
    assert delivery_mode() == expected


ENTRY = {"title": "Daily Dashboard — team-a", "date": "2026-10-02", "time": "09:00"}


def test_notification_text():
    assert notification_text(ENTRY, "pulse") == (
        "Engineering Pulse ready",
        "Fri 2 Oct · 09:00",
        "Daily Dashboard — team-a",
    )
    assert notification_text(ENTRY, "sprint")[0] == "Sprint report ready"


def test_send_notify_passes_text(tmp_path, notify, email):
    send(_report(tmp_path), "pulse", root=tmp_path / "reports")
    assert notify.call_args.args == ("Engineering Pulse ready", "Daily Dashboard")
    assert notify.call_args.kwargs["subtitle"].endswith(
        load_manifest(tmp_path / "reports")[0]["time"]
    )


def test_send_notify_only(tmp_path, notify, email):
    root = tmp_path / "reports"
    assert send(_report(tmp_path), "pulse", root=root) == 0
    assert len(load_manifest(root)) == 1
    notify.assert_called_once()
    assert notify.call_args.kwargs["open_target"] == root / "latest-day.html"
    email.assert_not_called()


def test_send_both_uses_subject(tmp_path, monkeypatch, notify, email):
    monkeypatch.setenv("DELIVERY", "both")
    report = _report(tmp_path)
    assert send(report, "pulse", subject="Subj", root=tmp_path / "reports") == 0
    notify.assert_called_once()
    email.assert_called_once_with("Subj", report)


def test_send_email_failure_keeps_archive(tmp_path, monkeypatch, notify, email):
    monkeypatch.setenv("DELIVERY", "email")
    email.return_value = 1
    root = tmp_path / "reports"
    assert send(_report(tmp_path), "pulse", root=root) == 1
    assert len(load_manifest(root)) == 1
    notify.assert_not_called()


def test_send_none_archives_only(tmp_path, monkeypatch, notify, email):
    monkeypatch.setenv("DELIVERY", "none")
    root = tmp_path / "reports"
    assert send(_report(tmp_path), "pulse", root=root) == 0
    assert len(load_manifest(root)) == 1
    notify.assert_not_called()
    email.assert_not_called()


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    """Point fallback reports at tmp and stub the pulse renderer."""
    monkeypatch.setattr(deliver_report, "ROOT", tmp_path)
    with patch("scripts.deliver_report._render_pulse", return_value=False) as render:
        yield render


def test_ensure_failure_with_none_does_not_notify(tmp_path, monkeypatch, notify, email, out_dir):
    monkeypatch.setenv("DELIVERY", "none")
    root = tmp_path / "reports"
    assert ensure("pulse", datetime.now(), None, root=root) == 1
    assert load_manifest(root)[0]["status"] == "ok"
    notify.assert_not_called()


def test_notification_text_counts_problems():
    assert notification_text({**ENTRY, "issues": 1}, "pulse")[0] == (
        "Engineering Pulse ready — 1 problem"
    )
    assert notification_text({**ENTRY, "issues": 3}, "sprint")[0] == (
        "Sprint report ready — 3 problems"
    )


class TestSendProblems:
    def test_injects_box_and_counts(self, tmp_path, notify, email):
        run_issues.reset("pulse")
        run_issues.add(
            "pulse", "github", "GitHub MCP needs sign-in", server="GitHub", agent="cursor"
        )
        root = tmp_path / "reports"
        report = _report(tmp_path)
        assert send(report, "pulse", root=root) == 0
        entry = load_manifest(root)[0]
        assert entry["issues"] == 1
        archived = (root / entry["path"]).read_text()
        assert MARKER in archived and "Sign in to GitHub" in archived
        assert MARKER in report.read_text()
        assert notify.call_args.args[0] == "Engineering Pulse ready — 1 problem"

    def test_no_problems_no_box(self, tmp_path, notify, email):
        root = tmp_path / "reports"
        send(_report(tmp_path), "pulse", root=root)
        entry = load_manifest(root)[0]
        assert "issues" not in entry
        assert MARKER not in (root / entry["path"]).read_text()

    def test_old_box_removed_when_run_is_clean(self, tmp_path, notify, email):
        run_issues.add("pulse", "github", "old problem")
        report = _report(tmp_path)
        send(report, "pulse", root=tmp_path / "r1")
        run_issues.reset("pulse")
        send(report, "pulse", root=tmp_path / "r2")
        assert MARKER not in report.read_text()

    def test_problems_of_other_type_ignored(self, tmp_path, notify, email):
        run_issues.add("sprint", "atlassian", "Jira down")
        root = tmp_path / "reports"
        send(_report(tmp_path), "pulse", root=root)
        assert "issues" not in load_manifest(root)[0]


def test_send_duplicate_skips_notify(tmp_path, notify, email):
    root = tmp_path / "reports"
    report = _report(tmp_path)
    send(report, "pulse", root=root)
    send(report, "pulse", root=root)
    assert notify.call_count == 1


class TestEnsure:
    def test_skips_when_agent_delivered(self, tmp_path, notify, email):
        root = tmp_path / "reports"
        start = datetime.now() - timedelta(seconds=5)
        send(_report(tmp_path), "pulse", root=root)
        notify.reset_mock()
        assert ensure("pulse", start, _report(tmp_path, body="later"), root=root) == 0
        assert len(load_manifest(root)) == 1
        notify.assert_not_called()

    def test_delivers_fresh_report(self, tmp_path, notify, email):
        root = tmp_path / "reports"
        start = datetime.now() - timedelta(seconds=5)
        assert ensure("pulse", start, _report(tmp_path), root=root) == 0
        assert load_manifest(root)[0]["status"] == "ok"
        notify.assert_called_once()

    def test_stale_report_gets_fallback_not_old_copy(self, tmp_path, notify, email, out_dir):
        root = tmp_path / "reports"
        report = _report(tmp_path, body="yesterday")
        old = (datetime.now() - timedelta(hours=3)).timestamp()
        os.utime(report, (old, old))
        assert ensure("pulse", datetime.now() - timedelta(minutes=5), report, 3, root=root) == 1
        entry = load_manifest(root)[0]
        assert entry["status"] == "ok"
        assert entry["issues"] == 1
        archived = (root / entry["path"]).read_text()
        assert "yesterday" not in archived
        assert "exit code 3" in archived
        assert "No sections could be generated" in archived
        assert notify.call_args.args[0] == "Engineering Pulse ready — 1 problem"

    def test_pulse_fallback_uses_renderer_with_since(self, tmp_path, notify, email, out_dir):
        def render(since, out):
            out.write_text("<html><title>Daily Dashboard</title><body>fresh PRs</body></html>")
            return True

        out_dir.side_effect = render
        root = tmp_path / "reports"
        start = datetime.now() - timedelta(seconds=5)
        assert ensure("pulse", start, None, 1, root=root) == 1
        assert out_dir.call_args.args[0] == start
        entry = load_manifest(root)[0]
        archived = (root / entry["path"]).read_text()
        assert "fresh PRs" in archived
        assert MARKER in archived
        assert "exit code 1" in archived

    def test_sprint_fallback_frame(self, tmp_path, notify, email, out_dir):
        run_issues.reset("sprint")
        run_issues.add("sprint", "atlassian", "Atlassian MCP needs sign-in")
        root = tmp_path / "reports"
        assert ensure("sprint", datetime.now(), None, 130, root=root) == 1
        entry = load_manifest(root)[0]
        assert entry["type"] == "sprint"
        assert entry["issues"] == 2
        archived = (root / entry["path"]).read_text()
        assert "Atlassian MCP needs sign-in" in archived
        assert "interrupted" in archived
        assert "(incomplete)" in entry["title"]
        out_dir.assert_not_called()

    def test_fresh_report_with_error_exit_adds_problem(self, tmp_path, notify, email):
        root = tmp_path / "reports"
        start = datetime.now() - timedelta(seconds=5)
        assert ensure("pulse", start, _report(tmp_path), 2, root=root) == 0
        entry = load_manifest(root)[0]
        assert entry["issues"] == 1
        assert "some sections may be missing" in (root / entry["path"]).read_text()


class TestAgentMessage:
    def test_wording(self):
        assert "interrupted" in agent_message("pulse", 130, False)
        assert "exit code 4" in agent_message("pulse", 4, False)
        assert "without writing a report" in agent_message("sprint", 0, False)
        assert "/tmp/engineering-pulse-compare.log" in agent_message("compare", 1, False)
