# Add Dashboard

Interactive workflow to add a Datadog dashboard to the daily report.

## 1. Gather inputs

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

## 4. Generate dashboard file

Create **`prompts/dashboards/custom_<slug>.md`** with URL, slug, focus, metrics table,
and optional colouring rules. Use `custom_` prefix (gitignored user content). No REST
extract command block — the daily agent follows [datadog-mcp-extract.md](datadog-mcp-extract.md).

## 5. Confirm

- File at `prompts/dashboards/custom_<slug>.md`
- No `.env` change needed (URL in file)
- Next daily run picks it up automatically
