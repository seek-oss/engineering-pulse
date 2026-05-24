# Agent Skills (Engineering Pulse)

Publishable skills for [Agent Skills](https://agentskills.io/specification) consumers.

## `engineering-pulse`

Daily engineering health dashboard (Datadog, GitHub, Todoist, optional Glean Stakeholder Pulse, HTML email).

**Path:** `skills/engineering-pulse/`

**Requires:** cloned repo (or `~/.engineering-pulse`) with `scripts/`, `.env`, and user `prompts/dashboards/*.md`.

## Install

| Harness | How |
|---------|-----|
| **Cursor** | Symlink or copy `skills/engineering-pulse` → `.cursor/skills/engineering-pulse`; use commands from `harness/cursor/commands/` |
| **Claude Code** | Copy/symlink to `~/.claude/skills/engineering-pulse` — see [`harness/claude-code/README.md`](../harness/claude-code/README.md) |
| **skills.sh** | `skills add` from this git repo with path `skills/engineering-pulse` (per [skills.sh](https://skills.sh) docs) |
| **ai-toolkit** | Fetch subtree `skills/engineering-pulse` from GitHub |
| **Pi Agent** *(in progress)* | Early notes: [`harness/pi-agent/README.md`](../harness/pi-agent/README.md) |
| **Scheduled runner** | `web-install.sh` + LaunchAgent or `make run`; runs `~/bin/run-daily-dashboard.sh` with `AGENT_CLI` (`claude` or `cursor`; experimental `pi`) |

- **Run:**
  - **Cursor:** `/daily-dashboard` (or invoke skill by name).
  - **Claude Code** / **skills.sh** / **ai-toolkit:** invoke **engineering-pulse** from your harness (see [`harness/`](harness/)).
  - **Scheduled / LaunchAgent:** `~/bin/run-daily-dashboard.sh` + `AGENT_CLI` (`claude` or `cursor`; experimental `pi`).
