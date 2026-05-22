# Claude Code

Install the product skill:

```bash
cp -r /path/to/engineering-pulse/skills/engineering-pulse ~/.claude/skills/engineering-pulse
```

Or symlink:

```bash
ln -sf /path/to/engineering-pulse/skills/engineering-pulse ~/.claude/skills/engineering-pulse
```

Clone the full repo (or use `~/.engineering-pulse`) so `scripts/` and `.env` are available.

Optional slash-command stubs: copy `harness/claude-code/commands/` into your Claude Code commands directory if your install supports them.

Run by asking Claude to use the **engineering-pulse** skill for a daily dashboard.

**Headless / scheduled:** set `AGENT_CLI=claude` in `.env` and run `~/bin/run-daily-dashboard.sh` (requires `ANTHROPIC_API_KEY` for automation).
