# Daily dashboard workflow

## Overview

Run **all Datadog dashboards** defined under
`~/.engineering-pulse-data/dashboards/`, produce a **single
focused HTML report**, archive it to the report calendar, and notify and/or email per `DELIVERY`.

## Problems box — always deliver a report

Start every run with:

```bash
python3 scripts/run_issues.py start --type pulse
```

(Scheduled runs already started the list and checked MCP sign-in; `start` keeps that.)

When a step fails or is skipped for a reason the user has to fix (MCP not signed in, a
search or extract errors, no dashboards), record it and **carry on with the other steps**:

```bash
python3 scripts/run_issues.py add --type pulse --source github \
  --message "GitHub MCP search failed: <short reason>" [--server <MCP server name>]
```

Use one of these `--source` names: `datadog`, `github`, `glean`, `todoist`, `atlassian`.
The box keeps one row per source, so first check `python3 scripts/run_issues.py show
--type pulse` and skip problems already listed (preflight records MCP sign-in and
missing dashboards before you start). Pass `--server` only when signing in to that MCP
server would fix it; the report then shows a **Sign in** button. Never stop early: render with whatever data this run produced
and deliver. `deliver_report.py send` puts the recorded problems in a red box at the top
of the report.

---

## Step 1 — Extract Datadog Dashboards

Use **Datadog MCP** (see [datadog-mcp-extract.md](datadog-mcp-extract.md)). For **each**
dashboard in `~/.engineering-pulse-data/dashboards/`, produce
`output/<slug>_metric_results.json` via MCP + local helper scripts.

Read every qualifying `.md` in `~/.engineering-pulse-data/dashboards/`; see
`prompts/dashboards/_example.md` for the file format.

---

## Step 2 — Build the HTML report

After Step 1, 2C, 2D, and (if applicable) 2F:

```bash
python3 scripts/todo.py list --json > output/todos.json                  # Step 2D (if token set)
python3 scripts/github_prs.py --from-mcp output/github_mcp_prs.json      # Step 2C
python3 scripts/render_daily_dashboard_html.py
```

Writes `output/daily_dashboard_report.html` by default (override with `--out`).

The renderer reads `~/.engineering-pulse-data/dashboards/*.md` + matching
`output/<slug>_metric_results.json`, `output/github_prs.json`, `output/todos.json`,
`~/.engineering-pulse-data/extras/*.md`, and
`output/stakeholders/*.md` when `STAKEHOLDERS` is set.

**Section order (dynamic Part letters):**

1. Each dashboard `.md` (sorted by filename)
2. Each `--extra LABEL:FILE` (CLI)
3. PR Review Queue
4. My Queue
5. Extras (`~/.engineering-pulse-data/extras/*.md`)
6. Stakeholder Pulse (only if `STAKEHOLDERS` non-empty)

One-off snapshot without a dashboard file:

```bash
python3 scripts/render_daily_dashboard_html.py \
  --extra "DORA Metrics:output/dora_metric_results.json"
```

#### Report format

Focused scorecard — no long prose. Header: `Daily Dashboard — <label> — YYYY-MM-DD (past 7 days)` where `<label>` is the first `tpl_var_team` from a dashboard URL, else the first dashboard title.
One tile per widget (latest value; grey for null). Tile colours if hand-editing:

- RED: `#fff5f5` / `#fc8181`
- YELLOW: `#fffff0` / `#f6e05e`
- ORANGE: `#fffaf0` / `#f6ad55`
- GREEN: `#f0fff4` / `#68d391`
- Big numbers: `48px`, weight `800`; max-width `660px`

---

## Step 2C — PR Review Queue

Use **GitHub MCP** (no token needed):

1. `get_me` → your GitHub login.
2. `search_pull_requests` with `query: "is:open review-requested:@me"`, `perPage: 100`,
   and `fields: ["number", "title", "draft", "html_url", "user", "labels", "created_at",
   "updated_at", "repository_url"]`. If more than 100 results, fetch `page: 2` too (stop at
   200, the same cap as the token path).
3. If `GITHUB_TEAM` is set (`org/team`; legacy: bare team slug plus `GITHUB_ORG`), run the
   same search with `query: "is:open team-review-requested:<org>/<team>"`.
4. Save every response unchanged to `output/github_mcp_prs.json`:
   `{"username": "<login>", "results": [<response>, <response>, ...]}`, then run:

```bash
python3 scripts/github_prs.py --from-mcp output/github_mcp_prs.json
```

The script dedupes the searches, drops Renovate PRs and sorts newest first.

**Fallback** — only if GitHub MCP is not available in this session and `GITHUB_TOKEN` is
set in `.env`: run `python3 scripts/github_prs.py` (GraphQL with the token). If neither is
available, run `rm -f output/github_prs.json`; the report then says "PR data not fetched"
instead of showing stale PRs.

Writes `output/github_prs.json`. Renderer shows green “inbox clear” or table:
**Repo** | **Title** | **Author** | **Age** (red ≥5d, yellow 2–4d, draft muted).

---

## Step 2D — Todo & Reading Queue

Only when `TODOIST_API_TOKEN` is set in `.env`. Otherwise run `rm -f output/todos.json`;
the report then leaves out My Queue.

```bash
python3 scripts/todo.py list --json > output/todos.json
```

Renderer adds **My Queue**: work tasks, personal tasks, reading queue. Actions use
`todo_report.format_view_action_html` (View link only).

---

## Step 2E — Extras

Drop `*.md` into `~/.engineering-pulse-data/extras/`. First `# Heading` = card title.
Override with `--extras-dir`.

---

## Step 3 — Deliver the report

```bash
python3 scripts/deliver_report.py send --type pulse \
  --subject "Daily dashboard — $(date +%Y-%m-%d)" \
  output/daily_dashboard_report.html
```

Always archives the report to `~/.engineering-pulse-data/reports/` (calendar at
`~/.engineering-pulse-data/reports/index.html`),
then follows `DELIVERY` in `.env`: `notify` (default, macOS notification), `email`
(SMTP via `send_report_smtp.py`), `both`, or `none` (archive only).

Confirm `Archived …`, plus `Notified via …` and/or `Sent to <SMTP_TO>` for the
configured mode. Do not mark complete until the command exits 0. Run it once per
report; a repeat with identical content is skipped.

Do not open the report or calendar automatically. The macOS notification is clickable;
the user chooses when to open the report.
