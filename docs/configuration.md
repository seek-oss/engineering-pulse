---
title: Configuration
---

# Configuration

Engineering Pulse reads its settings from `~/.engineering-pulse/.env`.
To edit the file, run `make config` in `~/.engineering-pulse`, or open the file in a text editor.

> **Caution:** `.env` can contain passwords and tokens. Do not share it and do not add it to git.

## Settings that most users need

| Setting | Example | Purpose |
|---------|---------|---------|
| `AGENT_CLI` | `cursor` | The agent that makes the reports. Use `cursor`. The installer sets it. |
| `DATADOG_TEAMS` | `team-a` | Your Datadog team slug. Use commas for more than one team. It filters the dashboard queries. |
| `GITHUB_TEAM` | `acme/team-a` | The GitHub team whose review requests you track, as `org/team`. Your own review requests are always included. |
| `DELIVERY` | `notify` | How you get the report. See [Delivery](#delivery). |

## Optional features

| Setting | Example | Purpose |
|---------|---------|---------|
| `SPRINT_BOARD` | `"My sprint board is at ..."` | One sentence about your Jira board. If it is not set, there is no sprint report. See [Sprint report](features.md#sprint-report). |
| `STAKEHOLDERS` | `Jane Doe,alex.smith@example.com` | The people for Stakeholder Pulse. Remove the line to turn it off. See [Stakeholder Pulse](features.md#stakeholder-pulse). |
| `TODOIST_API_TOKEN` | | Your Todoist token. If it is not set, the report does not show My Queue. |
| `TODOIST_PROJECT_ID` | | `scripts/todo.py setup` sets this value. |

## Delivery

`DELIVERY` sets how you get each report. All reports go on the calendar, for all values.

| Value | Result |
|-------|--------|
| `notify` | A macOS notification (default) |
| `email` | An email with the report |
| `both` | A notification and an email |
| `none` | No message. The report is on the calendar only. |

### Set up email with Gmail

1. Turn on 2-Step Verification for your Google account.
2. Make an App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Add these lines to `.env`:

   ```bash
   DELIVERY=email
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=xxxx xxxx xxxx xxxx
   SMTP_TO=you@example.com
   ```

Optional email settings: `SMTP_FROM` (default: `SMTP_USER`), `SMTP_HOST` (default: `smtp.gmail.com`), `SMTP_PORT` (default: `587`) and `SMTP_USE_TLS` (default: `true`).

## Schedule and reports

Use the **Settings** panel on the calendar for these settings. The panel writes them for you.

| Setting | Default | Purpose |
|---------|---------|---------|
| Days and times | 09:00, 12:00, 16:00, Monday to Friday | When the schedule makes reports |
| `SCHEDULED_REPORTS` | `pulse,sprint` | The reports that runs make: `pulse`, `sprint`, both, or `none` (paused). This also applies to `make run`. |
| `REPORT_AUTO_OPEN` | off | `1` opens each new report in your browser |
| `REPORT_RETENTION_DAYS` | `90` | The number of days to keep reports. `0` keeps all reports. |

You can also change them in Terminal:

```bash
cd ~/.engineering-pulse
.venv/bin/python scripts/schedule.py show
.venv/bin/python scripts/schedule.py set --days mon-fri --times 09:00,12:00,16:00
.venv/bin/python scripts/settings.py set --reports pulse --times 10:00
```

To make only one report one time, without a change to the settings:

```bash
ENGINEERING_PULSE_ONLY=pulse make run      # or: ENGINEERING_PULSE_ONLY=sprint make run
```

## Settings for special cases

| Setting | Purpose |
|---------|---------|
| `GITHUB_TOKEN` | Use only when the GitHub MCP server is not available. A personal access token with `repo` (read) and `read:org`. |
| `REPORTS_DIR` | A different folder for the report calendar (default: `output/reports`) |
| `GITHUB_ORG` | Old format: `GITHUB_ORG` plus a team slug in `GITHUB_TEAM`. It still works. |

For the full list, see [`env-and-paths.md`](https://github.com/seek-oss/engineering-pulse/blob/main/skills/engineering-pulse/references/env-and-paths.md).

## Files that stay on your Mac

These files are not part of git. An upgrade does not change them.

| Path | Content |
|------|---------|
| `.env` | Your settings and passwords |
| `prompts/dashboards/*.md` | Your Datadog dashboards (not `_example.md`) |
| `prompts/extras/*.md` | Your extra cards |
| `output/` | All data and reports, including the calendar in `output/reports/` |
