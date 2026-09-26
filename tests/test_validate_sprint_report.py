"""Tests for deterministic sprint-report validation."""

from pathlib import Path

from scripts.validate_sprint_report import validate_report


def _epic_progress_inner(*, rows: str) -> str:
    return f"<table><tbody>{rows}</tbody></table>"


def _report(
    *,
    expectation_end: str = "0",
    actual_end: str = "2026-09-22T16:00:00+10:00",
    remaining: str = "16",
    section_ids: list[str] | None = None,
    epic_rows: str | None = None,
    epic_count: int = 1,
) -> str:
    ids = section_ids or [
        "header",
        "at-a-glance",
        "calendar",
        "burn-up",
        "burn-down",
        "epic-progress",
        "event-ledger",
        "ticket-table",
        "methods",
    ]
    default_row = (
        '<tr data-epic="SEA-100" data-done="2" data-total="4" data-pct="50">'
        '<td><a href="https://example.atlassian.net/browse/SEA-100">SEA-100</a></td>'
        "</tr>"
    )
    sections = []
    for section_id in ids:
        content = ""
        if section_id == "epic-progress":
            if epic_rows is not False:
                rows_html = epic_rows if epic_rows is not None else default_row
                content = (
                    f'<section id="epic-progress" data-epic-count="{epic_count}" '
                    f'data-team-prefix="[TEAM]">'
                    f"{_epic_progress_inner(rows=rows_html)}</section>"
                )
                sections.append(content)
            continue
        elif section_id == "burn-up":
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
        if section_id != "epic-progress":
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
        "epic-progress",
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


def test_epic_progress_pct_must_match_done_total(tmp_path: Path):
    rows = (
        '<tr data-epic="SEA-200" data-done="1" data-total="3" data-pct="50">'
        '<td><a href="https://example.atlassian.net/browse/SEA-200">SEA-200</a></td></tr>'
    )
    path = _write_report(tmp_path, _report(epic_rows=rows))
    assert any("data-pct must equal" in error for error in validate_report(path))


def test_epic_progress_done_cannot_exceed_total(tmp_path: Path):
    rows = (
        '<tr data-epic="SEA-201" data-done="5" data-total="3" data-pct="100">'
        '<td><a href="https://example.atlassian.net/browse/SEA-201">SEA-201</a></td></tr>'
    )
    path = _write_report(tmp_path, _report(epic_rows=rows))
    assert any("data-done (5) exceeds data-total (3)" in error for error in validate_report(path))


def test_epic_progress_row_count_must_match_section_attr(tmp_path: Path):
    rows = (
        '<tr data-epic="SEA-202" data-done="0" data-total="2" data-pct="0">'
        '<td><a href="https://example.atlassian.net/browse/SEA-202">SEA-202</a></td></tr>'
    )
    path = _write_report(tmp_path, _report(epic_rows=rows, epic_count=2))
    assert any("data-epic-count is 2 but found 1" in error for error in validate_report(path))


def test_epic_progress_requires_team_prefix_attr(tmp_path: Path):
    rows = (
        '<tr data-epic="SEA-204" data-done="1" data-total="2" data-pct="50">'
        '<td><a href="https://example.atlassian.net/browse/SEA-204">SEA-204</a></td></tr>'
    )
    html = _report(epic_rows=rows).replace('data-team-prefix="[TEAM]"', "")
    path = _write_report(tmp_path, html)
    assert "epic-progress: missing data-team-prefix on section" in validate_report(path)


def test_epic_progress_zero_total_omits_pct(tmp_path: Path):
    rows = (
        '<tr data-epic="SEA-203" data-done="0" data-total="0" data-pct="0">'
        '<td><a href="https://example.atlassian.net/browse/SEA-203">SEA-203</a></td></tr>'
    )
    path = _write_report(tmp_path, _report(epic_rows=rows))
    assert any(
        "data-pct must be omitted when data-total is 0" in error for error in validate_report(path)
    )
