"""Tests for deterministic sprint-report validation."""

from pathlib import Path

from scripts.validate_sprint_report import validate_report

SECTION_IDS = [
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
CALLOUT = (
    '<div class="epic-prefix-callout">Includes epics whose summary starts with [TEAM]; '
    "progress counts all standard-level children.</div>"
)


def _epic_row(
    key: str, done: int, total: int, pct: int | None, *, link: bool = True, summary: str = ""
) -> str:
    pct_attr = "" if pct is None else f' data-pct="{pct}"'
    cell = f'<a href="https://example.atlassian.net/browse/{key}">{key}</a>' if link else key
    return (
        f'<tr data-epic="{key}" data-done="{done}" data-total="{total}"{pct_attr}>'
        f"<td>{cell}</td><td>{summary}</td></tr>"
    )


def _epic_section(
    *,
    rows: str,
    count: int,
    attrs: str = 'data-team-prefix="[TEAM]"',
    callout: str = CALLOUT,
    extra: str = "",
) -> str:
    return (
        f'<section id="epic-progress" data-epic-count="{count}" {attrs}>'
        f"<h2>Epic progress</h2>{callout}<table><tbody>{rows}</tbody></table>{extra}</section>"
    )


def _report(
    *,
    expectation_end: str = "0",
    actual_end: str = "2026-09-22T16:00:00+10:00",
    remaining: str = "16",
    section_ids: list[str] | None = None,
    epic_section: str | None = None,
) -> str:
    sections = []
    for section_id in section_ids or SECTION_IDS:
        if section_id == "epic-progress":
            sections.append(
                epic_section or _epic_section(rows=_epic_row("SEA-100", 2, 4, 50), count=1)
            )
            continue
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
        elif section_id == "ticket-table":
            content = '<a href="https://example.atlassian.net/browse/SEA-999">SEA-999</a>'
        sections.append(f'<section id="{section_id}">{content}</section>')
    return "<!doctype html><html><body>" + "".join(sections) + "</body></html>"


def _write_report(tmp_path: Path, html: str, *, name: str | None = None) -> Path:
    path = tmp_path / (name or "sprint-report-TEAM-sprint123-run162500-2026-09-22.html")
    path.write_text(html, encoding="utf-8")
    return path


def _errors(tmp_path: Path, **kwargs) -> list[str]:
    return validate_report(_write_report(tmp_path, _report(**kwargs)))


def test_valid_report_passes(tmp_path: Path):
    assert _errors(tmp_path) == []


def test_expectation_must_reach_zero_at_target(tmp_path: Path):
    assert "rolling expectation: must end at 0, got 16" in _errors(tmp_path, expectation_end="16")


def test_actual_cannot_extend_after_as_of(tmp_path: Path):
    errors = _errors(tmp_path, actual_end="2026-09-23T09:00:00+10:00")
    assert "actual segment 1: contains future data after as-of time" in errors


def test_requires_exact_section_order(tmp_path: Path):
    ids = SECTION_IDS.copy()
    ids[1], ids[2] = ids[2], ids[1]
    assert any(e.startswith("sections must be exactly") for e in _errors(tmp_path, section_ids=ids))


def test_burnup_gap_must_reconcile(tmp_path: Path):
    errors = _errors(tmp_path, remaining="17")
    assert "burn-up: current scope minus completed must equal remaining" in errors


def test_filename_requires_unique_run_time(tmp_path: Path):
    path = _write_report(tmp_path, _report(), name="sprint-report-TEAM-sprint123-2026-09-22.html")
    assert any(error.startswith("filename must include") for error in validate_report(path))


def test_missing_epic_progress_section(tmp_path: Path):
    ids = [s for s in SECTION_IDS if s != "epic-progress"]
    assert "missing epic-progress section" in _errors(tmp_path, section_ids=ids)


def test_epic_progress_pct_must_match_done_total(tmp_path: Path):
    section = _epic_section(rows=_epic_row("SEA-200", 1, 3, 50), count=1)
    assert any("data-pct must equal" in e for e in _errors(tmp_path, epic_section=section))


def test_epic_progress_pct_required_when_total_positive(tmp_path: Path):
    section = _epic_section(rows=_epic_row("SEA-205", 1, 3, None), count=1)
    assert "epic-progress row 1: missing data-pct" in _errors(tmp_path, epic_section=section)


def test_epic_progress_done_cannot_exceed_total(tmp_path: Path):
    section = _epic_section(rows=_epic_row("SEA-201", 5, 3, 100), count=1)
    errors = _errors(tmp_path, epic_section=section)
    assert any("data-done (5) exceeds data-total (3)" in e for e in errors)


def test_epic_progress_row_count_must_match_section_attr(tmp_path: Path):
    section = _epic_section(rows=_epic_row("SEA-202", 0, 2, 0), count=2)
    errors = _errors(tmp_path, epic_section=section)
    assert any("data-epic-count is 2 but found 1" in e for e in errors)


def test_epic_progress_rejects_duplicate_epic(tmp_path: Path):
    rows = _epic_row("SEA-206", 1, 2, 50) + _epic_row("SEA-206", 1, 2, 50)
    section = _epic_section(rows=rows, count=2)
    errors = _errors(tmp_path, epic_section=section)
    assert "epic-progress row 2: duplicate epic key 'SEA-206'" in errors


def test_epic_progress_requires_team_prefix_attr(tmp_path: Path):
    section = _epic_section(rows=_epic_row("SEA-204", 1, 2, 50), count=1, attrs="")
    errors = _errors(tmp_path, epic_section=section)
    assert "epic-progress: missing data-team-prefix on section" in errors


def test_epic_progress_child_filter_must_be_non_empty(tmp_path: Path):
    attrs = 'data-team-prefix="[TEAM]" data-child-filter=" "'
    section = _epic_section(rows=_epic_row("SEA-207", 1, 2, 50), count=1, attrs=attrs)
    errors = _errors(tmp_path, epic_section=section)
    assert "epic-progress: data-child-filter must be non-empty when present" in errors


def test_epic_progress_child_filter_accepted(tmp_path: Path):
    attrs = 'data-team-prefix="[TEAM]" data-child-filter="[TEAM]"'
    section = _epic_section(rows=_epic_row("SEA-208", 1, 2, 50), count=1, attrs=attrs)
    assert _errors(tmp_path, epic_section=section) == []


def test_epic_progress_zero_total_omits_pct(tmp_path: Path):
    section = _epic_section(rows=_epic_row("SEA-203", 0, 0, 0), count=1)
    errors = _errors(tmp_path, epic_section=section)
    assert any("data-pct must be omitted when data-total is 0" in e for e in errors)


def test_epic_progress_zero_total_without_pct_passes(tmp_path: Path):
    section = _epic_section(rows=_epic_row("SEA-209", 0, 0, None), count=1)
    assert _errors(tmp_path, epic_section=section) == []


def test_epic_progress_link_must_be_inside_section(tmp_path: Path):
    section = _epic_section(rows=_epic_row("SEA-999", 1, 2, 50, link=False), count=1)
    errors = _errors(tmp_path, epic_section=section)
    assert "epic-progress row 1: missing browse link for SEA-999 in epic-progress" in errors


def test_epic_progress_requires_callout(tmp_path: Path):
    section = _epic_section(rows=_epic_row("SEA-210", 1, 2, 50), count=1, callout="")
    errors = _errors(tmp_path, epic_section=section)
    assert "epic-progress: missing epic-prefix-callout scope line" in errors


def test_epic_progress_rejects_forecast_wording(tmp_path: Path):
    section = _epic_section(
        rows=_epic_row("SEA-211", 1, 2, 50), count=1, extra="<p>Delivery looks on track.</p>"
    )
    errors = _errors(tmp_path, epic_section=section)
    assert "epic-progress: forbidden wording 'on track'" in errors


def test_epic_progress_ignores_forbidden_words_in_jira_data(tmp_path: Path):
    rows = _epic_row("SEA-212", 1, 2, 50, summary="Get onboarding back on track") + _epic_row(
        "SEA-213", 0, 1, 0, summary="Intervene on stale confidence scores"
    )
    section = _epic_section(rows=rows, count=2)
    assert _errors(tmp_path, epic_section=section) == []


def test_epic_progress_matches_whole_words_only(tmp_path: Path):
    section = _epic_section(
        rows=_epic_row("SEA-214", 1, 2, 50), count=1, extra="<p>Confidential tickets excluded.</p>"
    )
    assert _errors(tmp_path, epic_section=section) == []
