"""Tests for scripts/deliver_report.py."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from scripts.deliver_report import delivery_mode, ensure, notification_text, send
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


def test_notification_text_defaults(monkeypatch):
    for key in ("NOTIFY_TITLE", "NOTIFY_SUBTITLE", "NOTIFY_MESSAGE"):
        monkeypatch.delenv(key, raising=False)
    assert notification_text(ENTRY, "pulse") == (
        "Engineering Pulse ready",
        "Fri 2026-10-02 · 09:00",
        "Daily Dashboard — team-a — click to open",
    )


def test_notification_text_from_env(monkeypatch):
    monkeypatch.setenv("NOTIFY_TITLE", "📊 {type_label} · {time}")
    monkeypatch.setenv("NOTIFY_SUBTITLE", "")
    monkeypatch.setenv("NOTIFY_MESSAGE", "{title} {unknown}")
    title, subtitle, message = notification_text(ENTRY, "sprint")
    assert title == "📊 Sprint report · 09:00"
    assert subtitle == "Fri 2026-10-02 · 09:00"  # empty value falls back to the default
    assert message == "Daily Dashboard — team-a {unknown}"


def test_notification_text_bad_template_falls_back(monkeypatch):
    monkeypatch.setenv("NOTIFY_TITLE", "{broken")
    assert notification_text(ENTRY, "pulse")[0] == "Engineering Pulse ready"


def test_send_notify_uses_templates(tmp_path, monkeypatch, notify, email):
    monkeypatch.setenv("NOTIFY_MESSAGE", "Open {type_label}")
    send(_report(tmp_path), "pulse", root=tmp_path / "reports")
    assert notify.call_args.args[1] == "Open Engineering Pulse"


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


def test_ensure_failure_with_none_does_not_notify(tmp_path, monkeypatch, notify, email):
    monkeypatch.setenv("DELIVERY", "none")
    root = tmp_path / "reports"
    assert ensure("pulse", datetime.now(), None, root=root) == 1
    assert load_manifest(root)[0]["status"] == "failed"
    notify.assert_not_called()


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

    def test_records_failure_for_stale_report(self, tmp_path, notify, email):
        root = tmp_path / "reports"
        report = _report(tmp_path)
        old = (datetime.now() - timedelta(hours=3)).timestamp()
        os.utime(report, (old, old))
        assert ensure("pulse", datetime.now() - timedelta(minutes=5), report, 3, root=root) == 1
        entry = load_manifest(root)[0]
        assert entry["status"] == "failed"
        assert "code 3" in entry["note"]
        assert "failed" in notify.call_args.args[0]

    def test_records_failure_when_no_report(self, tmp_path, notify, email):
        root = tmp_path / "reports"
        assert ensure("sprint", datetime.now(), None, root=root) == 1
        assert load_manifest(root)[0]["type"] == "sprint"
