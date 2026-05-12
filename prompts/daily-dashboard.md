# Daily Dashboard Review

## Overview

This is an execution task, not a review task.
Do the steps now in the workspace. Do not stop after analysis or suggestions.

Run **all Datadog dashboards defined below**, produce a **single focused HTML report**, and email it.

**Time window: past 7 days for all dashboards** (use `--days 7`).

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
| `TODOIST_API_TOKEN` | no | Todoist API token (for My Queue: todo / reading queue) |
| `TODOIST_PROJECT_ID` | no | Auto-set by `python scripts/todo.py setup` |
| `STAKEHOLDERS` | no | Comma-separated **full names or emails** to track via Glean MCP (for Stakeholder Pulse). Empty/unset skips Step 2F. Prefer `Jane Doe,john.smith@xyz.com.au` over single first names — disambiguation matters. Soft-cap at ~5 names to keep agent latency reasonable. |

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
  --days 7 \
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

The renderer is **fully data-driven by `prompts/dashboards/*.md`**. For each
qualifying file (skipping `_*.md` templates) it reads the matching
`output/<slug>_metric_results.json` snapshot and renders one Part section.
It also reads `output/github_prs.json` and `output/todos.json` for the PR
Queue and My Queue sections, and writes **`daily_dashboard_report.html`** at
the repo root.

Section letters (Part A, B, C, …) are assigned **dynamically** in this
order, skipping any that have no content:

1. Each dashboard `.md` (sorted by filename)
2. Each `--extra LABEL:FILE` argument (CLI order)
3. PR Review Queue
4. My Queue
5. Extras (`prompts/extras/*.md`)
6. Stakeholder Pulse (`prompts/stakeholders/*.md`, when `STAKEHOLDERS` is set)

So with zero dashboard `.md` files, PR Queue becomes Part A. With two
dashboards, PR Queue becomes Part C, and so on.

For **one-off snapshots** that aren't worth a permanent `.md` file, use
`--extra`:

```bash
python3 scripts/render_daily_dashboard_html.py \
  --extra "DORA Metrics:output/dora_metric_results.json"
```

Each dashboard renders as one tile per unique widget — latest value per
widget, grey tile for nulls. No per-widget colouring or thresholds in the
shipped library; that's intentionally kept generic.

My Queue Actions use **`todo_report.format_view_action_html`** (View link only).

You can still hand-edit the HTML if needed; the renderer matches the scorecard layout below.

#### Report format

The report is a **focused scorecard** — no long prose, no caveats section. Use this structure:

```
Header (dark gradient):
  Title: "Daily Dashboard — <DATADOG_TEAMS> — YYYY-MM-DD (past 7 days)"
  One link per discovered dashboard

Dashboards (Part A, B, …):
  One section per *.md in prompts/dashboards/ (sorted by filename).
  One tile per unique widget, latest value, grey tile for nulls.

PR Review Queue (next letter)
My Queue (next letter)
Extras (next letter — only if any *.md files in prompts/extras/)
Stakeholder Pulse (next letter — only if STAKEHOLDERS is set and any *.md in prompts/stakeholders/)

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

The renderer adds a **PR Review Queue** section (Part letter depends on how many dashboard sections precede it — see Step 2 ordering above):
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

The renderer adds a **My Queue** section (Part letter depends on dashboards and PR section — see Step 2 ordering above):

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

### Step 2E — Extras plugin (drop-in `.md` files)

Any `*.md` file dropped into **`prompts/extras/`** is rendered as a card under
**Extras** in the report (section title includes the dynamic Part letter). Files starting with `_` (like
`_example.md`) are reference templates and are skipped.

No code changes or CLI flags are needed — the renderer auto-discovers the
folder. Override the location if needed:

```bash
python3 scripts/render_daily_dashboard_html.py --extras-dir prompts/extras
```

Each file's first `# Heading` becomes the card title; the rest of the body
is rendered with a small markdown subset (headings, bold/italic, inline
code, lists, links, fenced code blocks). If a file has no `# Heading`, the
filename (without `.md`) is used as the title.

