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

scripts/
  datadog_dashboard_extract.py   ← fetches Datadog metrics via API
  github_prs.py                  ← fetches PR review queue via GitHub GraphQL
  todo.py                        ← Todoist-backed tasks & reading queue
  send_report_smtp.py            ← sends HTML report via SMTP

output/                     ← gitignored; all generated files land here
  daily_dashboard_report.html
  github_prs.json
  dashboard.json
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
| `DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY` | yes | URL of your Catalogue Quality dashboard |
| `DATADOG_DASHBOARD_URL_OWNER_METRICS` | yes | URL of your Owner Metrics dashboard |
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

After running both Datadog extractions (copy `output/dashboard_metric_results.json` → `part_a_metric_results.json` between runs), GitHub PRs, and `todo.py list --json`:

```bash
python3 scripts/render_daily_dashboard_html.py
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
  --url-env DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY \
  --days 2

# Fetch GitHub PR review queue
python3 scripts/github_prs.py

# Send a report
python3 scripts/send_report_smtp.py "My Subject" output/daily_dashboard_report.html
```

---

## Customising for your dashboards

The prompt and metric names in this repo are tuned for a specific Datadog setup. To adapt it for your own dashboards, see **[CUSTOMISING.md](CUSTOMISING.md)** — no scripts to run, just fill in a template and paste it into Cursor.

---

## License

MIT — see [LICENSE](LICENSE).
