# Daily dashboard workflow

## Overview

Run **all Datadog dashboards** defined under `prompts/dashboards/`, produce a **single
focused HTML report**, and email it.

---

## Step 1 — Extract Datadog Dashboards

For **each dashboard** in `prompts/dashboards/` (skip `_*.md` templates), run:

```bash
python3 scripts/datadog_dashboard_extract.py \
  --url '<URL from the dashboard .md file>' \
  --output-slug <SLUG> \
  --days 7 \
  --focus "<focus terms, if any>"
```

Each dashboard writes to `output/<slug>_metric_results.json`.

Read every qualifying `.md` in `prompts/dashboards/` and execute its extraction command.
See `prompts/dashboards/_example.md` for the file format.

---

## Step 2 — Build the HTML report

After Step 1, 2C, 2D, and (if applicable) 2F:

```bash
python3 scripts/todo.py list --json > output/todos.json   # Step 2D
python3 scripts/github_prs.py                             # Step 2C
python3 scripts/render_daily_dashboard_html.py
```

Writes `output/daily_dashboard_report.html` by default (override with `--out`).

The renderer reads `prompts/dashboards/*.md` + matching `output/<slug>_metric_results.json`,
`output/github_prs.json`, `output/todos.json`, `prompts/extras/*.md`, and
`output/stakeholders/*.md` when `STAKEHOLDERS` is set.

**Section order (dynamic Part letters):**

1. Each dashboard `.md` (sorted by filename)
2. Each `--extra LABEL:FILE` (CLI)
3. PR Review Queue
4. My Queue
5. Extras (`prompts/extras/*.md`, skip `_*.md`)
6. Stakeholder Pulse (only if `STAKEHOLDERS` non-empty)

One-off snapshot without a dashboard file:

```bash
python3 scripts/render_daily_dashboard_html.py \
  --extra "DORA Metrics:output/dora_metric_results.json"
```

#### Report format

Focused scorecard — no long prose. Header: `Daily Dashboard — <DATADOG_TEAMS> — YYYY-MM-DD (past 7 days)`.
One tile per widget (latest value; grey for null). Tile colours if hand-editing:

- RED: `#fff5f5` / `#fc8181`
- YELLOW: `#fffff0` / `#f6e05e`
- ORANGE: `#fffaf0` / `#f6ad55`
- GREEN: `#f0fff4` / `#68d391`
- Big numbers: `48px`, weight `800`; max-width `660px`

---

## Step 2C — PR Review Queue

```bash
python3 scripts/github_prs.py
```

Writes `output/github_prs.json`. Renderer shows green “inbox clear” or table:
**Repo** | **Title** | **Author** | **Age** (red ≥5d, yellow 2–4d, draft muted).

---

## Step 2D — Todo & Reading Queue

```bash
python3 scripts/todo.py list --json > output/todos.json
```

Renderer adds **My Queue**: work tasks, personal tasks, reading queue. Actions use
`todo_report.format_view_action_html` (View link only).

---

## Step 2E — Extras

Drop `*.md` into `prompts/extras/` (skip `_*.md`). First `# Heading` = card title.
Override: `--extras-dir prompts/extras`.

---

## Step 3 — Send the report

```bash
python3 scripts/send_report_smtp.py \
  "Daily dashboard — <team> — $(date +%Y-%m-%d)" \
  output/daily_dashboard_report.html
```

Confirm `Sent to <SMTP_TO>`. Do not mark complete until send succeeds.
