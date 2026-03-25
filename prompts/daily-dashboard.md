# Daily Dashboard Review

## Overview

This is an execution task, not a review task.
Do the steps now in the workspace. Do not stop after analysis or suggestions.

Run **all Datadog dashboards defined below**, produce a **single focused HTML report**, and email it.

**Time window: past 2 days for all dashboards** (use `--days 2`).

---

## Prerequisites

### Environment variables (`.env`)

| Variable | Required | Purpose |
|----------|----------|---------|
| `DD_API_KEY` | yes | Datadog API key |
| `DD_APP_KEY` | yes | Datadog application key |
| `DD_SITE` | no | API host (default `https://api.datadoghq.com`) |
| `DATADOG_TEAMS` | no | Comma-separated teams — replaces `tpl_var_team` in URL **and** injects `team:<value>` into every metric query |
| `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_TO` | yes | Gmail SMTP credentials |
| `TODOIST_API_TOKEN` | no | Todoist API token (for Part D: todo / reading queue) |
| `TODOIST_PROJECT_ID` | no | Auto-set by `python scripts/todo.py setup` |

### Datadog Site

| Site | DD_SITE value |
|------|--------------|
| US1 (default) | `https://api.datadoghq.com` |
| EU | `https://api.datadoghq.eu` |
| US3 | `https://api.us3.datadoghq.com` |

### Gmail SMTP (one-time setup)

1. Enable 2-Step Verification on your Google account.
2. Create an App password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Add to `.env`:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
SMTP_FROM=you@gmail.com
SMTP_TO=recipient@example.com
```

---

## Workflow

### Step 1 — Extract Datadog Dashboards

For **each dashboard** defined below, run the extraction script:

```bash
python3 scripts/datadog_dashboard_extract.py \
  --url '<URL from the dashboard .md file>' \
  --output-slug <SLUG> \
  --days 2 \
  --focus "<focus terms, if any>"
```

Each dashboard writes to `output/<slug>_metric_results.json` — no files overwrite each other.

---

#### Dashboard Definitions

Each dashboard is defined in its own `.md` file under **`prompts/dashboards/`**.
These files are **gitignored** (they contain real Datadog URLs) and live on the
user's disk only. See `prompts/dashboards/_example.md` for the template.

**Important:** Skip any file whose name starts with `_` (like `_example.md`) —
those are reference templates, not real dashboards. Only process files that do
**not** start with `_`.

Read every qualifying `.md` file in that directory and execute the extraction
command from each one.

---

### Step 2 — Build the HTML report

> **UI skill:** Before hand-editing HTML/CSS, read and apply `.cursor/skills/ui-design-brain/SKILL.md`.
> Use the **Data Dashboard** design direction (Step 3 of the skill).

**Preferred:** generate the report from snapshots (after Step 1, 2C, 2D):

```bash
python3 scripts/render_daily_dashboard_html.py
```

This reads `output/catalogue_quality_metric_results.json` (Part A), `output/owner_metrics_metric_results.json` (Part B), `output/github_prs.json`, and `output/todos.json`, and writes **`daily_dashboard_report.html`** at the repo root.

To include **additional dashboards** beyond Part A/B, use the `--extra` flag:

```bash
python3 scripts/render_daily_dashboard_html.py \
  --extra "DORA Metrics:output/dora_metric_results.json"
```

Part D Actions use **`todo_report.format_view_action_html`** (View link only).

You can still hand-edit the HTML if needed; the renderer matches the scorecard layout below.

#### Report format

The report is a **focused scorecard** — no long prose, no caveats section. Use this structure:

```
Header (dark gradient):
  Title: "Daily Dashboard — <DATADOG_TEAMS> — YYYY-MM-DD (past 2 days)"
  Link to each dashboard

For each Dashboard Part (A, B, …):
  Render tiles as described in that Part's definition above.
  Generic dashboards: one tile per widget, latest value, grey tile for nulls.

Part C: PR Review Queue (if enabled)
Part D: My Queue (if enabled)

Footer: link to each dashboard, generated date
```

Style rules (carry forward from `daily_dashboard_report.html` reference):
- `background: #fff5f5; border: 2px solid #fc8181` for RED tiles
- `background: #fffff0; border: 2px solid #f6e05e` for YELLOW tiles
- `background: #fffaf0; border: 2px solid #f6ad55` for ORANGE tiles
- `background: #f0fff4; border: 2px solid #68d391` for GREEN tiles
- Big number font-size: `48px`, font-weight `800`
- Max-width `660px`, centred

### Step 2C — PR Review Queue

```bash
python3 scripts/github_prs.py
```

