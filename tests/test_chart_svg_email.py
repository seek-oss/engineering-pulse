"""Tests for sprint-report SVG → PNG email preparation."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.chart_svg_email import (
    is_sprint_report_html_path,
    prepare_sprint_report_html_for_email,
    replace_svgs_with_png_images,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = next(ROOT.glob("output/sprint-report-*-sprint*-2026-09-21.html"), None)


def test_is_sprint_report_html_path() -> None:
    assert is_sprint_report_html_path("output/sprint-report-team-sprint1-2026-09-22.html")
    assert not is_sprint_report_html_path("output/daily_dashboard_report.html")


def test_replace_svgs_with_png_images_sample_report() -> None:
    if SAMPLE is None or not SAMPLE.is_file():
        return
    html = SAMPLE.read_text(encoding="utf-8")
    assert "<svg" in html
    out, count = replace_svgs_with_png_images(html)
    assert count == 2
    assert "<svg" not in out
    assert 'src="data:image/png;base64,' in out
    assert out.count("data:image/png;base64,") == 2


def test_prepare_preserves_non_svg_sections() -> None:
    if SAMPLE is None or not SAMPLE.is_file():
        return
    html = SAMPLE.read_text(encoding="utf-8")
    out = prepare_sprint_report_html_for_email(html)
    assert "Event ledger" in out
    assert "FY27 Q1 Sprint 6" in out
