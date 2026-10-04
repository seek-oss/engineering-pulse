# Environment and paths

## Environment variables (`.env`)

| Variable | Required | Purpose |
|----------|----------|---------|
| `AGENT_CLI` | for schedule | `claude` or `cursor` (set by installer). `pi`: **experimental / in progress** — see [`harness/pi-agent/`](../../../harness/pi-agent/). |
| `ANTHROPIC_API_KEY` | for Claude automation | API key when using Claude Code for scheduled runs |
| `PI_API_KEY` | experimental | Provider API key if testing `AGENT_CLI=pi` ([in progress](../../../harness/pi-agent/README.md)) |
| `DATADOG_TEAMS` | no | Comma-separated teams — replaces `tpl_var_team` in URL **and** injects `team:<value>` into every metric query |
| `DELIVERY` | no | `notify` (default, macOS notification), `email`, `both`, or `none` (local file only). Reports are always archived. |
| `GITHUB_TEAM` | no | Team whose PR reviews you track, as `org/team`. PRs come from GitHub MCP (Step 2C); your own review requests are always included. |
| `GITHUB_ORG` | legacy | Older `.env` files set `GITHUB_ORG` plus a bare `GITHUB_TEAM` slug; still works |
| `GITHUB_TOKEN` | fallback | Only when GitHub MCP is not available: PAT with `repo` (read) + `read:org` |
| `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_TO` | for email | Gmail SMTP credentials (only when `DELIVERY` is `email` or `both`) |
| `SMTP_FROM` | no | Sender address (default `SMTP_USER`) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USE_TLS` | no | Defaults `smtp.gmail.com`, `587`, `true` |
| `REPORT_AUTO_OPEN` | no | `1` also opens the report in the browser after delivery (Settings panel) |
| `REPORT_RETENTION_DAYS` | no | Days of archived reports to keep (default `90`; `0` keeps all; Settings panel) |
| `SCHEDULED_REPORTS` | no | Reports that runs make, scheduled or `make run`: `pulse,sprint` (default), `pulse`, `sprint`, `none` (Settings panel) |
| `REPORTS_DIR` | no | Archive root (default `output/reports`) |
| `TODOIST_API_TOKEN` | no | Todoist API token (for My Queue; unset → section omitted) |
| `TODOIST_PROJECT_ID` | no | Auto-set by `python scripts/todo.py setup` |
| `STAKEHOLDERS` | no | Pulse names (Glean). **Leave this key out** of `.env` to omit Pulse entirely (ignored if only set via shell `export`). |
| `SPRINT_BOARD` | for sprint | One sentence describing the sprint board ([sprint-report skill](../../sprint-report/SKILL.md)); unset → no sprint report |

The keys marked *Settings panel* are normally changed from the calendar's Settings panel
(or `scripts/settings.py`), which writes them to `.env` for you.

### Gmail SMTP (one-time)

1. Enable 2-Step Verification on your Google account.
2. Create an App password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Add to `.env`:

```bash
DELIVERY=email
SMTP_USER=you@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
SMTP_TO=recipient@example.com
```

## Gitignored user content

| Path | Purpose |
|------|---------|
| `prompts/dashboards/*.md` | Real Datadog URLs (except `_example.md`) |
| `prompts/extras/*.md` | Extra report cards |
| `output/` | All generated JSON/HTML |
| `output/stakeholders/*.md` | Glean-generated stakeholder cards |
| `output/reports/` | Archived reports, `manifest.json`, calendar `index.html` |
| `.env` | Secrets |

## Script reference

**Extract:** Datadog MCP + `scripts/datadog_dashboard_extract.py` →
`output/<slug>_metric_results.json` ([datadog-mcp-extract.md](datadog-mcp-extract.md))

**Render:** `scripts/render_daily_dashboard_html.py` — default HTML at
`output/daily_dashboard_report.html`; args include `--out`, `--dashboards-dir`,
`--output-dir`, `--prs`, `--todos`, `--extras-dir`, `--stakeholders-dir`, `--extra LABEL:FILE`

**Deliver:** `scripts/deliver_report.py send --type pulse|sprint|compare [--subject S] FILE` —
archives via `scripts/report_archive.py` (which stores a structured snapshot from
`scripts/report_snapshot.py` for the calendar's change view), then notifies
(`scripts/notify_report.py`) and/or emails (`scripts/send_report_smtp.py`) per `DELIVERY`.

**Problems box:** `scripts/run_issues.py` keeps this run's problems in
`output/run_issues/<type>.json`. The runner resets it and checks MCP sign-in through the
agent CLI (`agent mcp list` / `claude mcp list`) before each report; the agent adds
problems as steps fail. `deliver_report.py send` shows them in a red box at the top of
the report (`scripts/issue_box.py`). Buttons: **Sign in to <server>**
(`engineering-pulse://auth`, opens Terminal) and **Re-run this report**
(`engineering-pulse://run`), handled by `scripts/fix_link.py`. If the agent writes no
report, `deliver_report.py ensure` still delivers one: Pulse is rendered from data
fetched during this run only (`render_daily_dashboard_html.py --since`), Sprint and
Compare get a short frame with the problems.

**Feature hints:** when `STAKEHOLDERS`, `SPRINT_BOARD` or `TODOIST_API_TOKEN` is unset,
the Pulse header shows a "✦ N more features" badge at the top right. Clicking it lists
what each feature adds and how to switch it on. Email copies leave the badge out.

**Compare:** `scripts/run_compare.sh <id-A> <id-B>` (or `make compare A= B=`) validates
the ids with `scripts/compare_reports.py prepare`, writes
`output/compare/context-<A>-vs-<B>.json`, and runs the `report-compare` skill through
`AGENT_CLI`. Log: `/tmp/engineering-pulse-compare.log`.

**Schedule:** `scripts/schedule.py show` / `set --days mon-sun --times 10:00` — edits the
installed LaunchAgent plist and reloads it. `scripts/settings.py show` / `set` also
covers `SCHEDULED_REPORTS`, `REPORT_AUTO_OPEN` and `REPORT_RETENTION_DAYS`, and backs
the calendar's Settings panel (`engineering-pulse://settings` links).

| Argument (`datadog_dashboard_extract.py`) | Default | Purpose |
|-------------------------------------------|---------|---------|
| `--from-dashboard-json FILE` | | MCP: build `*_mcp_query_plan.json` from saved dashboard JSON |
| `--from-mcp-responses FILE` | | MCP: build `*_metric_results.json` from MCP metric bundle |
| `--url` | | Dashboard URL (required with `--from-dashboard-json`) |
| `--days N` | `0` | Past N days (use `7` for daily run; MCP plan default 7) |
| `--output-slug` | | File prefix under `output/` |

**DATADOG_TEAMS:** replaces `tpl_var_team` in URL; injects `team:<value>` into queries.

**Time window:** `--days` → URL timestamps → 30-day fallback. `live=true` snaps `to_ts` to now.

## Caveats

1. Metric queries are fetched as base series. When a dashboard **Focus** list is set, each focused query-value formula (for example a percentage) is evaluated from those series. Logs/APM/RUM/DORA widgets are not metric queries and show `—`.
2. Template variables other than `$team` use dashboard defaults.