If `prompts/extras/` is empty (or only contains `_*.md` templates), the Extras
section is omitted entirely.


### Step 2F — Stakeholder Pulse (Slack via Glean MCP)

Track what a small set of named stakeholders have been working on in Slack
over the past 7 days. Uses the **Glean MCP server** (already configured in
`.cursor/mcp.json` as `Glean`) — no Slack token required.

**Skip this entire step if `STAKEHOLDERS` is empty or unset.**

**Procedure:**

1. **Clean stale cards.** Delete every file in `prompts/stakeholders/`
   whose name does **not** start with `_`. This guarantees that removing a
   name from `STAKEHOLDERS` removes the card on the next run.

2. **For each name** in `STAKEHOLDERS` (split on `,`, strip whitespace,
   skip empties):

   a. **Inspect the Glean MCP `search` tool schema first** (read parameters
      before calling). Typical filters for Slack-only, last 7 days:
      - `app`: `"slack"`
      - `from`: `"<name>"` (full name or email)
      - `updated`: `"past_week"` (or `after` / `before` as `YYYY-MM-DD`)
      - `query`: `"*"` or a few discriminative keywords (required)
      - `sort_by_recency`: `true` when you want newest hits first

   b. **Summarize** the returned hits into exactly three bullets:
      - **Themes:** one sentence — what is this person mostly engaged in?
      - **Notable:** one sentence — most useful thread/decision/question,
        with a markdown link.
      - **Top links:** up to 3 markdown links (channels, threads, key
        messages), comma-separated on a single bullet.

   c. **Write** to `prompts/stakeholders/<slug>.md` where `<slug>` is the
      lowercased name with spaces replaced by hyphens (e.g. `Jane Doe` →
      `jane-doe.md`). Use this exact format:

      ```
      # <Display Name>

      - **Themes:** ...
      - **Notable:** [thread title](url) — short context
      - **Top links:** [#chan-name](url), [thread](url), [message](url)
      ```

   d. **No-activity case.** If Glean returns no Slack hits for the person
      in the window, write a single bullet instead:

      ```
      # <Display Name>

      - No Slack activity in the last 7 days.
      ```

3. **Renderer is automatic.** `render_daily_dashboard_html.py`
   auto-discovers `prompts/stakeholders/*.md` and emits a dynamically
   lettered **Stakeholder Pulse** section (same card styling as Extras).
   Override the folder with `--stakeholders-dir` if needed.

**Scope caveats to keep in mind (and surface in cards if relevant):**

- Glean only indexes **public Slack channels** that it has been granted
  access to. DMs and private channels will not appear.
- Glean indexes on a delay (often a few hours), so very recent activity
  may be missing until the next run.

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

The HTML builder is **`scripts/render_daily_dashboard_html.py`**. Useful optional args: `--out`, `--dashboards-dir`, `--output-dir`, `--prs`, `--todos`, `--extras-dir`, `--stakeholders-dir`, and repeatable `--extra "Label:path/to_metric_results.json"`.

**CLI arguments (`datadog_dashboard_extract.py`):**

| Argument | Default | Purpose |
|----------|---------|--------|
| `--url` | | Dashboard URL (preferred — pass directly) |
| `--url-env` | | Env var name holding the dashboard URL (fallback) |
| `--days N` | `0` | Override time window to past N days (0 = use URL timestamps) |
| `--focus "a,b"` | `""` | Comma-separated title substrings to highlight with ★ in console output |
| `--output-slug` | `""` | Prefix for output files (e.g. `my_dashboard` → `my_dashboard_metric_results.json`) |

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
2. Widgets sourced from logs, APM, or RUM (rather than metrics) are skipped; the corresponding tile will show `—`.
3. Template variables other than `$team` (e.g. `$criticality`) remain at their dashboard defaults unless you add more overrides.
