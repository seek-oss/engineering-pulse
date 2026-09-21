# Harness adapters

Thin entrypoints that activate skills under `skills/` — no duplicated workflow logic.

| Directory | Harness |
|-----------|---------|
| [`cursor/commands/`](cursor/commands/) | Cursor slash commands (`daily-dashboard`, `sprint-burndown`, …) |
| [`claude-code/`](claude-code/) | Claude Code install notes |
| [`pi-agent/`](pi-agent/) | Pi Agent **(in progress)** — manifest / skill layout TBD |

**Canonical workflows:** `skills/engineering-pulse/SKILL.md` (+ `references/`) and
`skills/sprint-burndown/SKILL.md`.

**Scheduled runs:** `~/bin/run-daily-dashboard.sh` uses `AGENT_CLI` from `.env` (see `scripts/lib/agent_cli.sh`).
