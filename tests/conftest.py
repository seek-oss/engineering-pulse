"""
Set required environment variables before any script module is imported.
Module-level code in the scripts (DD_API_KEY, GITHUB_TOKEN checks) runs
on import, so these must be set before pytest collects tests.
"""
import os

os.environ.setdefault("DD_API_KEY", "test-api-key")
os.environ.setdefault("DD_APP_KEY", "test-app-key")
os.environ.setdefault("GITHUB_TOKEN", "test-github-token")
os.environ.setdefault("GITHUB_ORG", "test-org")
os.environ.setdefault("GITHUB_TEAM", "test-team")
os.environ.setdefault("TODOIST_API_TOKEN", "test-todoist-token")
os.environ.setdefault("TODOIST_PROJECT_ID", "test-project-id")
