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
| **Pi Agent** | See [`harness/pi-agent/README.md`](../harness/pi-agent/README.md) |
| **Scheduled** | `web-install.sh` + LaunchAgent / `make run` — uses `AGENT_CLI` from `.env` |

## Run

- Cursor: `/daily-dashboard` (or invoke the **engineering-pulse** skill by name)
- Any harness: invoke skill by description; agent reads `SKILL.md` then `references/daily-workflow.md`
