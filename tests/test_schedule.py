"""Tests for scripts/schedule.py."""

import plistlib
from unittest.mock import patch

import pytest
from scripts.schedule import (
    build_intervals,
    describe,
    main,
    parse_days,
    parse_times,
    read_schedule,
)


def _write_plist(path, intervals):
    data = {
        "Label": "com.test.daily-dashboard",
        "ProgramArguments": ["/bin/bash", "/tmp/run.sh"],
        "StandardOutPath": "/tmp/out",
        "StartCalendarInterval": intervals,
    }
    with path.open("wb") as fh:
        plistlib.dump(data, fh)


@pytest.fixture
def plist(tmp_path, monkeypatch):
    path = tmp_path / "agent.plist"
    _write_plist(path, build_intervals([1, 2, 3, 4, 5], [(9, 0), (12, 0), (16, 0)]))
    monkeypatch.setenv("SCHEDULE_PLIST", str(path))
    return path


class TestParseDays:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("mon-fri", [1, 2, 3, 4, 5]),
            ("mon-sun", [1, 2, 3, 4, 5, 6, 0]),
            ("daily", [1, 2, 3, 4, 5, 6, 0]),
            ("weekends", [6, 0]),
            ("fri,mon,wed", [1, 3, 5]),
            ("Monday,Sunday", [1, 0]),
            ("weekdays,sat", [1, 2, 3, 4, 5, 6]),
        ],
    )
    def test_valid(self, spec, expected):
        assert parse_days(spec) == expected

    @pytest.mark.parametrize("spec", ["", "xyz", "fri-mon", ","])
    def test_invalid(self, spec):
        with pytest.raises(ValueError):
            parse_days(spec)


class TestParseTimes:
    def test_bare_hour_and_sorting(self):
        assert parse_times("16:00, 9 ,12:30") == [(9, 0), (12, 30), (16, 0)]

    def test_deduplicates(self):
        assert parse_times("10:00,10") == [(10, 0)]

    @pytest.mark.parametrize("spec", ["24:00", "9:60", "nine", "", "10:5"])
    def test_invalid(self, spec):
        with pytest.raises(ValueError):
            parse_times(spec)

    def test_too_many(self):
        with pytest.raises(ValueError, match="at most"):
            parse_times(",".join(f"{h}:00" for h in range(13)))


class TestIntervals:
    def test_every_day_omits_weekday(self):
        assert build_intervals(parse_days("mon-sun"), [(10, 0)]) == [{"Hour": 10, "Minute": 0}]

    def test_weekdays_expand_per_day(self):
        intervals = build_intervals([1, 3], [(9, 0), (16, 30)])
        assert len(intervals) == 4
        assert {"Weekday": 3, "Hour": 16, "Minute": 30} in intervals

    def test_describe_round_trip(self):
        summary = describe(build_intervals([1, 2, 3, 4, 5], [(9, 0), (12, 0)]))
        assert summary == {"days": [1, 2, 3, 4, 5], "times": ["09:00", "12:00"], "irregular": False}

    def test_describe_every_day_and_sunday_seven(self):
        assert describe({"Hour": 10, "Minute": 0})["days"] == [1, 2, 3, 4, 5, 6, 0]
        assert describe([{"Weekday": 7, "Hour": 8}])["days"] == [0]

    def test_describe_flags_irregular(self):
        summary = describe([{"Weekday": 1, "Hour": 9}, {"Weekday": 2, "Hour": 10}])
        assert summary["irregular"] is True


class TestMain:
    def test_show(self, plist, capsys):
        assert main(["show"]) == 0
        out = capsys.readouterr().out
        assert "Mon–Fri" in out
        assert "09:00, 12:00, 16:00" in out

    def test_show_missing_plist(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SCHEDULE_PLIST", str(tmp_path / "missing.plist"))
        assert main(["show"]) == 1

    def test_set_rewrites_only_schedule_and_reloads(self, plist):
        with (
            patch("scripts.schedule.subprocess.run") as run,
            patch("scripts.schedule._refresh_index"),
        ):
            assert main(["set", "--days", "mon-sun", "--times", "10:00"]) == 0
        data = plistlib.loads(plist.read_bytes())
        assert data["StartCalendarInterval"] == [{"Hour": 10, "Minute": 0}]
        assert data["Label"] == "com.test.daily-dashboard"
        assert data["ProgramArguments"] == ["/bin/bash", "/tmp/run.sh"]
        cmds = [c.args[0] for c in run.call_args_list]
        assert cmds == [["launchctl", "unload", str(plist)], ["launchctl", "load", str(plist)]]
        assert read_schedule(plist)["times"] == ["10:00"]

    def test_dry_run_leaves_plist(self, plist):
        before = plist.read_bytes()
        with patch("scripts.schedule.subprocess.run") as run:
            assert main(["set", "--days", "mon-sun", "--times", "10:00", "--dry-run"]) == 0
        assert plist.read_bytes() == before
        run.assert_not_called()

    def test_invalid_input_exits_2(self, plist):
        before = plist.read_bytes()
        assert main(["set", "--days", "mon-fri", "--times", "25:00"]) == 2
        assert plist.read_bytes() == before
