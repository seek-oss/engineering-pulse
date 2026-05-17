# Engineering Pulse

[![CI](https://github.com/seek-oss/engineering-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/seek-oss/engineering-pulse/actions/workflows/ci.yml)

A **Cursor prompt-driven** daily engineering health dashboard for **engineering teams** — visibility into systems, delivery, and review load in one place.

Pulls live data from **Datadog**, **GitHub**, and **Todoist**, generates a colour-coded HTML scorecard, and emails it — triggered manually in Cursor or automatically on a schedule. Also keeps a **task list** and **reading queue** in Todoist. Optionally adds **Stakeholder Pulse** — per-person Slack summaries (via Glean MCP) for names you list in `.env`.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/seek-oss/engineering-pulse/main/web-install.sh | bash
```

Use **`web-install.sh`**, not `install.sh`, in the pipe — it clones the repo then runs `install.sh` from disk (see **Setup → Option A** for why). The installer will:
- Clone the repo to `~/.engineering-pulse` (override with `INSTALL_DIR` if you want a different path)
- Set up a Python virtual environment
- Copy `.env.example` → `.env` if `.env` is missing (then **edit `.env`** with your keys)
- Print where to edit prompts, customise dashboards, and adjust the LaunchAgent schedule
- Schedule the report at **09:00, 12:00 and 16:00 Mon–Fri** via macOS LaunchAgent (override times with `SCHEDULE_HOURS` when running the installer)

> **Prerequisites:** Python 3.11+, `git`, and the [Cursor](https://cursor.sh) `agent` CLI in your PATH.

See [CONTRIBUTING.md](CONTRIBUTING.md) for running tests and opening pull requests.

---

## What it produces

```
┌─────────────────────────────────────────────────────┐
│  Daily Dashboard — my-team — 2026-03-20 (past 7d)  │
├──────────────────────────────────────────────────────┤
│  Part A — <Your Dashboard #1>                       │
│  ┌──────────────┬─────────────────┬───────────────┐ │
│  │  Widget 1    │  Widget 2       │  Widget 3     │ │
│  │  latest val  │  latest val     │  latest val   │ │
│  └──────────────┴─────────────────┴───────────────┘ │
│                                                      │
│  Part B — <Your Dashboard #2>                       │
│  (one tile per widget, populated automatically)     │
│                                                      │
│  Part C — PR Review Queue  (21 open, 14 red)       │
│  Newest-first, renovate bots excluded              │
│                                                      │
│  Part D — My Queue                                  │
│  Tasks: 2 open (1 high, 1 low)                     │
│  Reading Queue: 1 article                           │
│                                                      │
│  Part E — Extras (optional)                         │
│  Drop *.md files in prompts/extras/                 │
│                                                      │
│  Part F — Stakeholder Pulse (optional)              │
│  One card per name in STAKEHOLDERS (.env)           │
└──────────────────────────────────────────────────────┘
```

Section letters (A, B, C, …) are assigned **dynamically**: dashboards from
`prompts/dashboards/*.md` come first (sorted by filename), then PR Queue,
My Queue, Extras, and (when configured) **Stakeholder Pulse** fill the
remaining letters. With zero dashboards configured, PR Queue is Part A.
Stakeholder Pulse is omitted entirely when `STAKEHOLDERS` is empty or unset.

---

## Agent skill (multi-harness)

The daily workflow lives in a portable **[Agent Skill](https://agentskills.io/specification)**:

- **Canonical:** [`skills/engineering-pulse/SKILL.md`](skills/engineering-pulse/SKILL.md) + [`references/`](skills/engineering-pulse/references/)
- **Install matrix:** [`skills/README.md`](skills/README.md) (Cursor, Claude Code, skills.sh, ai-toolkit)
- **Harness adapters:** [`harness/`](harness/) — thin Cursor / Claude Code / Pi entrypoints
- **Repo context:** [`AGENTS.md`](AGENTS.md) — always-on rules for agents in this tree

**Run in Cursor:** `/daily-dashboard` — or scheduled via `make run` / LaunchAgent (see below).

## Architecture

```
skills/engineering-pulse/   ← publishable Agent Skill (SKILL.md + references/)
harness/                    ← per-harness commands / install notes
AGENTS.md                   ← repo-wide agent context

prompts/                    ← user workspace data only (no workflow shims)
  dashboards/
    _example.md             ← format reference (tracked by git, skipped by agent)
    custom_*.md             ← your dashboards (local only, gitignored)
  extras/                   ← drop-in report cards (gitignored except _example)
  _stakeholder-card-example.md

scripts/
  datadog_dashboard_extract.py   ← fetches Datadog metrics via API
  render_daily_dashboard_html.py ← builds the HTML scorecard
  extras_plugin.py               ← discovers + renders extras & stakeholder *.md cards
  github_prs.py                  ← fetches PR review queue via GitHub GraphQL
  todo.py                        ← Todoist-backed tasks & reading queue
  send_report_smtp.py            ← sends HTML report via SMTP

output/                     ← gitignored; all generated files land here
  <slug>_metric_results.json
  github_prs.json
  todos.json
  stakeholders/*.md         ← Glean-generated Stakeholder Pulse cards
  ...
```

All credentials come from `.env` — never hardcoded.

---

## Setup

### Option A — one-liner installer (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/seek-oss/engineering-pulse/main/web-install.sh | bash
```

This bootstrap only clones/updates the repo and runs `install.sh` **from disk**. Do **not** use `curl …/install.sh | bash`: your shell would read the installer from stdin (not a real TTY), and GitHub’s raw CDN can briefly serve an older `install.sh` than `git clone` gets — both caused confusing failures in the past.

**Alternative:** `curl -fsSL …/install.sh -o /tmp/ep-install.sh && bash /tmp/ep-install.sh`

The installer handles cloning (or update), Python venv, `.env` seeding, runner + LaunchAgent, and prints next-step paths.

### Option B — manual setup

```bash
git clone https://github.com/seek-oss/engineering-pulse.git ~/.engineering-pulse
cd ~/.engineering-pulse
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
```

You need:
- **Datadog** — API key + App key + dashboard URLs
- **GitHub** — Personal Access Token with `repo` (read) + `read:org` scopes
- **Gmail SMTP** — App Password (2FA must be enabled on your Google account)
- **Todoist** *(optional)* — API token from Settings → Integrations → Developer
- **Glean MCP** *(optional)* — for Stakeholder Pulse today (readonly Slack token support planned); configure in Cursor, then set `STAKEHOLDERS` in `.env`

Then add your dashboards using the interactive command in Cursor:
```
/add-dashboard add my dashboard at https://app.datadoghq.com/dashboard/...
```

See `prompts/dashboards/_example.md` for the file format reference.
Dashboard files are **gitignored** so your Datadog URLs stay local.

### Running the dashboard

**Manually in Cursor** — `/daily-dashboard` (or ask the agent to run the **engineering-pulse** skill).

**From the terminal** (`agent -p` uses the same skill as the schedule):
```bash
make run          # run now (foreground)
make run-bg       # run now (background)
make logs         # tail the log
make status       # check the schedule
make update       # pull latest + reinstall deps
make help         # list all targets
```

**On a schedule** — the installer sets up a macOS LaunchAgent (default 9:00, 12:00, 16:00 Mon–Fri). After upgrading the repo, re-run `bash install.sh` from `~/.engineering-pulse` so `~/bin/run-daily-dashboard.sh` points at `skills/engineering-pulse/SKILL.md`.

---

## Configuration reference

| Variable | Required | Description |
|---|---|---|
| `DD_API_KEY` | yes | Datadog API key |
| `DD_APP_KEY` | yes | Datadog Application key |
| `DD_SITE` | no | Datadog API host (default: `https://api.datadoghq.com`) |
| `DATADOG_TEAMS` | no | Comma-separated team slugs — filters all queries |
| `GITHUB_TOKEN` | yes | PAT with `repo` + `read:org` scopes |
| `GITHUB_ORG` | yes | GitHub org slug |
| `GITHUB_TEAM` | yes | Team slug for PR review queue |
| `SMTP_USER` | yes | Gmail address |
| `SMTP_PASSWORD` | yes | Gmail App Password (16 chars) |
| `SMTP_FROM` | yes | Sender address |
| `SMTP_TO` | yes | Recipient address |
| `TODOIST_API_TOKEN` | no | Todoist API token (for todo / reading queue) |
| `TODOIST_PROJECT_ID` | no | Auto-set by `python scripts/todo.py setup` |
| `STAKEHOLDERS` | no | Comma-separated full names or emails for **Stakeholder Pulse** (via Glean MCP in Cursor). Empty/unset skips the section and deletes generated cards. Prefer `Jane Doe,john.smith@example.com` over first names only. |

See `.env.example` for the full template.

---

## Todo list & reading queue

Backed by **Todoist** — works on your phone via the Todoist app.

```bash
# One-time setup (creates project + sections in Todoist)
python3 scripts/todo.py setup

# Add tasks (default section **Tasks** = work; use --domain personal for life stuff)
python3 scripts/todo.py add "Review EKS upgrade proposal" --priority high
python3 scripts/todo.py add "Book dentist" --domain personal
python3 scripts/todo.py add "Fowler article" --type read --url "https://..."

# List open items (work + personal + reading; filter with --domain / --type)
python3 scripts/todo.py list

# Mark done / cancel
python3 scripts/todo.py done <task-id> --comment "Merged"
python3 scripts/todo.py cancel <task-id> --comment "No longer needed"
```

Or use `/todo` in Cursor: `remind me to review the EKS upgrade`

### Daily dashboard HTML

After running both Datadog extractions, GitHub PRs, and `todo.py list --json`:

```bash
python3 scripts/render_daily_dashboard_html.py
```

To include custom dashboards beyond Part A/B:

```bash
python3 scripts/render_daily_dashboard_html.py \
  --extra "DORA Metrics:output/custom_dora_metric_results.json"
```

### View from the daily email

Export the queue for the HTML report with:

```bash
python3 scripts/todo.py list --json > output/todos.json
```

Each row has **`view_url`** (Todoist on the web). For Part D Actions, use **`format_view_action_html()`** in `scripts/todo_report.py` — one **View** link per task / reading item.

---

## Running scripts directly

```bash
# Extract Datadog metrics for a dashboard
python3 scripts/datadog_dashboard_extract.py \
  --url 'https://app.datadoghq.com/dashboard/abc-123/my-dashboard?...' \
  --output-slug my_dashboard \
  --days 7

# Fetch GitHub PR review queue
python3 scripts/github_prs.py

# Send a report
python3 scripts/send_report_smtp.py "My Subject" output/daily_dashboard_report.html
```

---

## Adding a new Datadog dashboard

You can add any Datadog dashboard to the daily report without editing existing files:

1. **Run the add-dashboard command in Cursor:**
   ```
   /add-dashboard add my DORA dashboard at https://app.datadoghq.com/dashboard/xyz-123, I care about deploy rate
   ```

2. The command will:
   - Discover all widgets in the dashboard
   - Let you pick which ones to include
   - Generate colouring rules
   - Save a new file at `prompts/dashboards/custom_dora.md` with the URL embedded

Next time the daily dashboard runs, it picks up the new file automatically.

User-added dashboards are prefixed with `custom_` by convention to keep things organised.

---

## Stakeholder Pulse (optional)

Track what a small set of **named stakeholders** have been doing in **Slack**
over the past 7 days. The daily dashboard agent (Step 2F in
[`skills/engineering-pulse/references/stakeholder-pulse.md`](skills/engineering-pulse/references/stakeholder-pulse.md))
writes one markdown card per name in `output/stakeholders/`; the HTML report picks
them up when `STAKEHOLDERS` is set in `.env`.

### Slack data: two possible approaches

| Approach | Status | Best for |
|----------|--------|----------|
| **Glean MCP** in Cursor | **Supported today** | Orgs that already use Glean for Slack search — no Slack token in `.env` |
| **Read-only Slack token** | *Not implemented yet* | Orgs without Glean; a bot/user token with read-only channel history could feed the same card format |

**Today only Glean MCP is wired up** (Step 2F). A direct Slack API path may be
added later for teams that prefer a readonly token over enterprise search.

### Enable (Glean MCP)

1. **Glean MCP** — add/configure the Glean server in your [Cursor MCP settings](https://docs.cursor.com/context/mcp) (not shipped in this repo).
2. **`STAKEHOLDERS` in `.env`** — comma-separated names or emails, e.g.  
   `STAKEHOLDERS=Jane Doe,john.smith@example.com`
3. Run the dashboard in Cursor: `/daily-dashboard`

### What happens each run

- The agent deletes stale `output/stakeholders/*.md`, then writes one file per
  name: `output/stakeholders/<slug>.md` (same gitignored `output/` tree as PRs
  and todos).
- Each card has three bullets: **Themes**, **Notable** (with link), **Top links**.
- The HTML renderer reads `STAKEHOLDERS` from `.env`:
  - **Empty/unset** — no Stakeholder Pulse section; non-template cards are removed.
  - **Non-empty** — section appears (placeholder if Step 2F has not run yet).

Cards live under **`output/stakeholders/`** (gitignored with the rest of
`output/`). You normally do not edit them by hand — change `STAKEHOLDERS` or
re-run the dashboard.

Override the folder with `--stakeholders-dir <path>` on
`render_daily_dashboard_html.py`.

### Scope caveats

- Glean typically indexes **public Slack channels** it has access to — not DMs or
  private channels.
- Indexing can lag by a few hours; very recent messages may show up on the next run.
- Keep the list small (~5 names) to keep agent latency reasonable.

See `prompts/_stakeholder-card-example.md` for the expected card format.

---

## Adding extra tasks (drop-in plugin folder)

Beyond Datadog dashboards, you can drop **any markdown file** into
`prompts/extras/` and it will appear as a card under **Part E — Extras** in
the next report. No code changes, no CLI flags — just write the file and run
the dashboard.

```
prompts/extras/
  release-checklist.md   ← becomes a card titled from its first `# Heading`
  oncall-notes.md
  ...
```

Per-file format:

- The first `# Heading` is the **card title**. If absent, the filename
  (without `.md`) is used.
- Everything below is the **body**, rendered with a small markdown subset:
  headings, **bold**, *italic*, `inline code`, bullet/numbered lists,
  [links](https://example.com), and fenced code blocks.
- Files whose name starts with `_` (e.g. `_example.md`) are treated as
  reference templates and skipped.
- The folder is gitignored (except `_example.md`) so your notes stay local.

If `prompts/extras/` is empty (or only contains templates), Part E is
omitted from the report. Override the folder with
`--extras-dir <path>` on `render_daily_dashboard_html.py`.

See `prompts/extras/_example.md` for a working template.

---

## Upgrading

To upgrade to a new release:

```bash
# If installed via web-install:
curl -fsSL https://raw.githubusercontent.com/seek-oss/engineering-pulse/main/web-install.sh | bash

# If cloned manually:
git pull --ff-only
pip install -r requirements.txt
```

**Your dashboards and credentials are safe.** All dashboard definition files
under `prompts/dashboards/` (except `_example.md`) are gitignored — they live
on your disk only and are never touched by `git pull`.

| What | Upgraded? | Your changes safe? |
|------|-----------|--------------------|
| Example template (`_example.md`) | Yes | N/A (reference only) |
| Your dashboard files (`*.md` in `prompts/dashboards/`) | No (gitignored) | Yes |
| Your extras files (`*.md` in `prompts/extras/`) | No (gitignored) | Yes |
| Stakeholder Pulse cards (`output/stakeholders/*.md`) | No (gitignored) | Yes |
| `STAKEHOLDERS` in `.env` | No (untouched) | Yes |
| Scripts (`scripts/*.py`) | Yes | N/A |
| `.env` (your credentials) | No (untouched) | Yes |
| `skills/engineering-pulse/` (workflow) | Yes | N/A (don't edit) |

