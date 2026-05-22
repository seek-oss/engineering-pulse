"""Integration tests for the file-driven dashboard rendering in
scripts/render_daily_dashboard_html.py.

These exercise the CLI end-to-end against a temporary `prompts/dashboards/`
folder, asserting dynamic Part-letter numbering and generic dashboard rendering.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
