# Pi Agent

**Status: in progress.** Skill install layout and first-class support are not finalized; `AGENT_CLI=pi` exists for early experiments only (see `scripts/lib/agent_cli.sh`).

Install the skill directory the same way as other Agent Skills consumers:

```bash
ln -sf /path/to/engineering-pulse/skills/engineering-pulse <pi-skills-dir>/engineering-pulse
```

Ensure the agent's workspace is the engineering-pulse repo root (or `~/.engineering-pulse`) so `scripts/` and `.env` resolve.

Document Pi-specific manifest paths here when your Pi Agent version publishes a stable skill layout.

**Headless / scheduled (experimental):** set `AGENT_CLI=pi` in `.env` and run `~/bin/run-daily-dashboard.sh` (set `PI_API_KEY` for your provider). Prefer `claude` or `cursor` until Pi support is finalized.
