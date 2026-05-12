"""Integration tests for Stakeholder Pulse wiring in the renderer.

Unit-level coverage of `render_extras_section()` lives in
`test_extras_plugin.py`. These tests exercise the stakeholders call-site in
`render_daily_dashboard_html.main()` end-to-end against minimal fixtures,
using the same subprocess style as `test_render_dashboards_integration.py`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "render_daily_dashboard_html.py"


def _write_prs(path: Path) -> None:
    path.write_text(json.dumps({"prs": []}), encoding="utf-8")


def _write_todos(path: Path) -> None:
    path.write_text(json.dumps([]), encoding="utf-8")


def _run(
    tmp_path: Path,
    *,
    stakeholders_dir: Path,
    extras_dir: Path | None = None,
) -> str:
    out = tmp_path / "report.html"
    extras = extras_dir if extras_dir is not None else tmp_path / "extras"
    (tmp_path / "dashboards").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    extras.mkdir(exist_ok=True)
    _write_prs(tmp_path / "output" / "github_prs.json")
    _write_todos(tmp_path / "output" / "todos.json")

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
        str(extras),
        "--stakeholders-dir",
        str(stakeholders_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, (
        f"renderer failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    return out.read_text(encoding="utf-8")


class TestStakeholderPulseWiring:
    def test_omits_section_when_dir_missing(self, tmp_path: Path) -> None:
        html = _run(tmp_path, stakeholders_dir=tmp_path / "missing")
        assert "Stakeholder Pulse" not in html

    def test_omits_section_when_dir_only_has_underscore_files(
        self, tmp_path: Path
    ) -> None:
        sdir = tmp_path / "stakeholders"
        sdir.mkdir()
        (sdir / "_example.md").write_text("# example\n", encoding="utf-8")
        html = _run(tmp_path, stakeholders_dir=sdir)
        assert "Stakeholder Pulse" not in html

    def test_emits_stakeholder_pulse_with_card(self, tmp_path: Path) -> None:
        sdir = tmp_path / "stakeholders"
        sdir.mkdir()
        (sdir / "jane-doe.md").write_text(
            "# Jane Doe\n\n- **Themes:** orchestrator work\n", encoding="utf-8"
        )
        html = _run(tmp_path, stakeholders_dir=sdir)
        # Zero dashboards: PR=A, Queue=B, Stakeholder=C
        assert "Part C — Stakeholder Pulse" in html
        assert "Jane Doe" in html
        assert "orchestrator work" in html
        assert '<div class="extra-card">' in html

    def test_renders_one_card_per_stakeholder_file(self, tmp_path: Path) -> None:
        sdir = tmp_path / "stakeholders"
        sdir.mkdir()
        (sdir / "jane-doe.md").write_text("# Jane Doe\n\n- A\n", encoding="utf-8")
        (sdir / "john-smith.md").write_text("# John Smith\n\n- B\n", encoding="utf-8")
        html = _run(tmp_path, stakeholders_dir=sdir)
        assert "Jane Doe" in html
        assert "John Smith" in html
        assert html.count('<div class="extra-card">') == 2

    def test_extras_and_stakeholder_pulse_coexist(self, tmp_path: Path) -> None:
        edir = tmp_path / "extras"
        edir.mkdir()
        (edir / "release-notes.md").write_text(
            "# Release notes\n\n- v1.2 shipped\n", encoding="utf-8"
        )
        sdir = tmp_path / "stakeholders"
        sdir.mkdir()
        (sdir / "jane-doe.md").write_text("# Jane Doe\n\n- A\n", encoding="utf-8")

        html = _run(tmp_path, stakeholders_dir=sdir, extras_dir=edir)
        assert "Part C — Extras" in html
        assert "Part D — Stakeholder Pulse" in html
        assert "Release notes" in html
        assert "Jane Doe" in html
        assert html.index("Part C") < html.index("Part D")
