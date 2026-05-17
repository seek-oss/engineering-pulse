# Engineering Pulse — agent context

## What this project is

A prompt- and skill-driven engineering productivity tool: Datadog metrics, GitHub PR
queue, Todoist tasks, optional Stakeholder Pulse (Glean MCP), HTML scorecard, SMTP email.

**Product skill (portable):** [`skills/engineering-pulse/`](skills/engineering-pulse/) per
[Agent Skills](https://agentskills.io/specification).

**Harness entrypoints:** [`harness/`](harness/) (Cursor `/daily-dashboard`, Claude Code, Pi Agent).

## Layout

| Path | Role |
|------|------|
| `scripts/` | Python orchestration (Datadog, GitHub, render, SMTP, Todoist) |
| `skills/engineering-pulse/` | Canonical daily-dashboard workflow (`SKILL.md` + `references/`) |
| `prompts/dashboards/*.md` | User dashboard defs (gitignored except `_example.md`) |
| `prompts/extras/*.md` | Drop-in report cards (gitignored except `_example.md`) |
| `output/` | Generated JSON/HTML; `output/stakeholders/*.md` for Glean cards |
| `.env` | Secrets (never commit) |
| `local/` | Maintainer-only tools (gitignored) |
| `.cursor/skills/` | Cursor adapters; product skill symlinks to `skills/engineering-pulse/` |

## Rules

- **Credentials:** `.env` via python-dotenv only — never hardcode tokens or org URLs in tracked files.
- **Output:** HTML/JSON under `output/`; report at repo root as `daily_dashboard_report.html`.
- **Config:** No hardcoded org/team names — use env vars (`DATADOG_TEAMS`, `GITHUB_ORG`, etc.).
- **Scripts:** Thin orchestration in `scripts/`; workflow prose lives in the skill references.

## Scripts

| Script | Purpose |
|--------|---------|
| `datadog_dashboard_extract.py` | Dashboard metrics → `output/<slug>_metric_results.json` |
| `github_prs.py` | PR review queue → `output/github_prs.json` |
| `render_daily_dashboard_html.py` | Build `daily_dashboard_report.html` |
| `send_report_smtp.py` | Email the report |
| `todo.py` | Todoist tasks / reading queue |

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
