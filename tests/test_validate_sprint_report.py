"""Tests for deterministic sprint-report validation."""

from pathlib import Path

from scripts.validate_sprint_report import validate_report


def _report(
    *,
    expectation_end: str = "0",
    actual_end: str = "2026-09-22T16:00:00+10:00",
    remaining: str = "16",
    section_ids: list[str] | None = None,
) -> str:
    ids = section_ids or [
        "header",
        "at-a-glance",
        "calendar",
        "burn-up",
        "burn-down",
        "event-ledger",
        "ticket-table",
        "methods",
    ]
    sections = []
    for section_id in ids:
        content = ""
        if section_id == "burn-up":
            content = f"""
            <svg data-chart="burn-up" data-current-scope="26"
                 data-current-completed="10" data-remaining="{remaining}">
              <polyline data-series="total-scope" data-end-value="26"/>
              <polyline data-series="completed" data-end-value="10"/>
            </svg>
            """
        elif section_id == "burn-down":
            content = f"""
            <svg data-chart="burn-down" data-baseline="1"
                 data-as-of-timestamp="2026-09-22T16:25:00+10:00"
                 data-target-timestamp="2026-09-28T18:00:00+10:00">
              <polyline data-series="frozen-ideal" data-start-value="1"
                 data-end-value="0"
                 data-end-timestamp="2026-09-28T18:00:00+10:00"/>
              <polyline data-series="rolling-expectation"
                 data-end-value="{expectation_end}"
                 data-end-timestamp="2026-09-28T18:00:00+10:00"/>
              <polyline data-series="actual" data-end-value="16"
                 data-end-timestamp="{actual_end}"/>
            </svg>
            """
        sections.append(f'<section id="{section_id}">{content}</section>')
    return "<!doctype html><html><body>" + "".join(sections) + "</body></html>"


def _write_report(tmp_path: Path, html: str, *, name: str | None = None) -> Path:
    path = tmp_path / (name or "sprint-report-TEAM-sprint123-run162500-2026-09-22.html")
    path.write_text(html, encoding="utf-8")
    return path


def test_valid_report_passes(tmp_path: Path):
    path = _write_report(tmp_path, _report())
    assert validate_report(path) == []


def test_expectation_must_reach_zero_at_target(tmp_path: Path):
    path = _write_report(tmp_path, _report(expectation_end="16"))
    errors = validate_report(path)
    assert "rolling expectation: must end at 0, got 16" in errors


def test_actual_cannot_extend_after_as_of(tmp_path: Path):
    path = _write_report(
        tmp_path,
        _report(actual_end="2026-09-23T09:00:00+10:00"),
    )
    errors = validate_report(path)
    assert "actual segment 1: contains future data after as-of time" in errors


def test_requires_exact_section_order(tmp_path: Path):
    ids = [
        "header",
        "calendar",
        "at-a-glance",
        "burn-up",
        "burn-down",
        "event-ledger",
        "ticket-table",
        "methods",
    ]
    path = _write_report(tmp_path, _report(section_ids=ids))
    assert any(error.startswith("sections must be exactly") for error in validate_report(path))


def test_burnup_gap_must_reconcile(tmp_path: Path):
    path = _write_report(tmp_path, _report(remaining="17"))
    assert "burn-up: current scope minus completed must equal remaining" in validate_report(path)


def test_filename_requires_unique_run_time(tmp_path: Path):
    path = _write_report(
        tmp_path,
        _report(),
        name="sprint-report-TEAM-sprint123-2026-09-22.html",
    )
    assert any(error.startswith("filename must include") for error in validate_report(path))
