# Engineering Pulse

[![CI](https://github.com/seek-oss/engineering-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/seek-oss/engineering-pulse/actions/workflows/ci.yml)

An **agent- and skill-driven** daily engineering health dashboard for **engineering teams** — visibility into systems, delivery, and review load in one place.

Pulls live data from **Datadog**, **GitHub**, and **Todoist**, generates a colour-coded HTML scorecard, archives it to a local **report calendar**, and notifies you on macOS (or emails it) — driven interactively (**Claude Code** or **Cursor** with **`/daily-dashboard`**) or headlessly (`make run` / LaunchAgent via `AGENT_CLI`: **`claude`** or **`cursor`**). Also keeps a **task list** and **reading queue** in Todoist. Optionally adds **Stakeholder Pulse** — per-person Slack summaries (via Glean MCP where your editor exposes it — e.g. Cursor) for names you list in `.env`. **Pi Agent** support is **[in progress](harness/pi-agent/)** (experimental `AGENT_CLI=pi`).

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

> **Prerequisites:** Python 3.11+, `git`, and **one** AI agent CLI (installer helps you choose).

See [CONTRIBUTING.md](CONTRIBUTING.md) for running tests and opening pull requests.

### Agent CLI

Engineering Pulse needs an AI agent CLI to run dashboard prompts. The installer detects which agents you have and lets you pick:

| Agent | Install command | Notes |
|---|---|---|
| Claude Code (recommended) | `npm install -g @anthropic-ai/claude-code` | Requires Anthropic API key for automation; scheduled runs bypass interactive permissions |
| Cursor CLI | `curl https://cursor.com/install -fsSL \| bash` | Uses Cursor subscription credits |
| Pi Agent *(in progress)* | `curl -fsSL https://pi.dev/install.sh \| sh` | Experimental; see [`harness/pi-agent/README.md`](harness/pi-agent/README.md) |

Your choice is saved in `.env` as `AGENT_CLI` (`claude` or `cursor` today; **`pi` experimental**). Change it any time, or re-run `bash install.sh`.

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
**Stakeholder Pulse** is omitted when the **`STAKEHOLDERS`** line is absent from **`.env`** (or cleared with **`STAKEHOLDERS=`**); the Pulse section renders only once Step 2F has produced the Markdown cards.
---

## Agent skill (multi-harness)

The daily workflow lives in a portable **[Agent Skill](https://agentskills.io/specification)**:

- **Canonical:** [`skills/engineering-pulse/SKILL.md`](skills/engineering-pulse/SKILL.md) + [`references/`](skills/engineering-pulse/references/)
- **Install matrix:** [`skills/README.md`](skills/README.md) (Cursor, Claude Code, skills.sh, ai-toolkit)
- **Harness adapters:** [`harness/`](harness/) — Cursor / Claude Code entrypoints (Pi: [in progress](harness/pi-agent/))
- **Repo context:** [`AGENTS.md`](AGENTS.md) — always-on rules for agents in this tree

**Run interactively:** invoke the **engineering-pulse** skill (`SKILL.md`) from **Claude Code** or **Cursor** (`/daily-dashboard`) — see [`harness/`](harness/) (**Pi** [in progress](harness/pi-agent/)). **Scheduled / headless:** `make run`, `~/bin/run-daily-dashboard.sh`, or LaunchAgent (see below).

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
  deliver_report.py              ← archive + notify/email per DELIVERY
  report_archive.py              ← report archive, manifest, calendar index.html
  report_snapshot.py             ← structured snapshot of a report (for changes / compare)
  compare_reports.py             ← validate two report ids, write the compare context
  run_compare.sh                 ← run the report-compare skill through AGENT_CLI
  install_url_handler.sh         ← register engineering-pulse:// links (macOS)
  notify_report.py               ← macOS "report ready" notification
  schedule.py                    ← show / change the LaunchAgent schedule
  send_report_smtp.py            ← sends HTML report via SMTP

output/                     ← gitignored; all generated files land here
  <slug>_metric_results.json
  github_prs.json
  todos.json
  stakeholders/*.md         ← Glean-generated Stakeholder Pulse cards
  reports/                  ← archived reports + calendar (index.html, manifest.json)
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
- **Datadog MCP** — connected in your agent (OAuth), plus your dashboard URLs
- **GitHub MCP** — connected in your agent (OAuth); set `GITHUB_TEAM=org/team` in `.env`. A personal access token (`GITHUB_TOKEN`) is only a fallback when MCP is not available
- **Gmail SMTP** *(only for `DELIVERY=email` or `both`)* — App Password (2FA must be enabled on your Google account)
- **Todoist** *(optional)* — API token from Settings → Integrations → Developer
- **Glean MCP** *(optional)* — for Stakeholder Pulse today (readonly Slack token support planned); add it wherever your toolchain supports MCP (commonly Cursor), then set `STAKEHOLDERS` in `.env`

Then add your dashboards using **`/add-dashboard`** in Cursor (or the equivalent flow in **Claude Code** — see [`harness/`](harness/)):
```
/add-dashboard add my dashboard at https://app.datadoghq.com/dashboard/...
```

See `prompts/dashboards/_example.md` for the file format reference.
Dashboard files are **gitignored** so your Datadog URLs stay local.

### Running the dashboard

**Interactively:** run the **engineering-pulse** skill — e.g. **Cursor:** **`/daily-dashboard`** · **Claude Code:** see [`skills/README.md`](skills/README.md) and [`harness/`](harness/).

**From the terminal** (same **`SKILL.md`** payload as LaunchAgent — agent chosen via `AGENT_CLI` in `.env`):
```bash
cd ~/.engineering-pulse
make run          # foreground: stream logs to your terminal AND append /tmp/daily-dashboard.log
make run-bg       # background: append log only (use `make logs` or `tail -f`)
make logs         # tail the log
make status       # check the schedule
make update       # pull latest + reinstall deps
make help         # list all targets
```

**On a schedule** — the installer sets up a macOS LaunchAgent (default 9:00, 12:00, 16:00 Mon–Fri). After upgrading the repo, re-run `bash install.sh` from `~/.engineering-pulse` so `~/bin/run-daily-dashboard.sh` points at `skills/engineering-pulse/SKILL.md`.

Change the schedule from the command line (rewrites the plist and reloads it):

```bash
cd ~/.engineering-pulse
.venv/bin/python scripts/schedule.py show
.venv/bin/python scripts/schedule.py set --days mon-sun --times 10:00            # 10 AM every day
.venv/bin/python scripts/schedule.py set --days mon-fri --times 09:00,12:00,16:00
```

### Report calendar and notifications

Every report is archived under `output/reports/` and listed on a calendar at
`output/reports/index.html` (`make reports` opens it). Days with reports show a
coloured dot per type (Engineering Pulse, Sprint report); click a day to step through
all of that day's reports with ← / →. Days without reports are greyed out, and a
scheduled day with no report gets a dashed red outline.

The ⚙ Settings panel changes the schedule (days and times), pauses or resumes each
scheduled report, and sets `REPORT_AUTO_OPEN` and `REPORT_RETENTION_DAYS`. **Apply**
opens an `engineering-pulse://settings` link; the helper app shows a macOS confirmation
dialog, then `scripts/settings.py` updates the LaunchAgent and `.env` and rebuilds the
calendar. Secrets and `DELIVERY` are only changed by editing `.env`. The same changes
work from Terminal: `.venv/bin/python scripts/settings.py set --reports pulse --times 10:00`.

`DELIVERY` in `.env` picks how you're told a report is ready: `notify` (default, macOS
notification), `email` (SMTP), `both`, or `none` (local file only — no notification or
email). The installer installs `terminal-notifier` via Homebrew so clicking the
notification opens the report; without Homebrew you get a plain banner. To import
reports generated before the archive existed, run `.venv/bin/python scripts/report_archive.py backfill`.

### When something goes wrong

Every run delivers a report, even when a data source or the agent fails. Problems from
that run appear in a **red box at the top of the report**, and everything that could
still be generated appears below it. The notification says how many problems there were.

- **MCP server not signed in** (checked through your agent CLI before each run): the box
  shows **Sign in to <server>**, which opens Terminal at the sign-in step
  (`agent mcp login <server>` for Cursor; `/mcp` inside Claude Code), and **Re-run this
  report** once you have signed in.
- **No Datadog dashboards yet:** **Add a Datadog dashboard** opens Terminal with your
  agent already asking for the dashboard URL (the `/add-dashboard` flow). The box also
  lists the steps to do it yourself.
- **Anything a click cannot fix** (an MCP server not added to your
  agent, the agent stopping early): the box explains what happened and what to do; the
  run log is `/tmp/daily-dashboard.log`.

The buttons use the same `engineering-pulse://` helper app as Compare and Settings, so
they work when the report is opened on the Mac where Engineering Pulse is installed.

### Changes between reports and Compare

When you view a report on the calendar, the bar above it summarises what changed since
the previous report of the same type; **Show changes** lists the details:

- **Sprint report:** tickets finished, other status changes, tickets added to or removed
  from the sprint, and the completed / remaining / scope totals.
- **Engineering Pulse:** health metrics that changed (band changes first), new PRs in
  the review queue and PRs that left it, and new stakeholder messages (links that were
  not in the previous report).

**⇄ Compare** (top of the calendar) compares any two reports of the same type, for
example two sprint reports a month apart. **Ask the agent to compare** runs the
[`report-compare`](skills/report-compare/SKILL.md) skill through `AGENT_CLI` in the
background; the written comparison is archived to the calendar (grey dot) and you get a
notification when it is ready. The button uses an `engineering-pulse://` link that the
installer registers with a small helper app (`~/Applications/Engineering Pulse.app`).
Without the helper, run the same thing from Terminal:

```bash
cd ~/.engineering-pulse
make compare A=sprint-20260924-123457 B=sprint-20261003-184413   # ids are shown on the Compare view
tail -f /tmp/engineering-pulse-compare.log
```

---

## Configuration reference

| Variable | Required | Description |
|---|---|---|
| `DATADOG_TEAMS` | no | Comma-separated team slugs — filters all queries (Datadog data via **MCP** in the agent session) |
| `GITHUB_TEAM` | no | Team for the PR review queue, as `org/team` (PRs via **GitHub MCP**). Older `GITHUB_ORG` + bare team slug still works |
| `GITHUB_TOKEN` | fallback | PAT with `repo` + `read:org`, only when GitHub MCP is not available |
| `SPRINT_BOARD` | for sprint | One sentence describing your sprint board; unset → no sprint report |
| `DELIVERY` | no | `notify` (default), `email`, `both`, or `none` (local file only) — reports are always archived to the calendar |
| `REPORT_AUTO_OPEN` | no | `1` also opens the report in your browser after each run |
| `REPORT_RETENTION_DAYS` | no | Days of archived reports to keep (default `90`; `0` keeps all) |
| `SCHEDULED_REPORTS` | no | Reports that runs make, scheduled or `make run`: `pulse,sprint` (default), `pulse`, `sprint`, or `none` (paused) |
| `SMTP_USER` | for email | Gmail address |
| `SMTP_PASSWORD` | for email | Gmail App Password (16 chars) |
| `SMTP_FROM` | no | Sender address (default `SMTP_USER`) |
| `SMTP_TO` | for email | Recipient address |
| `TODOIST_API_TOKEN` | no | Todoist API token (for todo / reading queue; unset → My Queue omitted) |
| `TODOIST_PROJECT_ID` | no | Auto-set by `python scripts/todo.py setup` |
| `STAKEHOLDERS` | no | Names for Pulse (Glean MCP; typically wired through an MCP-capable editor such as Cursor). **Omit this line from `.env` to hide Pulse** (shell `export` alone does not enable it). `STAKEHOLDERS=` explicitly clears tracked names when your dotenv tooling needs an empty value. Prefer `Jane Doe,john.smith@example.com` over first names only. |

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

Or use **`/todo`** in Cursor (if available): `remind me to review the EKS upgrade`

### Daily dashboard HTML

After running both Datadog extractions, GitHub PRs, and `todo.py list --json`:

```bash
python3 scripts/render_daily_dashboard_html.py
```

By default this writes **`output/daily_dashboard_report.html`** (override with `--out`).

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

# Deliver a report (archive + notify/email per DELIVERY)
python3 scripts/deliver_report.py send --type pulse output/daily_dashboard_report.html

# Email only
python3 scripts/send_report_smtp.py "My Subject" output/daily_dashboard_report.html
```

---

## Adding a new Datadog dashboard

You can add any Datadog dashboard to the daily report without editing existing files:

1. Run **`/add-dashboard`** where your harness exposes it (**Cursor** snippet below; see [`harness/`](harness/) for **Claude Code**).
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
writes one markdown card per name in `output/stakeholders/`; the HTML report shows **Stakeholder Pulse** only when `STAKEHOLDERS` is set in `.env` and Step 2F has produced matching Markdown cards (nothing in HTML until then; stderr may hint if cards are missing).

### Slack data: two possible approaches

| Approach | Status | Best for |
|----------|--------|----------|
| **Glean MCP** (via an MCP-capable editor, commonly **Cursor**) | **Supported today** | Orgs that already use Glean for Slack search — no Slack token in `.env` |
| **Read-only Slack token** | *Not implemented yet* | Orgs without Glean; a bot/user token with read-only channel history could feed the same card format |

**Today only Glean MCP is wired up** (Step 2F). A direct Slack API path may be
added later for teams that prefer a readonly token over enterprise search.

### Enable (Glean MCP)

1. **Glean MCP** — add/configure Glean MCP in your editor (**Cursor:** [Cursor MCP settings](https://docs.cursor.com/context/mcp); others — see [`harness/`](harness/)). *(Not shipped in this repo.)*
2. **`STAKEHOLDERS` in `.env`** — comma-separated names or emails, e.g.  
   `STAKEHOLDERS=Jane Doe,john.smith@example.com`
3. Run the dashboard (e.g. Cursor **`/daily-dashboard`**, or invoke **`engineering-pulse`** in **Claude Code** — see [`harness/`](harness/)).

### What happens each run

- The agent deletes stale `output/stakeholders/*.md`, then writes one file per
  name: `output/stakeholders/<slug>.md` (same gitignored `output/` tree as PRs
  and todos).
- Each card has three bullets: **Themes**, **Notable** (with link), **Top links**.
- The HTML renderer reads **`STAKEHOLDERS` from your repo `.env` file text**. If **`STAKEHOLDERS` is missing from `.env`** (whole line omitted), Pulse is **off** even when a shell session has `export STAKEHOLDERS=…`. Use **`STAKEHOLDERS=`** on its own line to clear tracked names explicitly if your tooling prefers an empty assignment.

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
