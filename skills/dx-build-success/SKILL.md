---
name: dx-build-success
description: >
  Build a DX-style Build success rate HTML dashboard for one DX team: run Data Studio
  SQL via DX_TOKEN, show overall %, weekly area chart with trendline, and breakdown table.
  Use for DX build success rate, CI reliability, or /dx-build-success.
---

# DX Build success rate

On-demand report mirroring the DX **Build success rate** catalog view (overall %, weekly chart, team table).

## Prerequisites

- Workspace root: cloned repo or `~/.engineering-pulse`
- `DX_TOKEN` in `~/.engineering-pulse-data/.env` (scope `datacloud:query`) — see [dx-api.md](references/dx-api.md)
- Optional: `DX_BUILD_SUCCESS_TEAM`, `DX_BUILD_SUCCESS_PERIOD` — [env-and-alignment.md](references/env-and-alignment.md)

## Workflow

1. Confirm `DX_TOKEN` is set (read [env-and-paths.md](../engineering-pulse/references/env-and-paths.md)).
2. Run query and write JSON:

```bash
python3 scripts/dx_studio.py run \
  --sql-file skills/dx-build-success/references/build-success-rate.sql \
  --out output/dx_build_success_raw.json \
  --enrich-team
```

3. Render HTML:

```bash
python3 scripts/render_dx_build_success_html.py \
  --data output/dx_build_success_raw.json \
  --out output/dx-build-success-<team-slug>-<YYYY-MM-DD>.html
```

4. Tell the user the output path. Do **not** open the browser unless asked.

## Overrides

CLI flags on `dx_studio.py`:

- `--team "Example Team"` — overrides `DX_BUILD_SUCCESS_TEAM`
- `--period "3 months"` — overrides `DX_BUILD_SUCCESS_PERIOD` (allowlisted)

## Failures

- Missing token → stop with setup link to [dx-api.md](references/dx-api.md)
- SQL or API error → show `query_run.error` message from DX
- Empty weekly totals → report “no builds in period” in HTML

## Output

- Raw: `output/dx_build_success_raw.json` (on-demand) or `output/<slug>_dx_build_success.json` (pulse Part)
- Standalone report: `output/dx-build-success-*.html` (self-contained, DX-like layout)
- **Engineering Pulse:** add `prompts/dashboards/dx_build_success.md` to
  `~/.engineering-pulse-data/dashboards/`, run `scripts/dx_build_success_extract.py` before
  `render_daily_dashboard_html.py` — the daily report embeds the full chart (see
  `skills/engineering-pulse/references/daily-workflow.md`).
