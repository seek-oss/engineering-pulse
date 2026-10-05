---
title: Troubleshooting
---

# Troubleshooting

## The problems box

Each run makes a report, also when a step fails.
If a step fails, a red box at the top of the report tells you what failed. The sections below the box show all the data that the run got.

![Problems box (example)](images/problems-box.svg)

Some problems have a button:

| Button | What it does | When to use it |
|--------|--------------|----------------|
| **Sign in to &lt;server&gt;** | Opens Terminal at the sign-in step for that MCP server | An MCP server needs a sign-in |
| **Add a Datadog dashboard** | Opens Terminal with the Cursor agent. The agent asks for the dashboard URL. | No dashboard is set up |
| **Re-run this report** | Starts a new run of the same report in the background | After you fix the problems |

For a problem without a button, the box tells you what to do.

> **Note:** The buttons work only on the Mac where Engineering Pulse is installed. They do not work in an email.

## Log files

| File | Content |
|------|---------|
| `/tmp/daily-dashboard.log` | All runs: scheduled runs and `make run` |
| `/tmp/daily-dashboard-launchd.out` and `.err` | Messages from the schedule (run `make logs-launchd`) |
| `/tmp/engineering-pulse-compare.log` | Comparisons |

To see a run while it continues, run `make logs` in `~/.engineering-pulse`.

## Common problems

### An MCP server needs a sign-in

The problems box shows **Sign in to &lt;server&gt;**. Select the button, or do the sign-in in Terminal:

```bash
agent mcp login <server-name>
```

Then select **Re-run this report**. To see the server names and their status, run `agent mcp list`.

### The report has no Datadog metrics

You did not add a dashboard yet. Select **Add a Datadog dashboard** in the problems box, or follow [Datadog dashboards](features.md#datadog-dashboards).

### A button does nothing

The button app is not installed, or it is an old version. Run the installer again:

```bash
cd ~/.engineering-pulse && bash install.sh
```

Then open the report again and select the button.

### "A report run is already in progress"

Only one run can operate at a time. Wait for the run to finish, then try again.
The run log shows the progress. After 3 hours, the lock of a stopped run is not used again.

### The calendar does not show a new report

1. Look at the end of `/tmp/daily-dashboard.log`. Make sure that the run finished.
2. Make sure that `SCHEDULED_REPORTS` in `.env` includes the report, for example `pulse`.
3. Run `make reports`. This command makes the calendar again and opens it.

### There is no notification

1. Make sure that `DELIVERY` in `.env` is `notify` or `both`.
2. In macOS **System Settings**, open **Notifications**. Make sure that notifications are on for `terminal-notifier` or Script Editor.
3. If you do not have Homebrew, you get a simple notification that does not open the report. Install Homebrew, then run `bash install.sh` again.

### The schedule does not make reports

1. Run `make status`. The LaunchAgent must show as loaded.
2. If it is not loaded, run `make schedule`.
3. Your Mac must be on and awake at the scheduled time. macOS starts a missed run when the Mac wakes.
4. Look at `make logs-launchd` for errors.

### The sprint report fails

Make sure that `SPRINT_BOARD` in `.env` describes your board. It must not have the example values from `.env.example`.
If you do not use Jira sprints, put `#` at the start of the `SPRINT_BOARD` line.
The Atlassian MCP server must be signed in.

### A stakeholder card is empty or missing

1. Make sure that the name in `STAKEHOLDERS` is spelled correctly. Use the full name or the email address.
2. Glean finds messages in public Slack channels only. A person who writes only in private channels has no card data.
3. The Glean MCP server must be signed in.

### A scheduled run stops at the start

Scheduled runs cannot ask you questions. Make sure of these items:

1. The Cursor CLI is signed in. Run `agent status`. If necessary, run `agent login`.
2. `AGENT_CLI=cursor` is in `.env`.
3. The runner is the current version. Run `bash install.sh` again in `~/.engineering-pulse`.

## Get help

Open an issue at [github.com/seek-oss/engineering-pulse/issues](https://github.com/seek-oss/engineering-pulse/issues).
Include the last 50 lines of `/tmp/daily-dashboard.log`. Remove passwords, tokens and names before you send it.
