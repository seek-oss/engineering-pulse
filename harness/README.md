# Harness adapters

Thin entrypoints that activate `skills/engineering-pulse/` — no duplicated workflow logic.

| Directory | Harness |
|-----------|---------|
| [`cursor/commands/`](cursor/commands/) | Cursor slash commands |
| [`claude-code/`](claude-code/) | Claude Code install notes |
| [`pi-agent/`](pi-agent/) | Pi Agent (document when manifest format is confirmed) |

**Canonical workflow:** `skills/engineering-pulse/SKILL.md` + `references/`.

**Scheduled runs:** `~/bin/run-daily-dashboard.sh` uses `AGENT_CLI` from `.env` (see `scripts/lib/agent_cli.sh`).
