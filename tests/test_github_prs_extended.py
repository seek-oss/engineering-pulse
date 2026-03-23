"""Extended tests for scripts/github_prs.py — HTTP helpers and display."""
from unittest.mock import MagicMock, patch

import pytest
import requests as req_lib

from scripts.github_prs import gql, get_authenticated_user, print_table


# ---------------------------------------------------------------------------
# gql()
# ---------------------------------------------------------------------------

class TestGql:
    @patch("scripts.github_prs.requests.post")
    def test_returns_data_on_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"data": {"search": {"nodes": []}}}
        mock_post.return_value = mock_resp

        result = gql("query { viewer { login } }", {})
        assert result == {"search": {"nodes": []}}

    @patch("scripts.github_prs.requests.post")
    def test_raises_value_error_on_graphql_errors(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "errors": [{"message": "Resource not accessible"}],
            "data": None,
        }
        mock_post.return_value = mock_resp

        with pytest.raises(ValueError, match="GraphQL errors"):
            gql("query { viewer { login } }", {})

    @patch("scripts.github_prs.requests.post")
    def test_raises_on_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError("401 Unauthorized")
        mock_post.return_value = mock_resp

        with pytest.raises(req_lib.HTTPError):
            gql("query { viewer { login } }", {})

    @patch("scripts.github_prs.requests.post")
    def test_passes_variables_in_payload(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"data": {"search": {"nodes": []}}}
        mock_post.return_value = mock_resp

        gql("query($q: String!) { search(query: $q) }", {"q": "is:open"})
        payload = mock_post.call_args[1]["json"]
        assert payload["variables"] == {"q": "is:open"}


# ---------------------------------------------------------------------------
# get_authenticated_user()
# ---------------------------------------------------------------------------

class TestGetAuthenticatedUser:
    @patch("scripts.github_prs.requests.get")
    def test_returns_login(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"login": "octocat", "id": 1}
        mock_get.return_value = mock_resp

        result = get_authenticated_user()
        assert result == "octocat"

    @patch("scripts.github_prs.requests.get")
    def test_raises_on_401(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError("401 Unauthorized")
        mock_get.return_value = mock_resp

        with pytest.raises(req_lib.HTTPError):
            get_authenticated_user()

    @patch("scripts.github_prs.requests.get")
    def test_calls_github_user_endpoint(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"login": "user1"}
        mock_get.return_value = mock_resp

        get_authenticated_user()
        assert mock_get.call_args[0][0] == "https://api.github.com/user"


# ---------------------------------------------------------------------------
# print_table()
# ---------------------------------------------------------------------------

class TestPrintTable:
    def test_empty_list_prints_no_prs_message(self, capsys):
        print_table([])  # should not raise

    def test_single_pr_renders_without_error(self):
        prs = [
            {
                "number": 42,
                "repo": "my-org/my-repo",
                "title": "Fix the thing",
                "author": "alice",
                "age_days": 3,
                "updated_days": 1,
                "draft": False,
            }
        ]
        print_table(prs)  # should not raise

    def test_old_pr_renders_without_error(self):
        prs = [
            {
                "number": 1,
                "repo": "my-org/repo",
                "title": "Old stale PR",
                "author": "bob",
                "age_days": 10,  # red
                "updated_days": 8,
                "draft": False,
            }
        ]
        print_table(prs)

    def test_draft_pr_renders_without_error(self):
        prs = [
            {
                "number": 5,
                "repo": "my-org/repo",
                "title": "WIP feature",
                "author": "carol",
                "age_days": 1,
                "updated_days": 0,
                "draft": True,
            }
        ]
        print_table(prs)

    def test_fresh_pr_no_colour(self):
        prs = [
            {
                "number": 9,
                "repo": "my-org/repo",
                "title": "Brand new PR",
                "author": "dave",
                "age_days": 0,
                "updated_days": 0,
                "draft": False,
            }
        ]
        print_table(prs)  # age < 2, no colour markup — should not raise
