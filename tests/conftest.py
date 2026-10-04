"""
Set required environment variables before any script module is imported.
Module-level code in the scripts (e.g. DD_API_KEY checks) runs on import,
so these must be set before pytest collects tests.
"""

import os

import pytest

os.environ.setdefault("DD_API_KEY", "test-api-key")
os.environ.setdefault("DD_APP_KEY", "test-app-key")
os.environ.setdefault("GITHUB_TOKEN", "test-github-token")
os.environ.setdefault("GITHUB_ORG", "test-org")
os.environ.setdefault("GITHUB_TEAM", "test-team")
os.environ.setdefault("TODOIST_API_TOKEN", "test-todoist-token")
os.environ.setdefault("TODOIST_PROJECT_ID", "test-project-id")


@pytest.fixture(autouse=True)
def _isolated_run_issues(tmp_path, monkeypatch):
    """Keep every test's red-box problems out of the repo's output/run_issues/."""
    from scripts import run_issues

    monkeypatch.setattr(run_issues, "ISSUES_DIR", tmp_path / "run_issues")
    monkeypatch.delenv("EP_RUN_ID", raising=False)
