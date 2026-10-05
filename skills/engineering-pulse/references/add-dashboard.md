# Add Dashboard

Interactive workflow to add a Datadog dashboard to the daily report.

## 1. Gather inputs

Ask for anything the user has not given yet, starting with the dashboard URL: open the
dashboard in Datadog and copy the address from the browser. Datadog MCP must be signed
in; if a Datadog tool call fails with an auth error, tell the user to run
`agent mcp login <server>` (Cursor) or `/mcp` (Claude Code) and try again.

| Input | Example |
|-------|---------|
| **Dashboard URL** | `https://app.datadoghq.com/dashboard/abc-xyz/...` |
| **Short name** | `DORA Metrics` |
| **Slug** | `dora` |
| **Focus** | natural language widget interests |

## 2. Discover widgets

1. Datadog MCP **`get_datadog_dashboard`** for the dashboard ID from the URL → save
   `output/<slug>_dashboard.json`.
2. Run the query-plan step from [datadog-mcp-extract.md](datadog-mcp-extract.md) § 1B.

Read `output/<slug>_dashboard_extracted_queries.json` for widget titles.

## 3. Present widgets

Table: # | Title | Source | Queryable? Confirm selections with user.

## 4. Agree colour thresholds

A tile without a colouring rule is always green when it has a value, so red and yellow
never show. For each selected metric, propose RED / YELLOW / GREEN thresholds (use the
widget's own conditional formats or markers from the dashboard JSON when present,
otherwise a sensible default for the metric) and ask the user to confirm or change them.
Skip a metric only if the user says it has no good or bad direction.

## 5. Generate dashboard file

Create **`prompts/dashboards/custom_<slug>.md`** with URL, slug, focus, metrics table,
and the **Colouring rules** table agreed in step 4 (same format as
[`prompts/dashboards/_example.md`](../../../prompts/dashboards/_example.md)). Use `custom_`
prefix (gitignored user content). No REST extract command block — the daily agent follows
[datadog-mcp-extract.md](datadog-mcp-extract.md).

## 6. Confirm

- File at `prompts/dashboards/custom_<slug>.md`
- No `.env` change needed (URL in file)
- Next daily run picks it up automatically
