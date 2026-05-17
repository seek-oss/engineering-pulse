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

```bash
python3 scripts/datadog_dashboard_extract.py \
  --url '<DASHBOARD_URL>' \
  --output-slug <SLUG> \
  --days 7
```

Read `output/<slug>_dashboard_extracted_queries.json` for widget titles.

## 3. Present widgets

Table: # | Title | Source | Queryable? Confirm selections with user.

## 4. Generate dashboard file

Create **`prompts/dashboards/custom_<slug>.md`** with URL, slug, focus, extract command,
metrics table, and optional colouring rules. Use `custom_` prefix (gitignored user content).

## 5. Confirm

- File at `prompts/dashboards/custom_<slug>.md`
- No `.env` change needed (URL in file)
- Next daily run picks it up automatically
