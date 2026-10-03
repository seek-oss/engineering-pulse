"""Tests for scripts/report_archive.py."""

import json
import os
from datetime import datetime, timedelta

import pytest
from scripts.report_archive import (
    archive,
    backfill,
    build_index,
    entries_since,
    extract_title,
    load_manifest,
    prune,
    record_failure,
)


@pytest.fixture(autouse=True)
def _no_schedule(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHEDULE_PLIST", str(tmp_path / "no-agent.plist"))


def _report(tmp_path, name="report.html", title="Daily Dashboard — team-a — 2026-10-02", body=""):
    path = tmp_path / name
    path.write_text(
        f"<!doctype html><html><head><title>{title}</title></head><body>{body}</body></html>"
    )
    return path


def _embedded_data(root):
    html = (root / "index.html").read_text(encoding="utf-8")
    start = html.index('<script id="report-data" type="application/json">') + len(
        '<script id="report-data" type="application/json">'
    )
    end = html.index("</script>", start)
    return json.loads(html[start:end].replace("<\\/", "</"))


class TestArchive:
    def test_copies_report_and_writes_manifest(self, tmp_path):
        root = tmp_path / "reports"
        when = datetime(2026, 10, 2, 9, 0, 12)
        entry, created = archive(_report(tmp_path), "pulse", root=root, when=when)

        assert created
        assert entry["path"] == "2026/10/02/pulse-090012.html"
        assert entry["date"] == "2026-10-02" and entry["time"] == "09:00"
        assert entry["status"] == "ok"
        assert entry["title"] == "Daily Dashboard — team-a — 2026-10-02"
        assert (root / entry["path"]).read_text().startswith("<!doctype html>")
        assert load_manifest(root) == [entry]

    def test_builds_index_latest_and_redirect(self, tmp_path):
        root = tmp_path / "reports"
        entry, _ = archive(_report(tmp_path), "pulse", root=root, when=datetime(2026, 10, 2, 9))

        html = (root / "index.html").read_text()
        assert "__REPORT_DATA__" not in html
        assert _embedded_data(root)["entries"][0]["id"] == entry["id"]
        assert (root / "latest.html").read_bytes() == (root / entry["path"]).read_bytes()
        assert f"index.html#/day/2026-10-02/{entry['id']}" in (root / "latest-day.html").read_text()

    def test_identical_content_is_not_duplicated(self, tmp_path):
        root = tmp_path / "reports"
        src = _report(tmp_path)
        first, _ = archive(src, "pulse", root=root, when=datetime(2026, 10, 2, 9))
        again, created = archive(src, "pulse", root=root, when=datetime(2026, 10, 2, 12))

        assert not created
        assert again["id"] == first["id"]
        assert len(load_manifest(root)) == 1

    def test_same_second_reports_get_unique_ids_and_paths(self, tmp_path):
        root = tmp_path / "reports"
        when = datetime(2026, 10, 2, 9)
        a, _ = archive(_report(tmp_path, "a.html", body="a"), "pulse", root=root, when=when)
        b, _ = archive(_report(tmp_path, "b.html", body="b"), "pulse", root=root, when=when)

        assert a["id"] != b["id"]
        assert a["path"] != b["path"]
        assert (root / a["path"]).read_text() != (root / b["path"]).read_text()

    def test_unknown_type_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            archive(_report(tmp_path), "weekly", root=tmp_path / "reports")

    def test_script_close_tag_in_title_is_escaped(self, tmp_path):
        root = tmp_path / "reports"
        archive(_report(tmp_path, title="x &lt;/script&gt; y"), "pulse", root=root)
        html = (root / "index.html").read_text()
        assert html.count("</script>") == 2  # data block + app script only
        assert _embedded_data(root)["entries"][0]["title"] == "x </script> y"


def test_extract_title_fallback():
    assert extract_title("<html><title>  A\n  B </title>", "x") == "A B"
    assert extract_title("<html>no title</html>", "Fallback") == "Fallback"


def test_record_failure(tmp_path):
    root = tmp_path / "reports"
    entry = record_failure("sprint", root=root, when=datetime(2026, 10, 2, 16), note="exit 1")
    assert entry["status"] == "failed"
    assert "path" not in entry
    assert entry["note"] == "exit 1"
    assert _embedded_data(root)["entries"][0]["status"] == "failed"
    assert not (root / "latest.html").exists()


def test_entries_since(tmp_path):
    root = tmp_path / "reports"
    archive(_report(tmp_path, body="old"), "pulse", root=root, when=datetime(2026, 10, 1, 9))
    archive(_report(tmp_path, body="new"), "pulse", root=root, when=datetime(2026, 10, 2, 9))
    archive(_report(tmp_path, body="s"), "sprint", root=root, when=datetime(2026, 10, 2, 9))
    found = entries_since(root, "pulse", datetime(2026, 10, 2, 8))
    assert [e["date"] for e in found] == ["2026-10-02"]


def test_backfill_parses_sprint_names_and_pulse_mtime(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    _report(out, "sprint-report-TEAM-sprint1-run115210-2026-09-24.html", body="1")
    _report(out, "sprint-report-TEAM-sprint1-run1501-2026-09-22.html", body="2")
    plain = _report(out, "sprint-report-TEAM-sprint1-2026-09-21.html", body="3")
    _report(out, "burndown-TEAM-sprint1-2026-09-21.html", body="ignored")
    pulse = _report(out, "daily_dashboard_report.html", body="pulse")
    stamp = datetime(2026, 10, 2, 9, 5).timestamp()
    os.utime(pulse, (stamp, stamp))
    os.utime(plain, (stamp, stamp))  # mtime on another day → falls back to noon

    root = tmp_path / "reports"
    assert backfill(out, root) == 4
    got = {(e["type"], e["date"], e["time"]) for e in load_manifest(root)}
    assert got == {
        ("sprint", "2026-09-24", "11:52"),
        ("sprint", "2026-09-22", "15:01"),
        ("sprint", "2026-09-21", "12:00"),
        ("pulse", "2026-10-02", "09:05"),
    }
    assert backfill(out, root) == 0


def test_prune_removes_old_reports(tmp_path):
    root = tmp_path / "reports"
    old, _ = archive(
        _report(tmp_path, body="old"), "pulse", root=root, when=datetime.now() - timedelta(days=100)
    )
    new, _ = archive(_report(tmp_path, body="new"), "pulse", root=root, when=datetime.now())

    assert prune(root, 90) == 1
    assert [e["id"] for e in load_manifest(root)] == [new["id"]]
    assert not (root / old["path"]).exists()
    assert not (root / old["path"]).parent.exists()
    assert prune(root, 0) == 0


def test_build_index_with_empty_archive(tmp_path):
    root = tmp_path / "reports"
    index = build_index(root)
    assert index.is_file()
    assert _embedded_data(root)["entries"] == []
