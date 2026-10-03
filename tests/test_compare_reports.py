"""Tests for scripts/compare_reports.py."""

import json
from datetime import datetime

import pytest
from scripts.compare_reports import CompareError, main, parse_url, prepare, validate
from scripts.report_archive import archive, record_failure

SPRINT = (
    "<!doctype html><html><head><title>Sprint {n}</title></head><body>"
    '<svg data-current-scope="5" data-current-completed="{n}"></svg></body></html>'
)


@pytest.fixture(autouse=True)
def _no_schedule(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHEDULE_PLIST", str(tmp_path / "no-agent.plist"))


@pytest.fixture
def archived(tmp_path):
    root = tmp_path / "reports"
    ids = {}
    for n, (kind, when) in enumerate(
        [
            ("sprint", datetime(2026, 9, 22, 9)),
            ("sprint", datetime(2026, 9, 24, 9)),
            ("pulse", datetime(2026, 9, 24, 10)),
        ]
    ):
        src = tmp_path / f"r{n}.html"
        src.write_text(SPRINT.format(n=n))
        entry, _ = archive(src, kind, root=root, when=when, rebuild=False)
        ids[n] = entry["id"]
    failed = record_failure("sprint", root=root, when=datetime(2026, 9, 25, 9), rebuild=False)
    ids["failed"] = failed["id"]
    return root, ids


class TestValidate:
    def test_accepts_two_reports_of_same_type(self, archived):
        root, ids = archived
        a, b = validate(ids[0], ids[1], root)
        assert (a["id"], b["id"]) == (ids[0], ids[1])

    @pytest.mark.parametrize(
        "a,b,message",
        [
            ("sprint-20260922-090000; rm -rf ~", "x", "not a report id"),
            ("../etc/passwd", "sprint-20260924-090000", "not a report id"),
            ("sprint-20260101-000000", "sprint-20260924-090000", "not in the archive"),
        ],
    )
    def test_rejects_bad_ids(self, archived, a, b, message):
        root, _ = archived
        with pytest.raises(CompareError, match=message):
            validate(a, b, root)

    def test_rejects_same_failed_and_mixed(self, archived):
        root, ids = archived
        with pytest.raises(CompareError, match="different"):
            validate(ids[0], ids[0], root)
        with pytest.raises(CompareError, match="failed run"):
            validate(ids[0], ids["failed"], root)
        with pytest.raises(CompareError, match="different types"):
            validate(ids[0], ids[2], root)


class TestParseUrl:
    def test_extracts_ids(self):
        assert parse_url(
            "engineering-pulse://compare?a=sprint-20260922-090000&b=sprint-20260924-090000"
        ) == ("sprint-20260922-090000", "sprint-20260924-090000")

    @pytest.mark.parametrize(
        "url",
        [
            "https://compare?a=sprint-20260922-090000&b=sprint-20260924-090000",
            "engineering-pulse://run?a=sprint-20260922-090000&b=sprint-20260924-090000",
            "engineering-pulse://compare?a=$(whoami)&b=sprint-20260924-090000",
        ],
    )
    def test_rejects_other_links(self, url):
        with pytest.raises(CompareError):
            parse_url(url)


class TestPrepare:
    def test_writes_context_older_first(self, archived, tmp_path):
        root, ids = archived
        out = tmp_path / "output"
        path = prepare(ids[1], ids[0], root=root, output=out)

        assert path == out / "compare" / f"context-{ids[0]}-vs-{ids[1]}.json"
        ctx = json.loads(path.read_text())
        assert ctx["type"] == "sprint"
        assert ctx["older"]["id"] == ids[0] and ctx["newer"]["id"] == ids[1]
        assert ctx["older"]["snapshot"]["totals"] == {"scope": 5, "completed": 0}
        assert ctx["output_html"].endswith(f"compare-{ids[0]}-vs-{ids[1]}.html")
        assert ctx["subject"] == "Sprint report: 2026-09-22 09:00 vs 2026-09-24 09:00"

    def test_cli_returns_2_on_invalid(self, archived, monkeypatch):
        root, _ = archived
        monkeypatch.setenv("REPORTS_DIR", str(root))
        assert main(["prepare", "--a", "bad", "--b", "bad2"]) == 2
