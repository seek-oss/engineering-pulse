# Agent Skills (Engineering Pulse)

Publishable skills for [Agent Skills](https://agentskills.io/specification) consumers.

## `engineering-pulse`

Daily engineering health dashboard (Datadog, GitHub, Todoist, optional Glean Stakeholder Pulse, HTML email).

**Path:** `skills/engineering-pulse/`

**Requires:** cloned repo (or `~/.engineering-pulse`) with `scripts/`, `.env`, and user `prompts/dashboards/*.md`.

## `sprint-report`

Sprint progress report for one team's delivery tickets on a Jira board —
configured via one free-form sprint description. Set it as `SPRINT_BOARD` in
`.env` for repository/scheduled runs, or append it directly to the command for
a standalone run: `/sprint-report My sprint board is at https://…`. Produces a
self-contained HTML report combining a burn-up chart (primary), a burn-down
chart with rolling-scope expectation line (secondary), per-epic progress, an
event ledger, and a per-ticket table. Suitable for browsers, Gmail and Outlook.

**Path:** `skills/sprint-report/SKILL.md` (single file)

**Requires:** Atlassian MCP (no browser fallback); no repo Python scripts.
The scheduled runner emails the HTML via `scripts/send_report_smtp.py`.

## Install

| Harness | How |
|---------|-----|
| **Cursor** | Symlink or copy `skills/engineering-pulse` → `.cursor/skills/engineering-pulse` (and optional `skills/sprint-report`); use commands from `harness/cursor/commands/` |
| **Claude Code** | Copy/symlink to `~/.claude/skills/engineering-pulse` — see [`harness/claude-code/README.md`](../harness/claude-code/README.md) |
| **skills.sh** | `skills add` from this git repo with path `skills/engineering-pulse` (per [skills.sh](https://skills.sh) docs) |
| **ai-toolkit** | Fetch subtree `skills/engineering-pulse` from GitHub |
| **Pi Agent** *(in progress)* | Early notes: [`harness/pi-agent/README.md`](../harness/pi-agent/README.md) |
| **Scheduled runner** | `web-install.sh` + LaunchAgent or `make run`; runs `~/bin/run-daily-dashboard.sh` with `AGENT_CLI` (`claude` or `cursor`; experimental `pi`) |

- **Run:**
  - **Cursor:** `/daily-dashboard` (or invoke skill by name).
  - **Claude Code** / **skills.sh** / **ai-toolkit:** invoke **engineering-pulse** from your harness (see [`harness/`](harness/)).
  - **Scheduled / LaunchAgent:** `~/bin/run-daily-dashboard.sh` + `AGENT_CLI` (`claude` or `cursor`; experimental `pi`).
