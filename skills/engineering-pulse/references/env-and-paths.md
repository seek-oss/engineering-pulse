# Environment and paths

## Environment variables (`.env`)

| Variable | Required | Purpose |
|----------|----------|---------|
| `AGENT_CLI` | for schedule | `claude` or `cursor` (set by installer). `pi`: **experimental / in progress** — see [`harness/pi-agent/`](../../../harness/pi-agent/). |
| `ANTHROPIC_API_KEY` | for Claude automation | API key when using Claude Code for scheduled runs |
| `PI_API_KEY` | experimental | Provider API key if testing `AGENT_CLI=pi` ([in progress](../../../harness/pi-agent/README.md)) |
| `DD_API_KEY` | yes | Datadog API key |
| `DD_APP_KEY` | yes | Datadog application key |
| `DD_SITE` | no | API host (default `https://api.datadoghq.com`) |
| `DATADOG_TEAMS` | no | Comma-separated teams — replaces `tpl_var_team` in URL **and** injects `team:<value>` into every metric query |
| `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_TO` | yes | Gmail SMTP credentials |
| `TODOIST_API_TOKEN` | no | Todoist API token (for My Queue) |
| `TODOIST_PROJECT_ID` | no | Auto-set by `python scripts/todo.py setup` |
| `STAKEHOLDERS` | no | Pulse names (Glean). **Leave this key out** of `.env` to omit Pulse entirely (ignored if only set via shell `export`). |
| `GITHUB_TOKEN` | for PRs | PAT with `repo` (read) + `read:org` |
| `GITHUB_ORG` / `GITHUB_TEAM` | for PRs | Org and team slugs |

### Datadog sites

| Site | `DD_SITE` |
|------|-----------|
| US1 (default) | `https://api.datadoghq.com` |
| EU | `https://api.datadoghq.eu` |
| US3 | `https://api.us3.datadoghq.com` |

### Gmail SMTP (one-time)

1. Enable 2-Step Verification on your Google account.
2. Create an App password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Add to `.env`:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
SMTP_FROM=you@gmail.com
SMTP_TO=recipient@example.com
```

## Gitignored user content

| Path | Purpose |
|------|---------|
| `prompts/dashboards/*.md` | Real Datadog URLs (except `_example.md`) |
| `prompts/extras/*.md` | Extra report cards |
| `output/` | All generated JSON/HTML |
| `output/stakeholders/*.md` | Glean-generated stakeholder cards |
| `.env` | Secrets |

## Script reference

**Extract:** `scripts/datadog_dashboard_extract.py` → `output/<slug>_metric_results.json`

**Render:** `scripts/render_daily_dashboard_html.py` — default HTML at
`output/daily_dashboard_report.html`; args include `--out`, `--dashboards-dir`,
`--output-dir`, `--prs`, `--todos`, `--extras-dir`, `--stakeholders-dir`, `--extra LABEL:FILE`

| Argument (`datadog_dashboard_extract.py`) | Default | Purpose |
|-------------------------------------------|---------|---------|
| `--url` | | Dashboard URL |
| `--days N` | `0` | Past N days (use `7` for daily run) |
| `--focus "a,b"` | | Highlight widgets in console |
| `--output-slug` | | File prefix under `output/` |

**DATADOG_TEAMS:** replaces `tpl_var_team` in URL; injects `team:<value>` into queries.

**Time window:** `--days` → URL timestamps → 30-day fallback. `live=true` snaps `to_ts` to now.

## Caveats

1. Base metric queries only — no client-side formula arithmetic.
2. Logs/APM/RUM widgets skipped (tile shows `—`).
3. Template variables other than `$team` use dashboard defaults.
