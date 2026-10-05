---
title: Engineering Pulse
---

# Engineering Pulse

**Daily reports about your team and your sprint, made by the Cursor agent on your Mac.**

Engineering Pulse is for engineering managers. It makes two reports:

- The **Engineering Pulse report** shows system health from Datadog, the pull requests that wait for review, and your own tasks.
- The **sprint report** shows the progress of your Jira sprint, with burn-up and burn-down charts, the progress of each epic, and the scope changes.

You do not write code. The Cursor agent collects the data and writes the reports.

![Engineering Pulse report (example)](images/report.svg)

## What you get

- **A daily Engineering Pulse report** with red, yellow and green health metrics from your Datadog dashboards, and the GitHub pull requests that wait for you or your team.
- **A daily [sprint report](features.md#sprint-report)** with what is done, what remains, and what was added to or removed from the sprint.
- **A schedule:** 09:00, 12:00 and 16:00, Monday to Friday. You can change it, or pause one report.
- **A macOS notification** for each new report. Email is optional.
- **A report calendar** with all reports, and a view of what changed between two reports.
- **A problems box** at the top of the report when a step fails. Many problems have a button that fixes them.

Optional: [Stakeholder Pulse](features.md#stakeholder-pulse) from Slack through Glean, and [My Queue](features.md#my-queue-todoist) from Todoist.

![Report calendar (example)](images/calendar.svg)

## Start here

1. **Install.** Follow the [Installation guide](install.md). It takes approximately 15 minutes.
2. **Make your first report.** The guide ends with `make run` and a notification.
3. **Add more.** Select the **"✦ N more features"** badge on the report, or read [Features](features.md).

## What you need

- A Mac with Python 3.11 or newer and `git`
- Cursor and the Cursor CLI
- The Datadog and GitHub MCP servers in Cursor

## Your data

Engineering Pulse runs on your Mac. Reports, dashboards and settings stay in `~/.engineering-pulse`. They are not part of git, and an upgrade does not change them. The agent reads data through MCP servers with your own sign-in.

## Guides

| Guide | Content |
|-------|---------|
| [Installation guide](install.md) | Prerequisites, MCP servers, first run, upgrade, uninstall |
| [Features](features.md) | Report sections, calendar, Compare, sprint report, Stakeholder Pulse, Todoist, extras |
| [Configuration](configuration.md) | All `.env` settings, schedule, delivery |
| [Troubleshooting](troubleshooting.md) | The problems box and common problems |
| [Development](development.md) | How it works, scripts, tests |

Source code: [github.com/seek-oss/engineering-pulse](https://github.com/seek-oss/engineering-pulse)
