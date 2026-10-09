"""Tests for scripts/settings.py."""

import plistlib
import stat

import pytest
from scripts import schedule
from scripts.settings import (
    SettingsError,
    apply,
    current_settings,
    describe,
    main,
    parse_url,
    runner_supports_pause,
    upsert_env,
)

URL = "engineering-pulse://settings?"


@pytest.fixture
def plist(tmp_path):
    path = tmp_path / "agent.plist"
    intervals = schedule.build_intervals([1, 2, 3, 4, 5], [(9, 0), (12, 0)])
    path.write_bytes(
        plistlib.dumps({"Label": "com.test.daily", "StartCalendarInterval": intervals})
    )
    return path


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# secrets\nGITHUB_TOKEN=abc\nREPORT_RETENTION_DAYS=90\n")
    path.chmod(0o600)
    return path


class TestParseUrl:
    def test_parses_all_fields(self):
        changes = parse_url(URL + "days=mon,sun&times=10:00,8:30&reports=sprint&retention=30")
        assert changes == {
            "days": [1, 0],
            "times": ["08:30", "10:00"],
            "reports": ["sprint"],
            "retention": 30,
        }

    def test_none_pauses_all(self):
        assert parse_url(URL + "reports=none") == {"reports": []}

    @pytest.mark.parametrize(
        "url,message",
        [
            ("https://settings?reports=none", "unsupported"),
            ("engineering-pulse://compare?reports=none", "unsupported"),
            (URL + "GITHUB_TOKEN=x", "unknown setting"),
            (URL + "reports=pulse;rm -rf ~", "unknown report"),
            (URL + "times=25:00", "out of range"),
            (URL + "days=funday", "unknown day"),
            (URL + "auto_open=1", "unknown setting"),
            (URL + "retention=-1", "retention"),
            (URL + "retention=99999", "retention"),
            (URL + "reports=pulse&reports=none", "only once"),
        ],
    )
    def test_rejects_bad_links(self, url, message):
        with pytest.raises(SettingsError, match=message):
            parse_url(url)


class TestDescribeAndApply:
    def test_describe_lists_only_changes(self, plist, env_file):
        current = current_settings(plist, env_file)
        lines = describe(current, {"reports": ["pulse"], "retention": 90, "times": ["10:00"]})
        assert lines == [
            "Run times: 09:00, 12:00 → 10:00",
            "Scheduled reports: Engineering Pulse + Sprint report → Engineering Pulse",
        ]

    def test_apply_updates_plist_and_env(self, plist, env_file):
        changes = parse_url(URL + "days=mon-sun&times=10:00&reports=none&retention=30")
        lines = apply(changes, plist=plist, env_file=env_file, reload=False, rebuild=False)

        assert len(lines) == 4
        assert schedule.read_schedule(plist)["days"] == schedule.ORDERED_DAYS
        assert schedule.read_schedule(plist)["times"] == ["10:00"]
        text = env_file.read_text()
        assert "GITHUB_TOKEN=abc" in text and "# secrets" in text
        assert "REPORT_RETENTION_DAYS=30" in text and "SCHEDULED_REPORTS=none" in text
        assert current_settings(plist, env_file)["reports"] == []

    def test_apply_without_changes_is_a_no_op(self, plist, env_file):
        before = env_file.read_text()
        assert apply({"retention": 90}, plist=plist, env_file=env_file, rebuild=False) == []
        assert env_file.read_text() == before

    def test_schedule_change_needs_installed_agent(self, tmp_path, env_file):
        with pytest.raises(SettingsError, match="install.sh"):
            apply({"times": ["10:00"]}, plist=tmp_path / "missing.plist", env_file=env_file)


class TestUpsertEnv:
    def test_replaces_appends_and_keeps_mode(self, env_file):
        upsert_env(env_file, {"REPORT_RETENTION_DAYS": "7", "SCHEDULED_REPORTS": "pulse"})
        lines = env_file.read_text().splitlines()
        assert lines == [
            "# secrets",
            "GITHUB_TOKEN=abc",
            "REPORT_RETENTION_DAYS=7",
            "SCHEDULED_REPORTS=pulse",
        ]
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_runner_supports_pause(tmp_path):
    old, new = tmp_path / "old.sh", tmp_path / "new.sh"
    old.write_text("run_skill_step daily-dashboard")
    new.write_text("report_enabled pulse")
    assert not runner_supports_pause(old)
    assert runner_supports_pause(new)


def test_default_retention_keeps_reports_forever(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# no retention override\n")
    assert current_settings(tmp_path / "missing.plist", env_file)["retention"] == 0


def test_cli_rejects_bad_link(capsys):
    assert main(["describe-url", URL + "token=1"]) == 2
    assert "Settings not applied" in capsys.readouterr().err
