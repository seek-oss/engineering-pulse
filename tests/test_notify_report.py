"""Tests for scripts/notify_report.py."""

from unittest.mock import patch

from scripts.notify_report import notify, to_url


def test_to_url(tmp_path):
    assert to_url("https://example.com/x") == "https://example.com/x"
    assert to_url(tmp_path / "a b.html") == (tmp_path / "a b.html").resolve().as_uri()


def test_non_macos_prints(capsys):
    with patch("scripts.notify_report.platform.system", return_value="Linux"):
        assert notify("T", "M", open_target="https://x") == "print"
    assert "T: M — https://x" in capsys.readouterr().out


@patch("scripts.notify_report.platform.system", return_value="Darwin")
@patch("scripts.notify_report.subprocess.run")
def test_terminal_notifier_opens_target(run, _system, tmp_path):
    target = tmp_path / "latest-day.html"
    with patch("scripts.notify_report.find_terminal_notifier", return_value="/bin/tn"):
        assert notify("Ready", "Report · 09:00", open_target=target) == "terminal-notifier"
    cmd = run.call_args.args[0]
    assert cmd[0] == "/bin/tn"
    assert cmd[cmd.index("-open") + 1] == target.resolve().as_uri()
    assert cmd[cmd.index("-message") + 1] == "Report · 09:00"


@patch("scripts.notify_report.platform.system", return_value="Darwin")
@patch("scripts.notify_report.subprocess.run")
def test_osascript_fallback_passes_text_as_arguments(run, _system):
    with patch("scripts.notify_report.find_terminal_notifier", return_value=None):
        assert notify('Say "hi"', 'msg\'; do shell script "x"') == "osascript"
    cmd = run.call_args.args[0]
    assert cmd[:2] == ["osascript", "-e"]
    assert "on run argv" in cmd[2]
    assert cmd[3:] == ['msg\'; do shell script "x"', 'Say "hi"', ""]


@patch("scripts.notify_report.platform.system", return_value="Darwin")
@patch("scripts.notify_report.subprocess.run")
def test_never_auto_opens_from_legacy_env(run, _system, monkeypatch):
    monkeypatch.setenv("REPORT_AUTO_OPEN", "1")
    with patch("scripts.notify_report.find_terminal_notifier", return_value=None):
        notify("T", "M", open_target="https://x")
    assert all(call.args[0] != ["open", "https://x"] for call in run.call_args_list)
