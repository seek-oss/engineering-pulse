from scripts.render_dx_build_success_html import render_html, render_pulse_section


def test_render_contains_chart_and_overall():
    payload = {
        "meta": {
            "team_name": "Example Team",
            "period_label": "Last 3 months",
            "contributors": 17,
            "overall_pct": 87.27,
        },
        "rows": [
            {
                "week_start": "2026-10-19 00:00:00+00",
                "successful_builds": 96,
                "total_builds": 110,
                "success_rate_pct": 87.27,
            },
            {
                "week_start": "2026-10-12 00:00:00+00",
                "successful_builds": 75,
                "total_builds": 92,
                "success_rate_pct": 81.52,
            },
        ],
    }
    html = render_html(payload)
    assert "Build success rate" in html
    assert "87.27" in html
    assert "linearGradient" in html
    assert "stroke-dasharray" in html
    assert "Example Team" in html
    assert "17" in html


def test_pulse_section_embeds_chart():
    payload = {
        "meta": {"team_name": "Example Team", "period_label": "Last 3 months", "overall_pct": 90.0},
        "rows": [
            {
                "week_start": "2026-10-19",
                "successful_builds": 9,
                "total_builds": 10,
                "success_rate_pct": 90.0,
            },
        ],
    }
    html = render_pulse_section("Part B — Build success rate", payload)
    assert "section-title" in html
    assert "dx-build-success-embed" in html
    assert "linearGradient" in html


def test_pooled_overall_from_rows():
    payload = {
        "meta": {"team": "T"},
        "rows": [
            {
                "week_start": "2026-10-01",
                "successful_builds": 80,
                "total_builds": 100,
                "success_rate_pct": 80.0,
            },
            {
                "week_start": "2026-10-08",
                "successful_builds": 18,
                "total_builds": 20,
                "success_rate_pct": 90.0,
            },
        ],
    }
    html = render_html(payload)
    assert "81.67" in html or "81.66" in html
