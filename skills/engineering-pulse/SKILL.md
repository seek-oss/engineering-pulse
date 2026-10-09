---
name: engineering-pulse
description: >
  Run the daily engineering health dashboard: extract Datadog dashboards,
  GitHub PR review queue, Todoist tasks, optional Stakeholder Pulse via Glean MCP,
  render HTML scorecard, archive it to a local report calendar, and notify
  (macOS) and/or email via SMTP. Use when the user asks for daily
  dashboard, engineering pulse, health scorecard, or @daily-dashboard.
license: MIT
compatibility: >
  Requires Python 3.11+, this repository (or ~/.engineering-pulse) as workspace root,
  .env with team names (SMTP/Todoist optional); Datadog via Datadog MCP and GitHub
  via GitHub MCP (OAuth); optional Glean MCP for Stakeholder Pulse.
metadata:
  author: seek-oss
  repository: https://github.com/seek-oss/engineering-pulse
  scripts-root: scripts
---

# Engineering Pulse — daily dashboard

## Execution contract

- Run in the **workspace root** (cloned repo or `~/.engineering-pulse`).
- This is an **execution** task — run steps now; do not stop at analysis.
- Complete only when **delivery succeeds** (`scripts/deliver_report.py send` exits 0).

**Time window:** past **7 days** for all Datadog extractions (`--days 7`).

## Prerequisites

Read [env-and-paths.md](references/env-and-paths.md) for `.env` variables, gitignored
paths, and script reference.

## Workflow

1. **Datadog** — [datadog-mcp-extract.md](references/datadog-mcp-extract.md) (MCP; past 7 days)
2. **Render prep** — PRs (GitHub MCP), todos, extras per [daily-workflow.md](references/daily-workflow.md#step-2--build-the-html-report)
3. **Stakeholder Pulse** (if `STAKEHOLDERS` set) — [stakeholder-pulse.md](references/stakeholder-pulse.md)
4. **Render HTML** — `python3 scripts/render_daily_dashboard_html.py`
5. **Deliver** (archive + notify/email per `DELIVERY`) — [daily-workflow.md § Step 3](references/daily-workflow.md#step-3--deliver-the-report)

## Related tasks

| Task | Reference |
|------|-----------|
| Add a Datadog dashboard | [add-dashboard.md](references/add-dashboard.md) |
| Todoist / reading queue | [todo.md](references/todo.md) |
| Sprint report (optional extras card) | [../sprint-report/SKILL.md](../sprint-report/SKILL.md) |

## User data locations

- Configuration: `~/.engineering-pulse-data/.env`
- Dashboard defs: `~/.engineering-pulse-data/dashboards/*.md`
- Extras: `~/.engineering-pulse-data/extras/*.md`
- Stakeholder cards (generated): `output/stakeholders/*.md`
- Snapshots: `output/<slug>_metric_results.json`, `output/github_prs.json`, `output/todos.json`
- HTML scorecard (default render): `output/daily_dashboard_report.html`
- Report archive + calendar: `~/.engineering-pulse-data/reports/` (`index.html`, `manifest.json`)
