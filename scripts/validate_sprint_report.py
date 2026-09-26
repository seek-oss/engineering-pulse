#!/usr/bin/env python3
"""Validate structural and chart invariants in a generated sprint report."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from rich.console import Console

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
# Checked against agent-written text only; Jira data in table cells is skipped.
FORBIDDEN_EPIC_WORDS = ("confidence", "on track", "intervene")
UNIQUE_FILENAME = re.compile(
    r"^sprint-report-[A-Za-z0-9_-]+-sprint\d+-run\d{6}-\d{4}-\d{2}-\d{2}\.html$"
)


class SprintReportParser(HTMLParser):
    """Collect report sections, chart metadata, and epic-progress rows."""

    def __init__(self) -> None:
        super().__init__()
        self.section_ids: list[str] = []
        self.charts: dict[str, dict[str, object]] = {}
        self._current_chart: str | None = None
        self.epic_progress: dict[str, object] = {
            "attrs": {},
            "rows": [],
            "hrefs": [],
            "has_callout": False,
            "text": [],
        }
        self._in_epic_progress = False
        self._td_depth = 0

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key: value for key, value in attrs_list if value is not None}
        if tag == "section":
            section_id = attrs.get("id", "")
            self.section_ids.append(section_id)
            self._in_epic_progress = section_id == "epic-progress"
            if self._in_epic_progress:
                self.epic_progress["attrs"] = attrs
        elif self._in_epic_progress and tag == "td":
            self._td_depth += 1
        elif self._in_epic_progress and tag == "a" and "href" in attrs:
            hrefs = self.epic_progress["hrefs"]
            assert isinstance(hrefs, list)
            hrefs.append(attrs["href"])
        elif self._in_epic_progress and "epic-prefix-callout" in attrs.get("class", "").split():
            self.epic_progress["has_callout"] = True
        elif tag == "svg" and "data-chart" in attrs:
            chart_name = attrs["data-chart"]
            self._current_chart = chart_name
            self.charts[chart_name] = {"attrs": attrs, "series": []}
        elif tag in {"polyline", "path"} and self._current_chart and "data-series" in attrs:
            series = self.charts[self._current_chart]["series"]
            assert isinstance(series, list)
            series.append(attrs)
        elif tag == "tr" and self._in_epic_progress and "data-epic" in attrs:
            rows = self.epic_progress["rows"]
            assert isinstance(rows, list)
            rows.append(attrs)

    def handle_data(self, data: str) -> None:
        if self._in_epic_progress and self._td_depth == 0:
            text = self.epic_progress["text"]
            assert isinstance(text, list)
            text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg":
            self._current_chart = None
        elif tag == "td" and self._td_depth:
            self._td_depth -= 1
        elif tag == "section" and self._in_epic_progress:
            self._in_epic_progress = False
            self._td_depth = 0


def _number(attrs: dict[str, str], key: str, errors: list[str], label: str) -> float | None:
    value = attrs.get(key)
    try:
        return float(value) if value is not None else None
    except ValueError:
        errors.append(f"{label}: {key} must be numeric, got {value!r}")
        return None


def _timestamp(attrs: dict[str, str], key: str, errors: list[str], label: str) -> datetime | None:
    value = attrs.get(key)
    if value is None:
        errors.append(f"{label}: missing {key}")
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label}: {key} must be an ISO-8601 timestamp, got {value!r}")
        return None


def _series(
    chart: dict[str, object], name: str, errors: list[str], *, exactly_one: bool = True
) -> list[dict[str, str]]:
    all_series = chart["series"]
    assert isinstance(all_series, list)
    matches = [item for item in all_series if item.get("data-series") == name]
    if not matches:
        errors.append(f"missing {name!r} chart series")
    elif exactly_one and len(matches) != 1:
        errors.append(f"expected one {name!r} chart series, found {len(matches)}")
    return matches


def _validate_endpoint(
    attrs: dict[str, str],
    *,
    label: str,
    expected_end: float,
    target: datetime | None,
    errors: list[str],
) -> None:
    end_value = _number(attrs, "data-end-value", errors, label)
    if end_value is None:
        errors.append(f"{label}: missing data-end-value")
    elif end_value != expected_end:
        errors.append(f"{label}: must end at {expected_end:g}, got {end_value:g}")

    end_time = _timestamp(attrs, "data-end-timestamp", errors, label)
    if target is not None and end_time is not None and end_time != target:
        errors.append(f"{label}: endpoint timestamp must equal sprint target")


def _validate_burndown(chart: dict[str, object], errors: list[str]) -> None:
    attrs = chart["attrs"]
    assert isinstance(attrs, dict)
    target = _timestamp(attrs, "data-target-timestamp", errors, "burn-down")
    as_of = _timestamp(attrs, "data-as-of-timestamp", errors, "burn-down")
    baseline = _number(attrs, "data-baseline", errors, "burn-down")
    if baseline is None:
        errors.append("burn-down: missing data-baseline")

    ideal = _series(chart, "frozen-ideal", errors)
    if ideal:
        start_value = _number(ideal[0], "data-start-value", errors, "frozen ideal")
        if baseline is not None and start_value != baseline:
            errors.append("frozen ideal: data-start-value must equal burn-down baseline")
        _validate_endpoint(
            ideal[0], label="frozen ideal", expected_end=0, target=target, errors=errors
        )

    expectation = _series(chart, "rolling-expectation", errors)
    if expectation:
        _validate_endpoint(
            expectation[0],
            label="rolling expectation",
            expected_end=0,
            target=target,
            errors=errors,
        )

    actual = _series(chart, "actual", errors, exactly_one=False)
    for index, segment in enumerate(actual, start=1):
        end_time = _timestamp(segment, "data-end-timestamp", errors, f"actual segment {index}")
        if as_of is not None and end_time is not None and end_time > as_of:
            errors.append(f"actual segment {index}: contains future data after as-of time")


def _validate_burnup(chart: dict[str, object], errors: list[str]) -> None:
    attrs = chart["attrs"]
    assert isinstance(attrs, dict)
    current_scope = _number(attrs, "data-current-scope", errors, "burn-up")
    current_completed = _number(attrs, "data-current-completed", errors, "burn-up")
    remaining = _number(attrs, "data-remaining", errors, "burn-up")
    if None in {current_scope, current_completed, remaining}:
        errors.append("burn-up: missing current scope/completed/remaining metadata")
        return
    assert current_scope is not None
    assert current_completed is not None
    assert remaining is not None
    if current_scope - current_completed != remaining:
        errors.append("burn-up: current scope minus completed must equal remaining")

    scope_series = _series(chart, "total-scope", errors)
    completed_series = _series(chart, "completed", errors)
    if scope_series:
        end = _number(scope_series[0], "data-end-value", errors, "total scope")
        if end != current_scope:
            errors.append("total scope: endpoint must equal current scope")
    if completed_series:
        end = _number(completed_series[0], "data-end-value", errors, "completed")
        if end != current_completed:
            errors.append("completed: endpoint must equal current completed")


def _validate_epic_progress(epic_progress: dict[str, object], errors: list[str]) -> None:
    attrs = epic_progress["attrs"]
    rows = epic_progress["rows"]
    hrefs = epic_progress["hrefs"]
    text = epic_progress["text"]
    assert isinstance(attrs, dict)
    assert isinstance(rows, list)
    assert isinstance(hrefs, list)
    assert isinstance(text, list)

    team_prefix = attrs.get("data-team-prefix")
    if not team_prefix:
        errors.append("epic-progress: missing data-team-prefix on section")
    if "data-child-filter" in attrs and not attrs["data-child-filter"].strip():
        errors.append("epic-progress: data-child-filter must be non-empty when present")
    if not epic_progress["has_callout"]:
        errors.append("epic-progress: missing epic-prefix-callout scope line")

    section_text = " ".join(text)
    for word in FORBIDDEN_EPIC_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", section_text, re.IGNORECASE):
            errors.append(f"epic-progress: forbidden wording {word!r}")

    expected_count = attrs.get("data-epic-count")
    if expected_count is None:
        errors.append("epic-progress: missing data-epic-count on section")
    else:
        try:
            count = int(expected_count)
        except ValueError:
            errors.append(
                f"epic-progress: data-epic-count must be an integer, got {expected_count!r}"
            )
        else:
            if count != len(rows):
                errors.append(
                    f"epic-progress: data-epic-count is {count} but found {len(rows)} data row(s)"
                )

    seen_keys: set[str] = set()
    for index, row in enumerate(rows, start=1):
        label = f"epic-progress row {index}"
        key = row.get("data-epic")
        if not key:
            errors.append(f"{label}: missing data-epic")
            continue
        if key in seen_keys:
            errors.append(f"{label}: duplicate epic key {key!r}")
        seen_keys.add(key)

        done = _number(row, "data-done", errors, label)
        total = _number(row, "data-total", errors, label)
        if done is None or total is None:
            continue
        if done > total:
            errors.append(f"{label}: data-done ({done:g}) exceeds data-total ({total:g})")

        pct_raw = row.get("data-pct")
        if total == 0:
            if pct_raw is not None and pct_raw != "":
                errors.append(f"{label}: data-pct must be omitted when data-total is 0")
        elif pct_raw is None:
            errors.append(f"{label}: missing data-pct")
        else:
            pct = _number(row, "data-pct", errors, label)
            if pct is not None and round(100 * done / total) != int(pct):
                errors.append(
                    f"{label}: data-pct must equal round(100 * done / total), "
                    f"got {int(pct)} expected {round(100 * done / total)}"
                )

        if not any(href.endswith(f"/browse/{key}") for href in hrefs):
            errors.append(f"{label}: missing browse link for {key} in epic-progress")


def validate_report(path: Path) -> list[str]:
    """Return validation errors for a sprint-report HTML file."""
    errors: list[str] = []
    if not UNIQUE_FILENAME.fullmatch(path.name):
        errors.append(
            "filename must include a unique six-digit run time before the report date "
            "(...-runHHMMSS-YYYY-MM-DD.html)"
        )

    parser = SprintReportParser()
    parser.feed(path.read_text(encoding="utf-8"))
    if parser.section_ids != SECTION_IDS:
        errors.append(
            "sections must be exactly, in order: "
            + ", ".join(SECTION_IDS)
            + f"; found: {', '.join(parser.section_ids)}"
        )

    if "epic-progress" not in parser.section_ids:
        errors.append("missing epic-progress section")
    else:
        _validate_epic_progress(parser.epic_progress, errors)

    burnup = parser.charts.get("burn-up")
    burndown = parser.charts.get("burn-down")
    if burnup is None:
        errors.append("missing machine-readable burn-up SVG (data-chart='burn-up')")
    else:
        _validate_burnup(burnup, errors)
    if burndown is None:
        errors.append("missing machine-readable burn-down SVG (data-chart='burn-down')")
    else:
        _validate_burndown(burndown, errors)
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    errors = validate_report(args.report)
    console = Console()
    if errors:
        console.print(f"[red]Sprint report validation failed ({len(errors)} error(s)):[/red]")
        for error in errors:
            console.print(f"[red]• {error}[/red]")
        raise SystemExit(1)
    console.print("[green]Sprint report validation passed.[/green]")


if __name__ == "__main__":
    main()
