---
name: engineering-pulse
description: >
  Run the daily engineering health dashboard: extract Datadog dashboards,
  GitHub PR review queue, Todoist tasks, optional Stakeholder Pulse via Glean MCP,
  render HTML scorecard, and email via SMTP. Use when the user asks for daily
  dashboard, engineering pulse, health scorecard, or @daily-dashboard.
license: MIT
compatibility: >
  Requires Python 3.11+, this repository (or ~/.engineering-pulse) as workspace root,
  .env with Datadog/GitHub/SMTP keys; optional Glean MCP and Todoist for full sections.
metadata:
  author: seek-oss
  repository: https://github.com/seek-oss/engineering-pulse
  scripts-root: scripts
---

# Engineering Pulse — daily dashboard

## Execution contract

- Run in the **workspace root** (cloned repo or `~/.engineering-pulse`).
- This is an **execution** task — run steps now; do not stop at analysis.
- Complete only when **SMTP send succeeds** (`Sent to <SMTP_TO>`).

**Time window:** past **7 days** for all Datadog extractions (`--days 7`).

## Prerequisites

Read [env-and-paths.md](references/env-and-paths.md) for `.env` variables, gitignored
paths, and script reference.

## Workflow

1. **Datadog** — [daily-workflow.md § Step 1](references/daily-workflow.md#step-1--extract-datadog-dashboards)
2. **Render prep** — PRs, todos, extras per [daily-workflow.md](references/daily-workflow.md#step-2--build-the-html-report)
3. **Stakeholder Pulse** (if `STAKEHOLDERS` set) — [stakeholder-pulse.md](references/stakeholder-pulse.md)
4. **Render HTML** — `python3 scripts/render_daily_dashboard_html.py`
5. **Email** — [daily-workflow.md § Step 3](references/daily-workflow.md#step-3--send-the-report)

## Related tasks

| Task | Reference |
|------|-----------|
| Add a Datadog dashboard | [add-dashboard.md](references/add-dashboard.md) |
| Todoist / reading queue | [todo.md](references/todo.md) |

## User data locations

- Dashboard defs: `prompts/dashboards/*.md` (skip `_*.md`)
- Extras: `prompts/extras/*.md`
- Stakeholder cards (generated): `output/stakeholders/*.md`
- Snapshots: `output/<slug>_metric_results.json`, `output/github_prs.json`, `output/todos.json`
