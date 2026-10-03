"""Tests for scripts/report_snapshot.py."""

from scripts.report_snapshot import extract, pulse_snapshot, sprint_snapshot

PULSE_HTML = """<!doctype html><html><body><div class="container">
<div class="section-title">Part A — Service Health</div>
<div class="tile-row">
  <div class="tile tile-red"><div class="label">Error rate</div><div class="big-number">4.2%</div></div>
  <div class="tile tile-green"><div class="label">Uptime</div><div class="big-number">99.9%</div></div>
</div>
<div class="section-title">Part B — PR Review Queue (1 open)</div>
<table class="pr-table">
  <thead><tr><th>Repo</th><th>Title</th><th>Author</th><th>Age</th></tr></thead>
  <tbody><tr><td>widget-api</td><td><a href="https://github.example/acme/widget-api/pull/7">Add caching</a>
    <span class="draft-tag">(draft)</span></td><td>alex-doe</td><td><span class="age-red">6d</span></td></tr></tbody>
</table>
<div class="section-title">Part C — Stakeholder Pulse</div>
<div class="extra-card"><div class="extra-title">Jamie Rivers</div><div class="extra-body"><ul>
<li><strong>Themes:</strong> Launch plan &amp; <em>timeline</em>.</li>
<li><strong>Top links:</strong> <a href="https://chat.example/archives/C1/p1">#launch thread</a></li>
</ul></div></div>
</div></body></html>"""

SPRINT_HTML = """<!doctype html><html><body>
<svg data-current-scope="5" data-current-completed="2" data-remaining="3" data-baseline="4"></svg>
<section id="ticket-table"><h2>Tickets (2)</h2><table>
<thead><tr><th>Key</th><th>Status</th><th>Epic</th><th>Summary</th><th>Assignee</th></tr></thead>
<tbody>
<tr><td><a href="https://jira.example/browse/ABC-1">ABC-1</a></td><td><span class="pill">Done</span></td>
  <td><a href="https://jira.example/browse/ABC-9">ABC-9</a></td><td>Build widget</td><td>Sam Lee</td></tr>
<tr><td><a href="https://jira.example/browse/ABC-2">ABC-2</a></td><td><span class="pill">In Progress</span></td>
  <td><a href="https://jira.example/browse/ABC-9">ABC-9</a></td><td>Test widget</td><td>—</td></tr>
</tbody></table></section></body></html>"""


class TestPulse:
    def test_metrics_carry_value_and_band(self):
        snap = pulse_snapshot(PULSE_HTML)
        assert snap["metrics"] == {
            "Service Health / Error rate": {"value": "4.2%", "band": "red"},
            "Service Health / Uptime": {"value": "99.9%", "band": "green"},
        }

    def test_prs_keyed_by_url(self):
        snap = pulse_snapshot(PULSE_HTML)
        assert snap["prs"] == {
            "https://github.example/acme/widget-api/pull/7": {
                "repo": "widget-api",
                "title": "Add caching",
                "author": "alex-doe",
                "age": "6d",
            }
        }

    def test_stakeholder_bullets_and_links(self):
        card = pulse_snapshot(PULSE_HTML)["stakeholders"]["Jamie Rivers"]
        assert card["bullets"][0] == "Themes: Launch plan & timeline."
        assert card["links"] == {"https://chat.example/archives/C1/p1": "#launch thread"}


class TestSprint:
    def test_totals_and_tickets(self):
        snap = sprint_snapshot(SPRINT_HTML)
        assert snap["totals"] == {"scope": 5, "completed": 2, "remaining": 3, "baseline": 4}
        assert snap["tickets"]["ABC-1"] == {
            "status": "Done",
            "summary": "Build widget",
            "assignee": "Sam Lee",
            "epic": "ABC-9",
        }
        assert snap["tickets"]["ABC-2"]["status"] == "In Progress"


class TestExtract:
    def test_returns_none_for_unknown_type_or_empty_report(self):
        assert extract(PULSE_HTML, "compare") is None
        assert extract("<html><body>old format</body></html>", "sprint") is None

    def test_returns_snapshot(self):
        assert extract(SPRINT_HTML, "sprint")["totals"]["scope"] == 5
