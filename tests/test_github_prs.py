"""Tests for scripts/github_prs.py — pure logic functions."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from scripts.github_prs import format_pr, fetch_review_prs, graphql_search_all, MAX_PAGES


def _make_node(
    number=1,
    title="Fix the thing",
    url="https://github.com/my-org/repo/pull/1",
    is_draft=False,
    author_login="alice",
    repo="my-org/repo",
    created_days_ago=3,
    updated_days_ago=1,
    labels=None,
):
    """Helper to build a realistic GraphQL PR node."""
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=created_days_ago)
    updated = now - timedelta(days=updated_days_ago)
    return {
        "number": number,
        "title": title,
        "url": url,
        "isDraft": is_draft,
        "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updatedAt": updated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": {"login": author_login} if author_login else None,
        "repository": {"nameWithOwner": repo},
        "labels": {"nodes": [{"name": lbl} for lbl in (labels or [])]},
    }


# ---------------------------------------------------------------------------
# format_pr
# ---------------------------------------------------------------------------

class TestFormatPr:
    def test_basic_fields(self):
        node = _make_node(number=42, title="My PR", url="https://github.com/org/repo/pull/42")
        pr = format_pr(node)
        assert pr["number"] == 42
        assert pr["title"] == "My PR"
        assert pr["url"] == "https://github.com/org/repo/pull/42"
        assert pr["repo"] == "my-org/repo"
        assert pr["author"] == "alice"
        assert pr["draft"] is False

    def test_age_days_calculated_correctly(self):
        node = _make_node(created_days_ago=5, updated_days_ago=2)
        pr = format_pr(node)
        assert pr["age_days"] == 5
        assert pr["updated_days"] == 2

    def test_fresh_pr_age_is_zero(self):
        node = _make_node(created_days_ago=0, updated_days_ago=0)
        pr = format_pr(node)
        assert pr["age_days"] == 0

    def test_null_author_falls_back_to_unknown(self):
        node = _make_node(author_login=None)
        pr = format_pr(node)
        assert pr["author"] == "unknown"

    def test_draft_flag(self):
        node = _make_node(is_draft=True)
        pr = format_pr(node)
        assert pr["draft"] is True

    def test_labels_extracted(self):
        node = _make_node(labels=["bug", "priority:high"])
        pr = format_pr(node)
        assert pr["labels"] == ["bug", "priority:high"]

    def test_empty_labels(self):
        node = _make_node(labels=[])
        pr = format_pr(node)
        assert pr["labels"] == []


# ---------------------------------------------------------------------------
# fetch_review_prs
# ---------------------------------------------------------------------------

class TestFetchReviewPrs:
    def _pr(self, url, author="alice", age=5):
        node = _make_node(url=url, author_login=author, created_days_ago=age)
        return node

    @patch("scripts.github_prs.graphql_search_all")
    def test_user_prs_are_included(self, mock_search):
        node = self._pr("https://github.com/org/repo/pull/1", author="alice", age=3)
        mock_search.return_value = [node]
        prs = fetch_review_prs("alice")
        assert len(prs) == 1
        assert prs[0]["author"] == "alice"

    @patch("scripts.github_prs.graphql_search_all")
    def test_renovate_prs_are_excluded(self, mock_search):
        node = self._pr("https://github.com/org/repo/pull/2", author="renovate", age=3)
        mock_search.return_value = [node]
        prs = fetch_review_prs("alice")
        assert prs == []

    @patch("scripts.github_prs.graphql_search_all")
    def test_renovate_bot_suffix_also_excluded(self, mock_search):
        node = self._pr("https://github.com/org/repo/pull/3", author="renovate[bot]", age=3)
        mock_search.return_value = [node]
        prs = fetch_review_prs("alice")
        assert prs == []

    @patch("scripts.github_prs.graphql_search_all")
    def test_deduplication_by_url(self, mock_search):
        node = self._pr("https://github.com/org/repo/pull/1", author="alice", age=3)
        # Return the same PR from both user and team queries
        mock_search.side_effect = [[node], [node]]
        prs = fetch_review_prs("alice")
        assert len(prs) == 1

    @patch("scripts.github_prs.graphql_search_all")
    def test_sorted_newest_first(self, mock_search):
        old_pr = self._pr("https://github.com/org/repo/pull/1", age=10)
        new_pr = self._pr("https://github.com/org/repo/pull/2", age=1)
        mock_search.return_value = [old_pr, new_pr]
        prs = fetch_review_prs("alice")
        ages = [p["age_days"] for p in prs]
        assert ages == sorted(ages)  # ascending = newest first

    @patch("scripts.github_prs.graphql_search_all")
    def test_null_nodes_skipped(self, mock_search):
        node = self._pr("https://github.com/org/repo/pull/1")
        mock_search.return_value = [None, node, None]
        prs = fetch_review_prs("alice")
        assert len(prs) == 1

    @patch("scripts.github_prs.graphql_search_all")
    def test_empty_results_returns_empty_list(self, mock_search):
        mock_search.return_value = []
        prs = fetch_review_prs("alice")
        assert prs == []

    @patch("scripts.github_prs.graphql_search_all")
    def test_search_exception_is_caught(self, mock_search):
        mock_search.side_effect = Exception("Network error")
        # Should not raise — just return empty list
        prs = fetch_review_prs("alice")
        assert prs == []


# ---------------------------------------------------------------------------
# graphql_search_all (pagination logic, no real HTTP)
# ---------------------------------------------------------------------------

class TestGraphqlSearchAll:
    @patch("scripts.github_prs.gql")
    def test_single_page_no_next(self, mock_gql):
        mock_gql.return_value = {
            "search": {
                "nodes": [{"url": "https://github.com/org/repo/pull/1"}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
        results = graphql_search_all("is:open is:pr review-requested:alice")
        assert len(results) == 1
        assert mock_gql.call_count == 1

    @patch("scripts.github_prs.gql")
    def test_pagination_follows_next_page(self, mock_gql):
        page1 = {
            "search": {
                "nodes": [{"url": "https://github.com/org/repo/pull/1"}],
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor123"},
            }
        }
        page2 = {
            "search": {
                "nodes": [{"url": "https://github.com/org/repo/pull/2"}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
        mock_gql.side_effect = [page1, page2]
        results = graphql_search_all("is:open is:pr review-requested:alice")
        assert len(results) == 2
        assert mock_gql.call_count == 2

    @patch("scripts.github_prs.gql")
    def test_page_cap_stops_at_max_pages(self, mock_gql):
        always_has_next = {
            "search": {
                "nodes": [{"url": f"https://github.com/org/repo/pull/x"}],
                "pageInfo": {"hasNextPage": True, "endCursor": "cursor"},
            }
        }
        mock_gql.return_value = always_has_next
        results = graphql_search_all("is:open is:pr review-requested:alice")
        assert mock_gql.call_count == MAX_PAGES
