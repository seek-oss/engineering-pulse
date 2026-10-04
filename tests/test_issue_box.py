"""Tests for scripts/issue_box.py — the red problems box and the fallback report."""

from datetime import datetime

from scripts.issue_box import (
    MARKER,
    auth_link,
    fallback_report,
    inject,
    render_issue_box,
    rerun_link,
)

LOGIN = {"kind": "mcp_login", "agent": "cursor", "server": "GitHub"}
PAGE = "<html><head><title>T</title></head><body class='x'><h1>Report</h1></body></html>"


def _issue(message="Something failed", fix=None, source="github"):
    return {"source": source, "message": message, "fix": fix}


class TestRenderIssueBox:
    def test_no_issues_no_box(self):
        assert render_issue_box([], "pulse") == ""

    def test_heading_counts(self):
        assert "1 problem in this run" in render_issue_box([_issue()], "pulse")
        assert "2 problems in this run" in render_issue_box([_issue("a"), _issue("b")], "pulse")

    def test_escapes_text(self):
        box = render_issue_box([_issue("<script>alert(1)</script>", source="<b>")], "pulse")
        assert "<script>" not in box
        assert "&lt;script&gt;" in box

    def test_sign_in_button_only_on_fixable_rows(self):
        box = render_issue_box([_issue("needs sign-in", LOGIN), _issue("no fix")], "pulse")
        assert box.count("Sign in to GitHub") == 1
        assert "engineering-pulse://auth?agent=cursor&amp;server=GitHub" in box

    def test_rerun_when_fixable(self):
        box = render_issue_box([_issue("x", LOGIN)], "sprint")
        assert "engineering-pulse://run?type=sprint" in box
        assert "After signing in: <a" in box
        assert ">Re-run this report</a></p>" in box
        assert "opened on the Mac" in box

    def test_source_labels(self):
        box = render_issue_box(
            [_issue(source="github"), _issue(source="atlassian"), _issue(source="custom")],
            "pulse",
        )
        assert "<strong>GitHub:</strong>" in box
        assert "<strong>Jira:</strong>" in box
        assert "<strong>Custom:</strong>" in box
        assert "Github:" not in box

    def test_fixable_rows_come_first(self):
        box = render_issue_box(
            [
                _issue("no dashboards", source="datadog"),
                _issue("sign in", LOGIN),
                _issue("third problem"),
            ],
            "pulse",
        )
        assert box.index("sign in") < box.index("no dashboards") < box.index("third problem")

    def test_no_rerun_without_fixable_issue(self):
        box = render_issue_box([_issue()], "pulse")
        assert "Re-run" not in box
        assert "engineering-pulse://" not in box

    def test_no_rerun_for_compare(self):
        box = render_issue_box([_issue("x", LOGIN)], "compare")
        assert "Re-run" not in box
        assert "Sign in to GitHub" in box

    def test_server_names_are_url_encoded(self):
        assert auth_link("claude", "acme github&x") == (
            "engineering-pulse://auth?agent=claude&server=acme+github%26x"
        )
        assert rerun_link("pulse") == "engineering-pulse://run?type=pulse"


class TestInject:
    def test_after_body_open(self):
        out = inject(PAGE, render_issue_box([_issue()], "pulse"))
        assert out.index(MARKER) > out.index("<body")
        assert out.index(MARKER) < out.index("<h1>")

    def test_idempotent(self):
        box = render_issue_box([_issue()], "pulse")
        once = inject(PAGE, box)
        assert inject(once, box) == once
        assert once.count(MARKER) == 1

    def test_replaces_old_box(self):
        old = inject(PAGE, render_issue_box([_issue("old problem")], "pulse"))
        new = inject(old, render_issue_box([_issue("new problem")], "pulse"))
        assert "old problem" not in new
        assert "new problem" in new

    def test_empty_box_removes_old_box(self):
        old = inject(PAGE, render_issue_box([_issue()], "pulse"))
        assert inject(old, "") == PAGE

    def test_no_body_tag_prepends(self):
        assert inject("<p>x</p>", "<div data-ep-issues>b</div><!--/ep-issues-->").startswith(
            "<div data-ep-issues>"
        )


class TestFallbackReport:
    def test_frame_with_box(self):
        page = fallback_report("sprint", [_issue("Jira down")], datetime(2026, 10, 4, 9, 30))
        assert "<title>Sprint report — 2026-10-04 (incomplete)</title>" in page
        assert "Jira down" in page
        assert "No sections could be generated this run." in page
        assert page.count(MARKER) == 1

    def test_frame_without_issues(self):
        page = fallback_report("compare", [])
        assert MARKER not in page
        assert "Comparison" in page
