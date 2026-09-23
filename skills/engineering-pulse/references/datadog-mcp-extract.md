# Step 1 — Extract Datadog dashboards (Datadog MCP)

Use **Datadog MCP** (OAuth in Cursor / Claude Code). **`scripts/datadog_dashboard_extract.py`**
only supports the MCP offline steps (`--from-dashboard-json`, `--from-mcp-responses`); it
does not call the Datadog REST API.

**Time window:** past **7 days** (`from: now-7d`, `to: now` on every metric call).

For **each** dashboard in `prompts/dashboards/` (skip `_*.md`):

## 1A — Fetch dashboard definition

1. Read **URL** and **Slug** from the dashboard `.md` file.
2. Extract dashboard ID from the URL (path segment after `/dashboard/`).
3. Call Datadog MCP **`get_datadog_dashboard`**:
   - `dashboard_id`: that ID
   - `include_widgets`: `true`
   - If the URL sets `tpl_var_team`, pass matching `template_variable_values`
     (e.g. `team` → value from `DATADOG_TEAMS` in `.env`, or from the URL).
4. Save the full JSON response to **`output/<slug>_dashboard.json`**.

## 1B — Build query plan (local script, no keys)

```bash
python3 scripts/datadog_dashboard_extract.py \
  --from-dashboard-json "output/<slug>_dashboard.json" \
  --url '<URL from the dashboard .md file>' \
  --output-slug <slug> \
  --days 7
```

Writes:

- `output/<slug>_dashboard_extracted_queries.json`
- `output/<slug>_mcp_query_plan.json` — list of resolved metric queries

## 1C — Execute metric queries (MCP)

For **every** entry in `output/<slug>_mcp_query_plan.json` → `queries`:

Call **`get_datadog_metric`** with:

- `from`: plan `time_window.from` (typically `now-7d`)
- `to`: plan `time_window.to` (typically `now`)
- `response_format`: `scalar`
- `queries`: one structured object per call, e.g.
  `{ "query": "<query string from plan>", "aggregator": "last", "name": "q0" }`

Collect each response’s **JSON_DATA** (the JSON array) into one bundle file:

**`output/<slug>_mcp_responses.json`**

```json
{
  "dashboard_title": "...",
  "source_url": "...",
  "time_window": { "from": "now-7d", "to": "now" },
  "responses": [
    {
      "widget_title": "...",
      "kind": "metrics",
      "query": "avg:...",
      "data": [ ... JSON_DATA from get_datadog_metric ... ]
    }
  ]
}
```

Process **all** plan queries before Step 1D. On MCP failure for one query, still
include a `responses` entry with `"data": null` so the tile can show `—`.

## 1D — Build HTML snapshot (local script)

```bash
python3 scripts/datadog_dashboard_extract.py \
  --from-mcp-responses "output/<slug>_mcp_responses.json" \
  --url '<URL from the dashboard .md file>' \
  --output-slug <slug>
```

Writes **`output/<slug>_metric_results.json`** for the renderer.

## Caveats

- Same as [env-and-paths.md](env-and-paths.md): base metric queries only; logs/APM/RUM
  widgets may show `—`.
- Scheduled headless runs need Datadog MCP authenticated in that agent session (Cursor
  CLI / Claude Code MCP config).