This writes `github_prs.json` with all open PRs where you or the team are a requested reviewer.

**Env vars used:**

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | PAT with `repo` (read) + `read:org` scopes |
| `GITHUB_ORG` | GitHub org slug (e.g. `my-org`) |
| `GITHUB_TEAM` | Team slug (e.g. `my-team`) |

Add **Part C** to the HTML report:
- If `prs` is empty → show a green "No PRs awaiting review — inbox clear" banner
- If PRs exist → show a compact table: **Repo** | **Title** (linked) | **Author** | **Age**
  - Age ≥ 5 days → red bold
  - Age 2–4 days → yellow
  - Draft PRs → show `(draft)` in muted text

### Step 2D — Todo & Reading Queue

```bash
python3 scripts/todo.py list --json > output/todos.json
```

Each JSON item includes **`view_url`**, **`type`** (`task` | `read`), and **`domain`** (`work` | `personal` | `read`).

For the Actions column HTML, use **`scripts/todo_report.format_view_action_html(item)`** — a single **View** link per row (email-safe).

**Env vars used:**

| Variable | Purpose |
|----------|---------|
| `TODOIST_API_TOKEN` | Todoist API token |
| `TODOIST_PROJECT_ID` | Project ID (auto-set by `setup`) |

Add **Part D** to the HTML report:

- Section header: **"My Queue"**
- Subsection: **Work tasks** (`type` = `task` and `domain` = `work`, or missing `domain` for backward compatibility)
- Subsection: **Personal tasks** (`type` = `task` and `domain` = `personal`)
  - Each table: **Priority** | **Title** | **Age** | **Actions**
  - **Actions:** **View** via `format_view_action_html()`.
  - Priority `high` → red row, `medium` → yellow row
  - Empty subsection → muted "No open work tasks" / "No personal tasks"
- Subsection: **Reading Queue** (items where `type` = `read`)
  - Table: **Title** (linked to article `url` if any) | **Age** | **Actions**
  - **Actions:** same — **View** opens the task in Todoist (article URL stays in the **Title** / **Link** column as today).
  - Age > 7 days → yellow highlight
  - If no reading items → show "Reading queue empty" in muted text
- If `todos.json` is empty or the script fails → show a green "Queue clear" banner

### Step 3 — Send the report

```bash
python3 scripts/send_report_smtp.py \
  "Daily dashboard — team-a — $(date +%Y-%m-%d)" \
  daily_dashboard_report.html
```

Confirm `Sent to <SMTP_TO>`. Do not mark the task complete until the send succeeds.

---

## Script reference

The extraction script is `scripts/datadog_dashboard_extract.py`. With `--output-slug`, it saves **`output/<slug>_metric_results.json`** (per-query series + latest values) alongside `<slug>_dashboard.json` and `<slug>_dashboard_extracted_queries.json`. Each dashboard gets its own set of output files — no need to copy/rename.

The HTML builder is **`scripts/render_daily_dashboard_html.py`** (optional args: `--part-a`, `--part-b`, `--extra`, `--prs`, `--todos`, `--out`).

**CLI arguments (`datadog_dashboard_extract.py`):**

| Argument | Default | Purpose |
|----------|---------|--------|
| `--url` | | Dashboard URL (preferred — pass directly) |
| `--url-env` | | Env var name holding the dashboard URL (fallback) |
| `--days N` | `0` | Override time window to past N days (0 = use URL timestamps) |
| `--focus "a,b"` | `""` | Comma-separated title substrings to highlight with ★ in console output |
| `--output-slug` | `""` | Prefix for output files (e.g. `owner_metrics` → `owner_metrics_metric_results.json`) |

**DATADOG_TEAMS behaviour:**
- Replaces all `tpl_var_team[*]` URL params with the listed teams.
- Injects `team:<value>` into every metric query, replacing the `$team` template variable default (`team:*`).
- Single team: `team-a` → `team:team-a`
- Multiple teams: `team-a,team-b` → `team:(team-a OR team-b)`

**Time window precedence:** `--days` flag → URL `from_ts`/`to_ts` → 30-day fallback.
When `live=true` is in the URL, `to_ts` is snapped to `now` regardless.

---

## Important caveats

1. The script runs **base metric queries** — it does not re-evaluate Datadog formula arithmetic client-side. Values may differ slightly from dashboard UI totals.
2. For Owner Metrics, many widgets may use non-metric sources (logs, APM, RUM). Those are skipped; note any gaps in the report tile with `—`.
3. Template variables other than `$team` (e.g. `$criticality`) remain at their dashboard defaults unless you add more overrides.
