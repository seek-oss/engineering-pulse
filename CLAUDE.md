# Engineering Pulse — Claude Code context

Read [`AGENTS.md`](AGENTS.md) first; it is the canonical repo context for coding
agents in this project.

Critical runtime invariant: Engineering Pulse is an agent- and skill-driven product.
Follow `skills/engineering-pulse/SKILL.md` and its references for the daily dashboard
workflow. Keep `make run` and scheduled runs executing the selected agent through
`AGENT_CLI`; do not replace that product path with direct Python orchestration.

Python files under `scripts/` are tools called by the agent-guided workflow.
`scripts/run_daily_dashboard.py` is useful for helper/debug execution, not the
primary runtime.

For headless Claude Code runs, the generated runner must use explicit
non-interactive permission handling so Bash and file-read tools do not wait for an
approval UI that is unavailable during `make run` or LaunchAgent execution.
