"""Integration tests for the file-driven dashboard rendering in
scripts/render_daily_dashboard_html.py.

These exercise the CLI end-to-end against a temporary `prompts/dashboards/`
folder, asserting dynamic Part-letter numbering and generic dashboard rendering.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "render_daily_dashboard_html.py"


def _write_prs(path: Path, prs: list[dict]) -> None:
    path.write_text(json.dumps({"prs": prs}), encoding="utf-8")


def _write_todos(path: Path, todos: list[dict]) -> None:
    path.write_text(json.dumps(todos), encoding="utf-8")


def _write_snapshot(path: Path, results: list[dict], *, url: str = "") -> None:
    path.write_text(
        json.dumps(
            {
                "dashboard_title": "test",
                "source_url": url,
                "generated_at": "2026-05-13T00:00:00Z",
                "results": results,
            }
        ),
        encoding="utf-8",
    )


def _run(tmp_path: Path, *extra_args: str) -> str:
    """Invoke the CLI against tmp dirs; return the rendered HTML."""
    out = tmp_path / "report.html"
    (tmp_path / "stakeholders").mkdir(exist_ok=True)
    sd_stub = tmp_path / "pytest_stakeholders_dotenv.env"
    sd_stub.write_text("# pytest integration: omit STAKEHOLDERS key\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("STAKEHOLDERS", None)
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--out",
        str(out),
        "--dashboards-dir",
        str(tmp_path / "dashboards"),
        "--output-dir",
        str(tmp_path / "output"),
        "--prs",
        str(tmp_path / "output" / "github_prs.json"),
        "--todos",
        str(tmp_path / "output" / "todos.json"),
        "--extras-dir",
        str(tmp_path / "extras"),
        "--stakeholders-dir",
        str(tmp_path / "stakeholders"),
        "--stakeholders-dotenv",
        str(sd_stub),
        *extra_args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env)
    assert result.returncode == 0, (
        f"renderer failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    return out.read_text(encoding="utf-8")


@pytest.fixture
def base_dirs(tmp_path: Path) -> Path:
    """Set up empty dashboards/output/extras/stakeholders dirs + minimal fixtures."""
    (tmp_path / "dashboards").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "extras").mkdir()
    (tmp_path / "stakeholders").mkdir()
    _write_prs(tmp_path / "output" / "github_prs.json", [])
    _write_todos(tmp_path / "output" / "todos.json", [])
    return tmp_path


class TestZeroDashboards:
    def test_pr_queue_becomes_part_a(self, base_dirs: Path) -> None:
        html = _run(base_dirs)
        assert "Part A — PR Review Queue" in html
        assert "Part B — My Queue" in html

    def test_header_has_no_dashboard_links(self, base_dirs: Path) -> None:
        html = _run(base_dirs)
        # The links bar exists but is empty / whitespace when no dashboards.
        assert '<div class="links">' in html
        assert " ↗</a>" not in html


class TestOptionalInputs:
    def test_missing_todos_omits_my_queue(self, base_dirs: Path) -> None:
        (base_dirs / "output" / "todos.json").unlink()
        html = _run(base_dirs)
        assert "Part A — PR Review Queue" in html
        assert "— My Queue" not in html

    def test_missing_prs_shows_not_fetched(self, base_dirs: Path) -> None:
        (base_dirs / "output" / "github_prs.json").unlink()
        html = _run(base_dirs)
        assert "Part A — PR Review Queue" in html
        assert "PR data not fetched" in html
        assert "inbox clear" not in html
        assert "Part B — My Queue" in html

    def test_empty_prs_still_shows_inbox_clear(self, base_dirs: Path) -> None:
        html = _run(base_dirs)
        assert "inbox clear" in html
        assert "PR data not fetched" not in html


class TestFeatureHints:
    """Top-right badge listing optional parts that are switched off."""

    def _run_with_env(self, base_dirs: Path, dotenv: str) -> str:
        env_file = base_dirs / "settings.env"
        env_file.write_text(dotenv, encoding="utf-8")
        return _run(base_dirs, "--stakeholders-dotenv", str(env_file))

    def test_all_optional_parts_off(self, base_dirs: Path) -> None:
        html = self._run_with_env(base_dirs, "# nothing optional set\n")
        assert "3 more features" in html
        for title in ("Stakeholder Pulse", "Sprint report", "My Queue"):
            assert f'<div class="hint-title">{title}</div>' in html
        assert "Glean MCP" in html and "STAKEHOLDERS=" in html
        assert html.index('class="hints"') < html.index("<h1>")

    def test_only_missing_parts_are_listed(self, base_dirs: Path) -> None:
        html = self._run_with_env(
            base_dirs, 'SPRINT_BOARD="fictional board"\nTODOIST_API_TOKEN=x\n'
        )
        assert "1 more feature<" in html
        assert '<div class="hint-title">Stakeholder Pulse</div>' in html
        assert '<div class="hint-title">Sprint report</div>' not in html

    def test_no_badge_when_everything_is_on(self, base_dirs: Path) -> None:
        html = self._run_with_env(
            base_dirs, 'STAKEHOLDERS=Jane Doe\nSPRINT_BOARD="x"\nTODOIST_API_TOKEN=x\n'
        )
        assert 'class="hints"' not in html
        assert "<!--ep-hints-->" not in html


def test_footer_includes_run_time(base_dirs: Path) -> None:
    """Re-runs with unchanged data must still differ, or the archive treats them as duplicates."""
    html = _run(base_dirs)
    assert re.search(r"Generated \d{4}-\d{2}-\d{2} \d{2}:\d{2} ·", html)


class TestSince:
    """--since (fallback report): inputs written before the run started are ignored."""

    def _age(self, path: Path, hours: int = 3) -> None:
        old = time.time() - hours * 3600
        os.utime(path, (old, old))

    def test_stale_inputs_are_ignored(self, base_dirs: Path) -> None:
        (base_dirs / "dashboards" / "alpha.md").write_text(
            "# Alpha\n- **URL:** `https://example.com/alpha`\n- **Slug:** `alpha`\n",
            encoding="utf-8",
        )
        snap = base_dirs / "output" / "alpha_metric_results.json"
        _write_snapshot(snap, [{"widget_title": "OldWidget", "series": [{"latest": 1.0}]}])
        for path in (snap, base_dirs / "output" / "github_prs.json"):
            self._age(path)
        self._age(base_dirs / "output" / "todos.json")
        html = _run(base_dirs, "--since", str(time.time() - 60))
        assert "OldWidget" not in html
        assert "PR data not fetched" in html
        assert "— My Queue" not in html
        assert "Part A — PR Review Queue" in html

    def test_fresh_inputs_are_used(self, base_dirs: Path) -> None:
        _write_prs(
            base_dirs / "output" / "github_prs.json",
            [
                {
                    "number": 7,
                    "title": "Fresh change",
                    "repo": "acme-corp/widgets",
                    "author": "alice",
                    "age_days": 1,
                    "updated_days": 0,
                    "url": "https://github.com/acme-corp/widgets/pull/7",
                    "labels": [],
                    "draft": False,
                }
            ],
        )
        html = _run(base_dirs, "--since", str(time.time() - 60))
        assert "Fresh change" in html
        assert "Part B — My Queue" in html

    def test_without_since_old_files_still_render(self, base_dirs: Path) -> None:
        self._age(base_dirs / "output" / "todos.json")
        assert "Part B — My Queue" in _run(base_dirs)


class TestDashboardOrdering:
    def test_two_dashboards_shift_pr_queue_to_part_c(self, base_dirs: Path) -> None:
        # Two generic dashboards with snapshots.
        (base_dirs / "dashboards" / "alpha.md").write_text(
            "# Alpha\n- **URL:** `https://example.com/alpha`\n- **Slug:** `alpha`\n",
            encoding="utf-8",
        )
        (base_dirs / "dashboards" / "beta.md").write_text(
            "# Beta\n- **URL:** `https://example.com/beta`\n- **Slug:** `beta`\n",
            encoding="utf-8",
        )
        _write_snapshot(
            base_dirs / "output" / "alpha_metric_results.json",
            [{"widget_title": "AlphaWidget", "series": [{"scope": "*", "latest": 1.0}]}],
            url="https://example.com/alpha",
        )
        _write_snapshot(
            base_dirs / "output" / "beta_metric_results.json",
            [{"widget_title": "BetaWidget", "series": [{"scope": "*", "latest": 2.0}]}],
            url="https://example.com/beta",
        )

        html = _run(base_dirs)
        assert "Part A — Alpha" in html
        assert "Part B — Beta" in html
        assert "Part C — PR Review Queue" in html
        assert "Part D — My Queue" in html
        # Header links present
        assert "Alpha ↗" in html
        assert "Beta ↗" in html

    def test_underscore_templates_are_skipped(self, base_dirs: Path) -> None:
        (base_dirs / "dashboards" / "_template.md").write_text(
            "# Skipped\n- **Slug:** `template`\n", encoding="utf-8"
        )
        # Don't write a snapshot — the template should be skipped before snapshot lookup.
        html = _run(base_dirs)
        assert "Skipped" not in html
        assert "Part A — PR Review Queue" in html

    def test_dashboard_without_snapshot_is_skipped_with_warning(self, base_dirs: Path) -> None:
        (base_dirs / "dashboards" / "lonely.md").write_text(
            "# Lonely\n- **Slug:** `lonely`\n", encoding="utf-8"
        )
        # No `lonely_metric_results.json` — renderer should warn and skip.
        env = os.environ.copy()
        env.pop("STAKEHOLDERS", None)
        cmd = [
            sys.executable,
            str(SCRIPT),
            "--out",
            str(base_dirs / "report.html"),
            "--dashboards-dir",
            str(base_dirs / "dashboards"),
            "--output-dir",
            str(base_dirs / "output"),
            "--prs",
            str(base_dirs / "output" / "github_prs.json"),
            "--todos",
            str(base_dirs / "output" / "todos.json"),
            "--extras-dir",
            str(base_dirs / "extras"),
            "--stakeholders-dir",
            str(base_dirs / "stakeholders"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env)
        assert result.returncode == 0
        assert "lonely_metric_results.json not found" in result.stderr
        html = (base_dirs / "report.html").read_text(encoding="utf-8")
        assert "Lonely" not in html
        assert "Part A — PR Review Queue" in html


class TestGenericRendererWithDashboard:
    def test_generic_renderer_emits_tile_per_widget(self, base_dirs: Path) -> None:
        (base_dirs / "dashboards" / "my_dashboard.md").write_text(
            "# My Dashboard\n- **URL:** `https://example.com/mine`\n- **Slug:** `my_dashboard`\n",
            encoding="utf-8",
        )
        _write_snapshot(
            base_dirs / "output" / "my_dashboard_metric_results.json",
            [
                {"widget_title": "Error Rate", "series": [{"scope": "*", "latest": 3.5}]},
                {"widget_title": "Throughput", "series": [{"scope": "*", "latest": 1200}]},
            ],
        )
        html = _run(base_dirs)
        assert "Part A — My Dashboard" in html
        assert "Error Rate" in html
        assert "Throughput" in html
        assert "3.5" in html
        assert "1200.0" in html


class TestExtraFlag:
    def test_extra_flag_still_works(self, base_dirs: Path) -> None:
        _write_snapshot(
            base_dirs / "output" / "dora_metric_results.json",
            [{"widget_title": "DeployRate", "series": [{"scope": "*", "latest": 7.5}]}],
        )
        html = _run(
            base_dirs,
            "--extra",
            f"DORA Metrics:{base_dirs / 'output' / 'dora_metric_results.json'}",
        )
        assert "Part A — DORA Metrics" in html
        assert "DeployRate" in html
        assert "Part B — PR Review Queue" in html
