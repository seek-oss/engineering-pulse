# DX build success — env and DX UI alignment

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DX_TOKEN` | yes | Personal access token with `datacloud:query` |
| `DX_BUILD_SUCCESS_TEAM` | no | Substring matched with `dxt.name ILIKE '%…%'` (default: `Example Team`) |
| `DX_BUILD_SUCCESS_PERIOD` | no | SQL interval literal: `3 months` (default, matches DX **Last 3 months** / `l3m`) or `12 weeks` |
| `DX_BUILD_SUCCESS_REPORT_URL` | no | “Open in DX” link (default built from team id when enriched) |

## Matching the DX report

| DX UI | This skill |
|-------|------------|
| Filter **Last 3 months** | `DX_BUILD_SUCCESS_PERIOD=3 months` |
| Team filter in DX URL (e.g. `teams=…`) | URL team ids may differ from Web API ids. SQL filters by **team name** via `DX_BUILD_SUCCESS_TEAM`, not URL id. |
| **Overall average** (e.g. 81.93%) | Pooled: `sum(successful_builds) / sum(total_builds)` over weeks in range |
| Weekly chart/table | `date_trunc('week', finished_at)` in SQL |
| Builds counted | `status` matching `succ%` vs `succ%` or `fail%` (same as your SQL) |

Using **`12 weeks`** in SQL while DX shows **3 months** will change the headline percentage.

## Definition (displayed on HTML report)

Build success rate is the number of successful builds divided by total builds. Use this metric to assess the reliability of your build process and ensure consistent build quality.
