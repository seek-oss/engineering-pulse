"""Tests for scripts/github_prs.py — GitHub MCP input, team config, and the CLI entry point."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from scripts import github_prs
from scripts.github_prs import format_rest_pr, load_mcp_results, main, team_spec


def _iso(days_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _item(number=1, repo="acme-corp/widgets", author="alice", age=3, updated=1, **extra):
    """A GitHub MCP search_pull_requests item (REST search shape)."""
    item = {
        "number": number,
        "title": f"Change {number}",
        "html_url": f"https://github.com/{repo}/pull/{number}",
        "repository_url": f"https://api.github.com/repos/{repo}",
        "user": {"login": author, "type": "User"},
        "created_at": _iso(age),
        "updated_at": _iso(updated),
        "draft": False,
        "labels": [],
    }
    item.update(extra)
    return item


def _write(tmp_path, payload):
    path = tmp_path / "github_mcp_prs.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# team_spec
# ---------------------------------------------------------------------------


class TestTeamSpec:
    def test_org_slash_team(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TEAM", "acme-corp/platform")
        monkeypatch.delenv("GITHUB_ORG", raising=False)
        assert team_spec() == ("acme-corp", "platform")

    def test_org_slash_team_ignores_legacy_org(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TEAM", "acme-corp/platform")
        monkeypatch.setenv("GITHUB_ORG", "other-org")
        assert team_spec() == ("acme-corp", "platform")

    def test_legacy_org_plus_team(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TEAM", "platform")
        monkeypatch.setenv("GITHUB_ORG", "acme-corp")
        assert team_spec() == ("acme-corp", "platform")

    def test_bare_team_without_org_is_none(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TEAM", "platform")
        monkeypatch.delenv("GITHUB_ORG", raising=False)
        assert team_spec() is None

    @pytest.mark.parametrize("value", ["", "   ", "acme-corp/", "/platform"])
    def test_unset_or_incomplete_is_none(self, monkeypatch, value):
        monkeypatch.setenv("GITHUB_TEAM", value)
        monkeypatch.delenv("GITHUB_ORG", raising=False)
        assert team_spec() is None

    @patch("scripts.github_prs.graphql_search_all", return_value=[])
    def test_team_query_uses_org_slash_team(self, mock_search, monkeypatch):
        monkeypatch.setenv("GITHUB_TEAM", "acme-corp/platform")
        github_prs.fetch_review_prs("alice")
        queries = [call.args[0] for call in mock_search.call_args_list]
        assert queries[1] == "is:open is:pr team-review-requested:acme-corp/platform"

    @patch("scripts.github_prs.graphql_search_all", return_value=[])
    def test_team_query_skipped_without_team(self, mock_search, monkeypatch):
        monkeypatch.setenv("GITHUB_TEAM", "")
        github_prs.fetch_review_prs("alice")
        assert mock_search.call_count == 1


# ---------------------------------------------------------------------------
# format_rest_pr
# ---------------------------------------------------------------------------


class TestFormatRestPr:
    def test_fields_match_graphql_shape(self):
        pr = format_rest_pr(_item(number=42, age=5, updated=2, labels=[{"name": "bug"}]))
        assert pr == {
            "number": 42,
            "title": "Change 42",
            "repo": "acme-corp/widgets",
            "author": "alice",
            "age_days": 5,
            "updated_days": 2,
            "url": "https://github.com/acme-corp/widgets/pull/42",
            "labels": ["bug"],
            "draft": False,
        }

    def test_draft_flag(self):
        assert format_rest_pr(_item(draft=True))["draft"] is True

    def test_missing_user_is_unknown(self):
        assert format_rest_pr(_item(user=None))["author"] == "unknown"

    def test_missing_updated_at_uses_created_at(self):
        item = _item(age=4)
        del item["updated_at"]
        assert format_rest_pr(item)["updated_days"] == 4

    def test_missing_optional_fields(self):
        item = _item()
        for key in ("labels", "draft", "repository_url"):
            del item[key]
        pr = format_rest_pr(item)
        assert pr["labels"] == []
        assert pr["draft"] is False
        assert pr["repo"] == ""


# ---------------------------------------------------------------------------
# load_mcp_results
# ---------------------------------------------------------------------------


class TestLoadMcpResults:
    def test_merges_and_dedupes_user_and_team_searches(self, tmp_path):
        shared = _item(number=1, age=3)
        path = _write(
            tmp_path,
            {
                "username": "alice",
                "results": [
                    {"total_count": 2, "items": [shared, _item(number=2, age=1)]},
                    {"total_count": 2, "items": [shared, _item(number=3, age=9)]},
                ],
            },
        )
        username, prs = load_mcp_results(path)
        assert username == "alice"
        assert [p["number"] for p in prs] == [2, 1, 3]

    def test_drops_renovate_prs(self, tmp_path):
        items = [_item(number=1, author="renovate[bot]"), _item(number=2, author="Renovate")]
        items.append(_item(number=3, author="bob"))
        _, prs = load_mcp_results(_write(tmp_path, {"results": [{"items": items}]}))
        assert [p["author"] for p in prs] == ["bob"]

    def test_accepts_bare_item_lists(self, tmp_path):
        path = _write(tmp_path, [[_item(number=1)], {"items": [_item(number=2)]}])
        username, prs = load_mcp_results(path)
        assert username == ""
        assert sorted(p["number"] for p in prs) == [1, 2]

    def test_skips_non_pr_entries(self, tmp_path):
        items = [None, "oops", {"number": 9}, _item(number=1)]
        _, prs = load_mcp_results(_write(tmp_path, {"results": [{"items": items}, None]}))
        assert [p["number"] for p in prs] == [1]

    def test_empty_results(self, tmp_path):
        assert load_mcp_results(_write(tmp_path, {"username": "alice", "results": []})) == (
            "alice",
            [],
        )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_from_mcp_writes_output(self, tmp_path, monkeypatch):
        monkeypatch.setattr(github_prs, "GITHUB_TOKEN", "")
        src = _write(tmp_path, {"username": "alice", "results": [{"items": [_item()]}]})
        out = tmp_path / "out" / "github_prs.json"
        assert main(["--from-mcp", str(src), "--out", str(out)]) == 0
        data = json.loads(out.read_text())
        assert data["username"] == "alice"
        assert data["prs"][0]["repo"] == "acme-corp/widgets"

    @patch("scripts.github_prs.get_authenticated_user")
    def test_from_mcp_does_not_call_github_api(self, mock_user, tmp_path, monkeypatch):
        monkeypatch.setattr(github_prs, "GITHUB_TOKEN", "a-token")
        src = _write(tmp_path, {"results": []})
        assert main(["--from-mcp", str(src), "--out", str(tmp_path / "o.json")]) == 0
        mock_user.assert_not_called()

    def test_from_mcp_bad_file_fails_cleanly(self, tmp_path, monkeypatch):
        out = tmp_path / "o.json"
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        assert main(["--from-mcp", str(bad), "--out", str(out)]) == 1
        assert main(["--from-mcp", str(tmp_path / "missing.json"), "--out", str(out)]) == 1
        assert not out.exists()

    def test_no_token_and_no_mcp_explains_both_options(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(github_prs, "GITHUB_TOKEN", "")
        out = tmp_path / "o.json"
        assert main(["--out", str(out)]) == 2
        text = capsys.readouterr().out
        assert "--from-mcp" in text
        assert "GITHUB_TOKEN" in text
        assert not out.exists()

    @patch("scripts.github_prs.fetch_review_prs")
    @patch("scripts.github_prs.get_authenticated_user", return_value="alice")
    def test_token_path_still_works(self, _user, mock_fetch, tmp_path, monkeypatch):
        monkeypatch.setattr(github_prs, "GITHUB_TOKEN", "a-token")
        mock_fetch.return_value = [format_rest_pr(_item())]
        out = tmp_path / "o.json"
        assert main(["--out", str(out)]) == 0
        mock_fetch.assert_called_once_with("alice")
        assert json.loads(out.read_text())["username"] == "alice"

    def test_import_without_token_does_not_exit(self, monkeypatch):
        import importlib

        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
        reloaded = importlib.reload(github_prs)
        try:
            assert reloaded.GITHUB_TOKEN == ""
        finally:
            monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
            importlib.reload(github_prs)
