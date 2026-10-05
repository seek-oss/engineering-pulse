---
title: Features
---

# Features

This page tells you what is in the report and how to use each feature.

## The Engineering Pulse report

The report has these sections, in this sequence. Each section gets a letter (Part A, Part B, ...). A section that has no data is not shown.

| Section | Content | Source |
|---------|---------|--------|
| One section for each Datadog dashboard | One tile for each widget that you selected. Red, yellow and green show the health. | Datadog MCP |
| PR Review Queue | Open pull requests that wait for a review from you or your team, newest first. Renovate pull requests are not shown. | GitHub MCP |
| My Queue | Your Todoist tasks and reading list | Todoist (optional) |
| Extras | Your own Markdown notes as cards | `prompts/extras/` (optional) |
| Stakeholder Pulse | One card for each person: themes, notable messages and links from Slack | Glean MCP (optional) |

The **"✦ N more features"** badge at the top right shows the optional features that are off. Select it to see how to turn each one on. Email copies of the report do not show the badge.

## Datadog dashboards

You can add as many Datadog dashboards as you want. Each dashboard is a file in `prompts/dashboards/`.

To add a dashboard:

1. Copy the dashboard URL from your browser.
2. In `~/.engineering-pulse`, start your agent with this request:

   ```bash
   agent "Follow skills/engineering-pulse/references/add-dashboard.md to add this dashboard: <dashboard URL>"
   ```

   In the Cursor app, type `/add-dashboard <dashboard URL>` in the chat.

3. Tell the agent which widgets you want.

The agent writes `prompts/dashboards/custom_<name>.md`. The file contains the URL, the widgets and the colour rules. You can edit the file. To remove a dashboard, delete its file.

These files are not part of git. Your dashboard URLs stay on your Mac.
For the file format, see [`prompts/dashboards/_example.md`](https://github.com/seek-oss/engineering-pulse/blob/main/prompts/dashboards/_example.md).

## Report calendar

All reports go on a calendar at `~/.engineering-pulse/output/reports/index.html`. To open it, run `make reports`.

- A coloured dot on a day shows a report: one colour for each report type.
- Select a day to read its reports. Use the arrow keys to go to the next or previous report.
- A scheduled day without a report has a red dashed outline.

### Settings

Select **Settings** on the calendar to change:

- the days and times of the schedule
- which reports the schedule makes (pause or resume each report)
- if the report opens in your browser after each run
- how many days to keep reports (default: 90)

Select **Apply**. A macOS dialog asks you to confirm.

### What changed

When you read a report on the calendar, a bar above it tells you what changed since the previous report of the same type. Select **Show changes** to see the details:

- **Engineering Pulse:** metrics that changed (colour changes first), new pull requests, pull requests that left the queue, and new stakeholder messages.
- **Sprint report:** tickets that are done, other status changes, tickets added to or removed from the sprint, and the totals.

### Compare two reports

1. Select **Compare** at the top of the calendar.
2. Select two reports of the same type, for example two sprint reports a month apart.
3. Select **Ask the agent to compare**.

The agent writes a short comparison: what changed, what is at risk, and what to look at next. The comparison goes on the calendar, and you get a notification.

You can also start a comparison in Terminal. The Compare view shows the report IDs.

```bash
cd ~/.engineering-pulse
make compare A=<first report id> B=<second report id>
```

## Sprint report

The sprint report shows the progress of your team's sprint from Jira. It has a burn-up chart, a burn-down chart, the progress of each epic, a list of events and a table of tickets.

You need:

- the Atlassian MCP server in your agent
- one sentence that describes your board, in `.env`

```bash
SPRINT_BOARD="My sprint board is at https://<your-site>.atlassian.net/jira/software/c/projects/<PROJ>/boards/<id>. Only include epics whose summary starts with [TEAM]. Sprints run for two weeks."
```

You can add more information to the sentence, for example "use story points" or the locations of your team for public holidays.
If `SPRINT_BOARD` is not set, the schedule does not make a sprint report.

## Stakeholder Pulse

Stakeholder Pulse shows what a small group of people said and asked for in Slack in the last 7 days. Each person gets one card with three items: themes, a notable message with a link, and the top links.

You need:

- the Glean MCP server in your agent
- the names or email addresses, in `.env`:

```bash
STAKEHOLDERS=Jane Doe,alex.smith@example.com
```

Use full names or email addresses. First names alone can find the wrong person.

Limits:

- Glean usually finds messages in public Slack channels only. It does not find direct messages or private channels.
- New messages can take some hours to show.
- Keep the list short (approximately 5 people). Each name makes the run longer.

To turn off Stakeholder Pulse, remove the `STAKEHOLDERS` line from `.env`.

## My Queue (Todoist)

My Queue shows your open Todoist tasks and your reading list in the report.

1. In Todoist, open **Settings**, then **Integrations**, then **Developer**. Copy the API token.
2. Add the token to `.env`:

   ```bash
   TODOIST_API_TOKEN=<your token>
   ```

3. Make the Todoist project and sections one time:

   ```bash
   cd ~/.engineering-pulse && .venv/bin/python scripts/todo.py setup
   ```

You can add and close tasks in Terminal:

```bash
.venv/bin/python scripts/todo.py add "Review the upgrade proposal" --priority high
.venv/bin/python scripts/todo.py add "Article on team topologies" --type read --url "https://example.com/article"
.venv/bin/python scripts/todo.py list
.venv/bin/python scripts/todo.py done <task-id> --comment "Merged"
```

You can also use the Todoist app on your phone.

## Extras

Put a Markdown file in `prompts/extras/`. The next report shows it as a card.

- The first `# Heading` is the card title. If there is no heading, the file name is the title.
- The card can contain headings, bold and italic text, lists, links and code blocks.
- Files with a name that starts with `_` are examples. The report does not show them.

For an example, see [`prompts/extras/_example.md`](https://github.com/seek-oss/engineering-pulse/blob/main/prompts/extras/_example.md).

## Use the agent in a chat

You can also make a report in a chat with your agent:

- **Cursor:** open `~/.engineering-pulse` and type `/daily-dashboard`.
- **Claude Code:** run `claude` in `~/.engineering-pulse` and ask it to use the **engineering-pulse** skill.

The scheduled runs and `make run` use the same instructions as the chat. The instructions are in [`skills/engineering-pulse/SKILL.md`](https://github.com/seek-oss/engineering-pulse/blob/main/skills/engineering-pulse/SKILL.md).
