# Engineering Pulse — agent context

## What this project is

A prompt- and skill-driven engineering productivity tool: Datadog metrics, GitHub PR
queue, Todoist tasks, optional Stakeholder Pulse (Glean MCP), HTML scorecard, SMTP email.

**Product skill (portable):** [`skills/engineering-pulse/`](skills/engineering-pulse/) per
[Agent Skills](https://agentskills.io/specification).

**Harness entrypoints:** [`harness/`](harness/) — **Claude Code** and **Cursor** (e.g. **`/daily-dashboard`**); **Pi Agent [in progress](harness/pi-agent/)**; plus scheduled / headless runs via [`scripts/lib/agent_cli.sh`](scripts/lib/agent_cli.sh).

## Product invariants

- The canonical daily-dashboard workflow is Markdown guidance:
  `skills/engineering-pulse/SKILL.md` plus `skills/engineering-pulse/references/`.
- `make run` and scheduled runs must stay agent-driven through `AGENT_CLI`; do not
  replace product execution with a direct Python-only pipeline.
- `scripts/` contains callable tools for the agent-guided workflow. Keep workflow
  decisions and prose in the skill references.
- `scripts/run_daily_dashboard.py` is a helper/debug path for running the toolchain
  directly; it is not the primary product runtime.
- Installed `~/.engineering-pulse` clones normally track `main`. Feature branch
  checkout is a maintainer testing workflow, not normal user guidance.
- Claude Code headless runs need explicit non-interactive permission handling in the
  runner; keep that behavior aligned with Cursor/Pi trust/force execution.

## Layout

| Path | Role |
|------|------|
| `scripts/` | Python orchestration (Datadog, GitHub, render, SMTP, Todoist) |
| `scripts/lib/agent_cli.sh` | Multi-agent CLI abstraction for scheduled runs (`AGENT_CLI`) |
| `skills/engineering-pulse/` | Canonical daily-dashboard workflow (`SKILL.md` + `references/`) |
| `prompts/dashboards/_*.md` | Shipped dashboard definition templates |
| `prompts/extras/_*.md` | Shipped extra-card templates |
| `output/` | Disposable generated JSON/HTML; `output/stakeholders/*.md` for Glean cards |
| `~/.engineering-pulse-data/` | Durable `.env`, dashboard definitions, extras and report archive |
| `local/` | Maintainer-only tools (gitignored) |
| `.cursor/skills/` | Cursor adapters; product skill symlinks to `skills/engineering-pulse/` |

## Rules

- **Credentials:** `~/.engineering-pulse-data/.env` via python-dotenv only — never hardcode tokens or org URLs in tracked files.
- **Output:** HTML/JSON under `output/` (`output/daily_dashboard_report.html`).
- **Config:** No hardcoded org/team names — use env vars (`DATADOG_TEAMS`, `GITHUB_TEAM`, etc.).
- **Privacy:** No real stakeholder names or other PII in tracked files; demo and test fixtures use fictional orgs, hosts and names.
- **Changes:** Behaviour changes include or update tests; prefer the smallest correct diff and avoid new dependencies unless justified.
- **Scripts:** Thin orchestration in `scripts/`; workflow prose lives in the skill references.

## Scripts

| Script | Purpose |
|--------|---------|
| `datadog_dashboard_extract.py` | Dashboard metrics → `output/<slug>_metric_results.json` |
| `github_prs.py` | PR review queue → `output/github_prs.json` |
| `render_daily_dashboard_html.py` | Build `output/daily_dashboard_report.html` |
| `send_report_smtp.py` | Email the report |
| `todo.py` | Todoist tasks / reading queue |
| `deliver_report.py` | Archive a report to the calendar, then notify/email per `DELIVERY` |
| `settings.py` | Validate and apply calendar Settings (schedule, paused reports, auto-open, retention) |
| `report_snapshot.py` | Structured snapshot of a report, used by the calendar's change view |
| `compare_reports.py` / `run_compare.sh` | Validate two report ids and run the `report-compare` skill via `AGENT_CLI` |

## Development

```bash
python -m pip install -r requirements.txt
ruff check scripts tests
ruff format --check scripts tests
python -m pytest tests/ -q
```

CI runs the same lint and test jobs on push/PR (see `.github/workflows/ci.yml`).

## Terminal output

Use `rich` in scripts. Colour convention: red = attention, yellow = watch, green = healthy.
