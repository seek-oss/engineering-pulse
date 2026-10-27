from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts import dx_studio


def test_apply_sql_template():
    sql = "INTERVAL '__PERIOD__' AND ILIKE '__TEAM_ILIKE__'"
    out = dx_studio.apply_sql_template(sql, period="3 months", team="Example Team")
    assert "INTERVAL '3 months'" in out
    assert "ILIKE '%Example Team%'" in out


def test_apply_sql_template_rejects_bad_period():
    with pytest.raises(SystemExit):
        dx_studio.apply_sql_template("x", period="1 year", team="A")


def test_pooled_overall_pct():
    rows = [
        {"successful_builds": 90, "total_builds": 100},
        {"successful_builds": 8, "total_builds": 10},
    ]
    assert dx_studio.pooled_overall_pct(rows) == pytest.approx(89.09, abs=0.01)


@patch("scripts.dx_studio.requests.post")
@patch("scripts.dx_studio.requests.get")
def test_execute_query_polls(mock_get, mock_post):
    mock_post.return_value = MagicMock(
        ok=True,
        json=lambda: {"ok": True, "query_run": {"id": "run1"}},
        raise_for_status=lambda: None,
    )

    def get_side_effect(url, **kwargs):
        resp = MagicMock(ok=True, raise_for_status=lambda: None, headers={})
        if "info" in url:
            resp.json.return_value = {"query_run": {"status": "succeeded"}}
        else:
            resp.json.return_value = {
                "ok": True,
                "results": {"columns": ["a"], "rows": [[1]]},
            }
        return resp

    mock_get.side_effect = get_side_effect
    result = dx_studio.execute_query("tok", "SELECT 1")
    assert result["columns"] == ["a"]


def test_sql_file_placeholders():
    path = (
        Path(__file__).resolve().parents[1]
        / "skills/dx-build-success/references/build-success-rate.sql"
    )
    text = path.read_text(encoding="utf-8")
    assert "__PERIOD__" in text
    assert "__TEAM_ILIKE__" in text
