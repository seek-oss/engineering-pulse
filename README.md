# Engineering Pulse

A **Cursor prompt-driven** daily engineering health dashboard for **engineering teams** — visibility into systems, delivery, and review load in one place.

Pulls live data from **Datadog**, **GitHub**, and **Todoist**, generates a colour-coded HTML scorecard, and emails it — triggered manually in Cursor or automatically on a schedule. Also keeps a **task list** and **reading queue** in Todoist.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/harryzhu2011/engineering-pulse/main/web-install.sh | bash
```

Use **`web-install.sh`**, not `install.sh`, in the pipe — it clones the repo then runs `install.sh` from disk (see **Setup → Option A** for why). The installer will:
- Clone the repo to `~/.engineering-pulse` (override with `INSTALL_DIR` if you want a different path)
- Set up a Python virtual environment
- Copy `.env.example` → `.env` if `.env` is missing (then **edit `.env`** with your keys)
- Print where to edit prompts, customise dashboards, and adjust the LaunchAgent schedule
- Schedule the report at **08:00, 10:00 and 18:30** via macOS LaunchAgent (override times with `SCHEDULE_HOURS` when running the installer)

> **Prerequisites:** Python 3.11+, `git`, and the [Cursor](https://cursor.sh) `agent` CLI in your PATH.

---

## What it produces

```
┌─────────────────────────────────────────────────────┐
│  Daily Dashboard — my-team — 2026-03-20 (past 2d)  │
├──────────────────────────────────────────────────────┤
│  Part A — Catalogue Quality                         │
│  ┌──────────────┬─────────────────┬───────────────┐ │
│  │ 14 Incomplete│ 4 No Seal       │ 3 No Capabil. │ │
│  │  (RED)       │  (YELLOW)       │  (ORANGE)     │ │
│  └──────────────┴─────────────────┴───────────────┘ │
│                                                      │
│  Part B — Owner Metrics                             │
│  Tech Fitness 69% · Catalogue 73% · Security 0     │
│  Exercised 88% · Systems Assessed 13               │
│                                                      │
│  Part C — PR Review Queue  (21 open, 14 red)       │
│  Newest-first, renovate bots excluded              │
│                                                      │
│  Part D — My Queue                                  │
│  Tasks: 2 open (1 high, 1 low)                     │
│  Reading Queue: 1 article                           │
└──────────────────────────────────────────────────────┘
```

---

## Architecture

```
prompts/
  daily-dashboard.md        ← Cursor prompt (the entry point)
  add-dashboard.md          ← interactive command to add a new dashboard
  dashboards/
    catalogue_quality.md    ← shipped: Part A
    owner_metrics.md        ← shipped: Part B
    custom_*.md             ← your dashboards (created via /add-dashboard)

scripts/
  datadog_dashboard_extract.py   ← fetches Datadog metrics via API
  render_daily_dashboard_html.py ← builds the HTML scorecard
  github_prs.py                  ← fetches PR review queue via GitHub GraphQL
  todo.py                        ← Todoist-backed tasks & reading queue
  send_report_smtp.py            ← sends HTML report via SMTP

output/                     ← gitignored; all generated files land here
  catalogue_quality_metric_results.json
  owner_metrics_metric_results.json
  github_prs.json
  ...
```

All credentials come from `.env` — never hardcoded.

---

## Setup

### Option A — one-liner installer (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/harryzhu2011/engineering-pulse/main/web-install.sh | bash
```

This bootstrap only clones/updates the repo and runs `install.sh` **from disk**. Do **not** use `curl …/install.sh | bash`: your shell would read the installer from stdin (not a real TTY), and GitHub’s raw CDN can briefly serve an older `install.sh` than `git clone` gets — both caused confusing failures in the past.

**Alternative:** `curl -fsSL …/install.sh -o /tmp/ep-install.sh && bash /tmp/ep-install.sh`

The installer handles cloning (or update), Python venv, `.env` seeding, runner + LaunchAgent, and prints next-step paths.

### Option B — manual setup

```bash
git clone https://github.com/harryzhu2011/engineering-pulse.git ~/.engineering-pulse
cd ~/.engineering-pulse
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
```

You need:
- **Datadog** — API key + App key + two dashboard URLs
- **GitHub** — Personal Access Token with `repo` (read) + `read:org` scopes
- **Gmail SMTP** — App Password (2FA must be enabled on your Google account)
- **Todoist** *(optional)* — API token from Settings → Integrations → Developer

### Running the dashboard

**Manually in Cursor** — open a chat and type:
```
@prompts/daily-dashboard.md
```

**From the terminal:**
```bash
make run          # run now (foreground)
make run-bg       # run now (background)
make logs         # tail the log
make status       # check the schedule
make update       # pull latest + reinstall deps
make help         # list all targets
```

**On a schedule** — the installer sets up a macOS LaunchAgent that runs at 08:00, 10:00, and 18:30 automatically.

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

Or use natural language in Cursor: `@prompts/todo.md remind me to review the EKS upgrade`

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
  --days 2

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
   @prompts/add-dashboard.md add my DORA dashboard at https://app.datadoghq.com/dashboard/xyz-123, I care about deploy rate
   ```

2. The command will:
   - Discover all widgets in the dashboard
   - Let you pick which ones to include
   - Generate colouring rules
   - Save a new file at `prompts/dashboards/custom_dora.md` with the URL embedded

No `.env` changes needed — dashboard URLs are stored directly in the `.md` files.

Next time the daily dashboard runs, it picks up the new file automatically.

User-added dashboards are prefixed with `custom_` to avoid collisions with shipped files.

---

## Upgrading

To upgrade to a new release:

```bash
# If installed via web-install:
curl -fsSL https://raw.githubusercontent.com/harryzhu2011/engineering-pulse/main/web-install.sh | bash

# If cloned manually:
git pull --ff-only
pip install -r requirements.txt
```

**Your custom dashboards are safe.** User-added files (`prompts/dashboards/custom_*.md`) are separate from shipped files, so `git pull` won't cause merge conflicts. Your `.env` is also preserved.

| What | Upgraded? | Your changes safe? |
|------|-----------|--------------------|
| Shipped dashboards (`catalogue_quality.md`, `owner_metrics.md`) | Yes | N/A (don't edit these) |
| Your custom dashboards (`custom_*.md`) | No (untouched) | Yes |
| Scripts (`scripts/*.py`) | Yes | N/A |
| `.env` (your credentials) | No (untouched) | Yes |
| `daily-dashboard.md` (workflow) | Yes | N/A (don't edit) |

---

## License

MIT — see [LICENSE](LICENSE).
