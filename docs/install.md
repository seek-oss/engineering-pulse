---
title: Installation guide
---

# Installation guide

This guide tells you how to install Engineering Pulse on a Mac and make your first report.
The procedure takes approximately 15 minutes.

**Words in this guide**

- **Agent:** the AI tool that does the work. Engineering Pulse uses the Cursor agent. In Terminal, the Cursor CLI command is `agent`.
- **MCP server:** a connection that lets the agent read data from a tool, for example Datadog or GitHub.
- **Dashboard:** a Datadog dashboard. Engineering Pulse reads its widgets and shows their values.
- **Report:** the HTML page that Engineering Pulse makes. Each report goes on the report calendar.
- **Run:** one time that Engineering Pulse makes a report. Runs start on a schedule or from `make run`.

## 1. Get the prerequisites

### 1.1 Check the basic tools

Open Terminal. Run these commands:

```bash
python3 --version     # must show 3.11 or newer
git --version
```

If Python is older than 3.11, install a newer version from [python.org](https://www.python.org/downloads/) or with Homebrew (`brew install python`).

### 1.2 Install Cursor and the Cursor CLI

1. Install the Cursor app from [cursor.com](https://cursor.com) and sign in.
2. Install the Cursor CLI:

   ```bash
   curl https://cursor.com/install -fsSL | bash
   ```

3. Make sure that the CLI starts and that you are signed in:

   ```bash
   agent --version
   agent status
   ```

   If `agent status` shows that you are not signed in, run `agent login`.

The Cursor CLI uses your Cursor subscription.

### 1.3 Add the MCP servers in Cursor

Engineering Pulse needs two MCP servers:

| MCP server | Used for | Setup guide |
|------------|----------|-------------|
| Datadog | Dashboard metrics | [Datadog MCP server](https://docs.datadoghq.com/bits_ai/mcp_server/setup/) |
| GitHub | The pull request review queue | [GitHub MCP server](https://github.com/github/github-mcp-server) |

Optional features need more MCP servers: Atlassian for the sprint report, and Glean for Stakeholder Pulse.

The Cursor CLI reads MCP servers from these files:

| File | Scope |
|------|-------|
| `~/.cursor/mcp.json` | Your user config. Used for all projects and for `agent` in Terminal. |
| `.cursor/mcp.json` in a project | That project only. |

Ask your platform team for the company MCP config, or add the servers in the Cursor app: open **Settings**, then **MCP**. See [Cursor MCP](https://docs.cursor.com/context/mcp).

Make sure that the CLI shows the servers:

```bash
agent mcp list
```

If a server is missing from the list, it is not in the MCP config yet. Add it to `~/.cursor/mcp.json` (or to the project file), then run `agent mcp list` again.

## 2. Run the installer

Run this command in Terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/seek-oss/engineering-pulse/main/web-install.sh | bash
```

> **Note:** Use `web-install.sh`, not `install.sh`, in this command. `web-install.sh` gets the repository first and then starts the installer from your disk.

The installer asks which agent to use. Type the number for **Cursor CLI** and push Enter.

The installer does these steps:

1. It copies the repository to `~/.engineering-pulse`.
2. It makes a Python environment in `~/.engineering-pulse/.venv`.
3. It makes `~/.engineering-pulse/.env` from `.env.example`. It does not change an `.env` that exists.
4. It installs the schedule: 09:00 and 18:00, Monday to Friday. You can change it later in **Settings** on the report calendar.
5. It installs `~/Applications/Engineering Pulse.app`. This small app makes the buttons in the reports work.
6. It installs `terminal-notifier` with Homebrew, if you have Homebrew. Then a notification opens the report when you select it.

To use a different folder, set `INSTALL_DIR` before the command. To use different run hours, set `SCHEDULE_HOURS`, for example `SCHEDULE_HOURS="8 13"`.
When you run the installer again, it keeps the schedule that you set in Settings. It changes the schedule only when you set `SCHEDULE_HOURS`.

## 3. Sign in to the MCP servers

Do this step one time for each MCP server. The servers must already be in
`~/.cursor/mcp.json` or in a project `.cursor/mcp.json` (see [step 1.3](#13-add-the-mcp-servers-in-cursor)).

Find the server names first:

```bash
agent mcp list
```

A server that shows `requires_authentication` needs a sign-in. Run the command for each of these servers. These are the usual servers:

```bash
agent mcp login Datadog      # dashboard metrics (necessary)
agent mcp login GitHub       # pull request review queue (necessary)
agent mcp login Atlassian    # sprint report from Jira
agent mcp login Glean        # Stakeholder Pulse from Slack
```

Use the names that `agent mcp list` shows. They can be different on your Mac.
Each command opens a browser window. Sign in, then go back to Terminal.

If you forget this step, the report tells you. A **Sign in to &lt;server&gt;** button shows in the red problems box.

## 4. Configure the `.env` file

First, make a local `.env` from the example if it does not exist. The installer normally
does this for you. This command does not overwrite an existing `.env`:

```bash
cd ~/.engineering-pulse
test -f .env || cp .env.example .env
open -e .env
```

Follow the comments in `.env`. Replace the placeholder values. Uncomment an optional
variable only when you want the part of the report that uses it.

| Variable | Required for | What to do |
|----------|--------------|------------|
| `AGENT_CLI` | All reports | Keep `cursor`. The installer sets it. |
| `DATADOG_TEAMS` | Datadog metrics | Replace `your-team` with one or more Datadog team slugs. |
| `GITHUB_TEAM` | PR Review Queue | Replace the placeholder with `org/team`. |
| `SPRINT_BOARD` | Sprint report | Uncomment it and describe your Jira board in one sentence. See [Sprint report](features.md#sprint-report). |
| `STAKEHOLDERS` | Stakeholder Pulse | Uncomment it and add full names or email addresses. Glean MCP supplies the data. |
| `TODOIST_API_TOKEN` | My Queue | Uncomment it and add your Todoist token. |
| `DELIVERY` | Report delivery | Use `notify`, `email`, `both` or `none`. |
| `SMTP_*` | Email delivery | Uncomment and configure these only for `DELIVERY=email` or `both`. |

`DATADOG_TEAMS` and `GITHUB_TEAM` are the normal minimum for the Engineering Pulse
report. The other variables enable separate reports or optional sections.

Do not put Datadog or GitHub API keys in `.env`. Their MCP servers handle the sign-in.
For every setting and its accepted values, read [Configuration](configuration.md).

## 5. Add your first Datadog dashboard

1. Open the Datadog dashboard in your browser.
2. Copy the URL from the address bar.
3. Start the Cursor agent in the install folder:

   ```bash
   cd ~/.engineering-pulse
   agent "Follow skills/engineering-pulse/references/add-dashboard.md to add this dashboard: <dashboard URL>"
   ```

   In the Cursor app, open `~/.engineering-pulse` and type `/add-dashboard <dashboard URL>` in the chat.

4. The agent shows a list of the widgets on the dashboard. Tell it which widgets you want.
5. The agent proposes a red, yellow and green threshold for each metric. Confirm or change each threshold. Without thresholds, a tile is always green.
6. The agent writes `prompts/dashboards/custom_<name>.md`. The next run uses this file.

Repeat this procedure for each dashboard. You can also start it from the report: when no dashboard is set up, the red problems box shows an **Add a Datadog dashboard** button.

## 6. Make your first report

```bash
cd ~/.engineering-pulse
make run
```

The run takes 2 to 5 minutes. The terminal shows the agent's progress.
When the run is done, you get a macOS notification. Select it to open the report.

To open the report calendar at a different time:

```bash
cd ~/.engineering-pulse && make reports
```

If the report has a red problems box, read [Troubleshooting](troubleshooting.md).

## 7. After the first report

- The schedule makes new reports automatically. To change the days or times, open the calendar and select **Settings**.
- To turn on optional features, select the **"✦ N more features"** badge on the report, or read [Features](features.md).
- To get the report by email, read [Delivery](configuration.md#delivery).

## Upgrade

Run the installer again:

```bash
curl -fsSL https://raw.githubusercontent.com/seek-oss/engineering-pulse/main/web-install.sh | bash
```

The installer gets the new version and updates the runner, the schedule and the button app.
It does not change these items:

- `.env`
- your dashboards in `prompts/dashboards/`
- your notes in `prompts/extras/`
- your reports in `output/`

## Uninstall

> **Warning:** The uninstaller deletes `~/.engineering-pulse`, which includes `.env`, your dashboards and all reports. Copy the files that you want to keep before you start.

```bash
bash ~/.engineering-pulse/uninstall.sh
```

The uninstaller removes the schedule, the runner `~/bin/run-daily-dashboard.sh`, the button app and the install folder. It asks you to confirm first.

## Manual install

Use this procedure if you cannot use the installer.

```bash
git clone https://github.com/seek-oss/engineering-pulse.git ~/.engineering-pulse
cd ~/.engineering-pulse
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
bash install.sh
```

`install.sh` asks for the agent and installs the schedule and the button app. Then continue at [step 3](#3-sign-in-to-the-mcp-servers).
