# Harness adapters

Thin entrypoints that activate `skills/engineering-pulse/` — no duplicated workflow logic.

| Directory | Harness |
|-----------|---------|
| [`cursor/commands/`](cursor/commands/) | Cursor slash commands |
| [`claude-code/`](claude-code/) | Claude Code install notes |
| [`pi-agent/`](pi-agent/) | Pi Agent (document when manifest format is confirmed) |

**Canonical workflow:** `skills/engineering-pulse/SKILL.md` + `references/`.

**Scheduled runs:** `~/bin/run-daily-dashboard.sh` uses `scripts/run_daily_dashboard.py` by default. Set `RUN_WITH_AGENT=1` to route through `AGENT_CLI` from `.env`.
