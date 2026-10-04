"""The runner install.sh generates: problems list per step, run lock, Re-run filter.

Renders the runner heredoc from install.sh into a fake install dir whose agent,
venv python and skills are stubs, then runs it.
"""

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HEREDOC = re.compile(r'^cat > "\$RUNNER_SCRIPT" <<EOF\n(.*?)^EOF$', re.S | re.M)

AGENT_LIB = """load_agent_env() { :; }
resolve_agent() { echo cursor; }
run_agent() { echo "agent $(head -1 <<<"$2")" >> "$CALLS"; }
"""

PYTHON_STUB = """#!/bin/bash
echo "py $*" >> "$CALLS"
"""


def _exe(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def install(tmp_path):
    body = HEREDOC.search((ROOT / "install.sh").read_text()).group(1)
    inst = tmp_path / "install"
    _exe(inst / "scripts/lib/agent_cli.sh", AGENT_LIB)
    _exe(inst / ".venv/bin/python", PYTHON_STUB)
    (inst / ".venv/bin/activate").write_text("")
    (inst / "skills/engineering-pulse").mkdir(parents=True)
    (inst / "skills/engineering-pulse/SKILL.md").write_text("PULSE SKILL\n")
    (inst / "skills/sprint-report").mkdir(parents=True)
    (inst / "skills/sprint-report/SKILL.md").write_text("SPRINT SKILL\n")
    env = {
        **os.environ,
        "qi": str(inst),
        "ql": str(tmp_path / "run.log"),
        "qal": str(inst / "scripts/lib/agent_cli.sh"),
    }
    script = subprocess.run(
        ["bash", "-c", f"cat <<EOF\n{body}EOF\n"], env=env, capture_output=True, text=True
    )
    runner = tmp_path / "run-daily-dashboard.sh"
    _exe(runner, script.stdout)
    return runner, tmp_path


def _run(install, **env):
    runner, tmp = install
    full = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp),
        "CALLS": str(tmp / "calls"),
        "EP_LOCK_DIR": str(tmp / "run.lock"),
        "SPRINT_BOARD": "fictional board",
        **env,
    }
    result = subprocess.run(["bash", str(runner)], env=full, capture_output=True, text=True)
    calls = (tmp / "calls").read_text().splitlines() if (tmp / "calls").exists() else []
    return result, calls


def test_generated_runner_is_valid_bash(install):
    runner, _ = install
    assert subprocess.run(["bash", "-n", str(runner)]).returncode == 0


def test_each_report_starts_a_problems_list_before_the_agent(install):
    result, calls = _run(install)
    assert result.returncode == 0, result.stderr
    agents = [c for c in calls if c.startswith("agent")]
    assert agents == ["agent PULSE SKILL", "agent SPRINT SKILL"]
    for report in ("pulse", "sprint"):
        reset = calls.index(next(c for c in calls if f"reset --type {report}" in c))
        pre = calls.index(
            next(c for c in calls if f"preflight --type {report} --agent cursor" in c)
        )
        agent = calls.index(f"agent {report.upper()} SKILL")
        assert reset < pre < agent


def test_only_filter_runs_one_report(install):
    _, calls = _run(install, ENGINEERING_PULSE_ONLY="sprint")
    assert [c for c in calls if c.startswith("agent")] == ["agent SPRINT SKILL"]


def test_only_filter_cannot_enable_a_paused_report(install):
    _, calls = _run(install, ENGINEERING_PULSE_ONLY="sprint", SCHEDULED_REPORTS="pulse")
    assert not [c for c in calls if c.startswith("agent")]


def test_lock_skips_overlapping_run(install):
    _, tmp = install
    (tmp / "run.lock").mkdir()
    result, calls = _run(install)
    assert result.returncode == 0
    assert calls == []
    assert "Another report run is in progress" in (tmp / "run.log").read_text()


def test_lock_released_after_run(install):
    _, tmp = install
    _run(install)
    assert not (tmp / "run.lock").exists()


def test_stale_lock_is_cleared(install):
    _, tmp = install
    lock = tmp / "run.lock"
    lock.mkdir()
    os.utime(lock, (1, 1))
    _, calls = _run(install)
    assert any(c.startswith("agent") for c in calls)
