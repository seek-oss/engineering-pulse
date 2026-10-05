# Engineering Pulse

[![CI](https://github.com/seek-oss/engineering-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/seek-oss/engineering-pulse/actions/workflows/ci.yml)

Engineering Pulse gives an engineering manager one daily report about the team.
It shows system health from Datadog, the pull requests that wait for review, and your own tasks.
An AI agent on your Mac collects the data and writes the report. You do not write code.

![Engineering Pulse report (example)](docs/images/report.svg)

## What you get

- **A daily report.** It shows the health metrics from your Datadog dashboards with red, yellow and green colours, plus the GitHub pull requests that wait for you or your team.
- **A schedule.** The report runs at 09:00, 12:00 and 16:00, Monday to Friday. You can change the times.
- **A notification.** macOS tells you when a new report is ready. Email is optional.
- **A report calendar.** All reports stay on your Mac. You can see what changed between two reports.
- **A problems box.** If a data source fails, the report still comes. A red box at the top tells you what failed. Many problems have a button that fixes them.

Optional features: a sprint report from Jira, a summary of what your stakeholders said in Slack (Glean), and your Todoist tasks.
See [Optional features](#optional-features).

## What you need

| Item | How to check |
|------|--------------|
| A Mac | The schedule, notifications and buttons use macOS. |
| Python 3.11 or newer | `python3 --version` |
| `git` | `git --version` |
| One agent CLI: **Claude Code** or **Cursor CLI** | `claude --version` or `agent --version` |
| The **Datadog** and **GitHub** MCP servers, added to that agent | `claude mcp list` or `agent mcp list` |

An MCP server is a connection that lets the agent read data from a tool, for example Datadog.
You sign in to each MCP server one time. You do not put API keys in a file.
[docs/install.md](docs/install.md#1-get-the-prerequisites) tells you how to install the agent CLI and add the MCP servers.

## Install in 5 steps

1. Open Terminal and run the installer:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/seek-oss/engineering-pulse/main/web-install.sh | bash
   ```

   The installer asks one question: which agent to use. It installs to `~/.engineering-pulse`.

2. Sign in to the MCP servers. Use the name that `agent mcp list` or `claude mcp list` shows.

   ```bash
   agent mcp login <server-name>      # Cursor CLI
   claude                             # Claude Code: then type /mcp and sign in
   ```

3. Open `~/.engineering-pulse/.env` and set your teams:

   ```bash
   DATADOG_TEAMS=your-datadog-team
   GITHUB_TEAM=your-github-org/your-team
   ```

   If you do not use Jira sprints, put `#` at the start of the `SPRINT_BOARD` line.

4. Add one Datadog dashboard. Copy the dashboard URL from your browser. Then start your agent in `~/.engineering-pulse` (use `claude` in place of `agent` for Claude Code):

   ```bash
   cd ~/.engineering-pulse
   agent "Follow skills/engineering-pulse/references/add-dashboard.md to add this dashboard: <dashboard URL>"
   ```

   The agent shows the widgets on the dashboard. Tell it which widgets you want in the report.

5. Make your first report:

   ```bash
   cd ~/.engineering-pulse && make run
   ```

   The run takes 2 to 5 minutes. A notification tells you when the report is ready.

For more detail and for Claude Code commands, read the [installation guide](docs/install.md).

## Daily use

- **Read the report.** Select the notification, or open the calendar with `make reports`.
- **Make a report now.** Run `make run` in `~/.engineering-pulse`. To make only the Engineering Pulse report, run `ENGINEERING_PULSE_ONLY=pulse make run`.
- **Change the schedule.** On the calendar, open **Settings**. Change the days and times, then select **Apply**.
- **Compare two reports.** On the calendar, select **Compare**. The agent writes a short summary of what changed.

![Report calendar (example)](docs/images/calendar.svg)

## Optional features

The report shows a **"✦ N more features"** badge when optional features are off. Select the badge to see how to turn them on.

| Feature | What it adds | What you need |
|---------|--------------|---------------|
| [Sprint report](docs/features.md#sprint-report) | Burn-up and burn-down charts for your sprint | Atlassian MCP and `SPRINT_BOARD` in `.env` |
| [Stakeholder Pulse](docs/features.md#stakeholder-pulse) | One card per person: what they said and asked for in Slack this week | Glean MCP and `STAKEHOLDERS` in `.env` |
| [My Queue](docs/features.md#my-queue-todoist) | Your Todoist tasks and reading list | `TODOIST_API_TOKEN` in `.env` |
| [Email](docs/configuration.md#delivery) | The report in your inbox | A Gmail App Password and `DELIVERY=email` |
| [Extras](docs/features.md#extras) | Your own notes as cards in the report | A Markdown file in `prompts/extras/` |

## If something goes wrong

The report always comes, also when a step fails.
A red box at the top of the report shows each problem. Select **Sign in** or **Add a Datadog dashboard** to fix it, then select **Re-run this report**.

![Problems box (example)](docs/images/problems-box.svg)

The run log is `/tmp/daily-dashboard.log`. For more help, read [Troubleshooting](docs/troubleshooting.md).

## More information

| Guide | Content |
|-------|---------|
| [Installation guide](docs/install.md) | Prerequisites, MCP servers, first run, upgrade, uninstall |
| [Features](docs/features.md) | Report sections, calendar, Compare, sprint report, Stakeholder Pulse, Todoist, extras |
| [Configuration](docs/configuration.md) | All `.env` settings, schedule, delivery |
| [Troubleshooting](docs/troubleshooting.md) | The problems box and common problems |
| [Development](docs/development.md) | How it works, scripts, tests |

Your data stays on your Mac. Reports, dashboards and `.env` are not part of git, and an upgrade does not change them.

## Contributing and licence

Read [CONTRIBUTING.md](CONTRIBUTING.md) to run the tests and open a pull request.
Engineering Pulse uses the [MIT licence](LICENSE).
