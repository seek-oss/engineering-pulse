"""install.sh asks for the agent even under curl | bash, unless .env already has one.

Extracts the helper functions from install.sh and runs choose_agent with stdin
not a terminal (as with curl | bash) and a file standing in for /dev/tty.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FUNCS = ("info", "success", "warn", "divider", "upsert_env_var", "_detected_has_agent")
FUNCS += ("show_agent_selector", "choose_agent")


def _functions() -> str:
    text = (ROOT / "install.sh").read_text()
    parts = []
    for name in FUNCS:
        one_line = re.search(rf"^{name}\(\)\s*\{{.*\}}$", text, re.M)
        block = re.search(rf"^{name}\(\) \{{\n.*?^\}}$", text, re.M | re.S)
        parts.append((one_line or block).group(0))
    return "\n".join(parts)


def _choose(tmp_path: Path, env_text: str, tty_answer: str | None) -> tuple[str, str]:
    env_file = tmp_path / ".env"
    env_file.write_text(env_text)
    tty = tmp_path / "tty"
    if tty_answer is not None:
        tty.write_text(tty_answer)
    script = (
        f'source "{ROOT}/scripts/lib/agent_cli.sh"\n{_functions()}\n'
        f'choose_agent "{env_file}" cursor ""\necho "SELECTED=$SELECTED_AGENT"\n'
    )
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "AGENT_PROMPT_TTY": str(tty)}
    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout, env_file.read_text()


def test_asks_via_tty_when_no_agent_saved(tmp_path):
    out, env = _choose(tmp_path, "# AGENT_CLI=cursor\n", "2\n")
    assert "SELECTED=claude" in out
    assert re.search(r"^AGENT_CLI=claude$", env, re.M)
    assert "# AGENT_CLI" not in env


def test_upsert_promotes_commented_placeholder(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Agent that runs the reports\n"
        "# AGENT_CLI=cursor\n"
        "DATADOG_TEAMS=your-team\n"
    )
    script = (
        f'source "{ROOT}/scripts/lib/agent_cli.sh"\n{_functions()}\n'
        f'upsert_env_var "AGENT_CLI" "claude" "{env_file}"\n'
    )
    subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True)
    text = env_file.read_text()
    assert re.search(r"^AGENT_CLI=claude$", text, re.M)
    assert "# AGENT_CLI" not in text
    assert "DATADOG_TEAMS=your-team" in text


def test_keeps_saved_agent_without_asking(tmp_path):
    out, env = _choose(tmp_path, "AGENT_CLI=pi\n", "2\n")
    assert "SELECTED=pi" in out
    assert "Keeping existing AGENT_CLI=pi" in out
    assert env == "AGENT_CLI=pi\n"


def test_defaults_when_no_terminal_available(tmp_path):
    out, env = _choose(tmp_path, "", None)
    assert "SELECTED=cursor" in out
    assert "Non-interactive install" in out
    assert re.search(r"^AGENT_CLI=cursor$", env, re.M)


@pytest.mark.parametrize("answer", ["\n", "x\n"])
def test_enter_or_invalid_answer_uses_default(tmp_path, answer):
    out, _ = _choose(tmp_path, "", answer)
    assert "SELECTED=cursor" in out


def test_env_example_leaves_agent_unset():
    text = (ROOT / ".env.example").read_text()
    assert not re.search(r"^AGENT_CLI=", text, re.M)
