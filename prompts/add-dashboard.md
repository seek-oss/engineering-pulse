# Add Dashboard

## Overview

Interactive command to add a new Datadog dashboard to the daily report.
Run this when you want to start monitoring a new dashboard — it discovers
available widgets, asks what you care about, and appends a new Part section
to `prompts/daily-dashboard.md`.

---

## Workflow

### 1. Gather inputs

Ask the user (or extract from their message):

| Input | Example |
|-------|---------|
| **Dashboard URL** | `https://app.datadoghq.com/dashboard/abc-xyz/my-dashboard?...` |
| **Short name** | `DORA Metrics` |
| **Slug** (lowercase, underscores) | `dora` |
| **What they care about** | "deploy rate", "error rate" (natural language is fine) |

### 2. Discover widgets

Run the extraction script with the URL directly:

```bash
python3 scripts/datadog_dashboard_extract.py \
  --url '<DASHBOARD_URL>' \
  --output-slug <SLUG> \
  --days 7
```

Then read `output/<slug>_dashboard_extracted_queries.json` to get the list of
all widget titles and their query sources.

### 3. Present widgets to user

Show a summary table of discovered widgets:

| # | Widget Title | Source | Queryable? |
|---|-------------|--------|------------|

Highlight the ones matching the user's description. Ask the user to confirm
which widgets they want in their report.

### 4. Generate Part section

Based on the user's selections, generate a new Part section in this format:

```markdown
#### Part X — <Short Name>

- **URL:** `<DASHBOARD_URL>`
- **Slug:** `<slug>`
- **Focus:** `<comma-separated focus terms>`

\```bash
python3 scripts/datadog_dashboard_extract.py \
  --url '<DASHBOARD_URL>' \
  --output-slug <slug> \
  --days 7 \
  --focus "<focus terms>"
\```

**Metrics to extract:**

| Metric | Widget title contains |
|--------|-----------------------|
| <Label> | `<Title substring>` |
| ... | ... |

**Colouring rules:**

| Metric | RED | YELLOW | GREEN |
|--------|-----|--------|-------|
| <Label> | <condition> | <condition> | <condition> |

**Report rendering:** <N> tiles in a row, <description of layout>.
```

For colouring rules, infer sensible defaults from the metric type:
- Percentages: RED < 50%, YELLOW 50–75%, GREEN > 75%
- Counts (errors, incidents): RED > 0, GREEN 0
- Rates: adapt based on context

Ask the user to confirm or adjust the colouring rules.

### 5. Save as a new dashboard file

Create a new file at **`prompts/dashboards/custom_<slug>.md`** with the generated
Part section content. The `custom_` prefix ensures user-added files never collide
with shipped dashboard names on future upgrades.

Determine the correct Part letter by counting existing `.md` files in
`prompts/dashboards/` (A, B → next is C, etc.).

All dashboard files in this directory are **gitignored** (they contain real
Datadog URLs), so they stay on the user's disk only. The `custom_` prefix
is a naming convention to keep things organised.

### 6. Update the renderer command

If the new dashboard is not Part A or Part B (which have built-in rendering),
remind the user to pass `--extra` when running the renderer:

```bash
python3 scripts/render_daily_dashboard_html.py \
  --extra "<Short Name>:output/<slug>_metric_results.json"
```

### 7. Confirm

Tell the user:
- The new dashboard file has been created at `prompts/dashboards/custom_<slug>.md`
- The URL is embedded in the file — no `.env` changes needed
- The file is **gitignored** — your Datadog URLs will never be committed
- Next time the daily dashboard runs, it will pick up the new file automatically

---

## Example session

```
User: add my DORA dashboard at https://app.datadoghq.com/dashboard/xyz-123

Agent: I'll set up DORA Metrics. Let me discover the widgets...

[runs extract script]

Found 12 widgets:
  #0  Deployment Frequency    (metrics_formula) ✓ queryable
  #1  Lead Time for Changes   (metrics_formula) ✓ queryable
  #2  Change Failure Rate     (metrics_formula) ✓ queryable
  #3  Time to Restore         (logs)            ⚠ partial
  ...

Based on your mention of "deploy rate", #0 Deployment Frequency looks relevant.
Which widgets do you want in the report? (e.g. "0, 1, 2" or "all queryable")

User: 0 and 2

Agent: Generated Part C — DORA Metrics:
  - Deployment Frequency: GREEN > 10/week, YELLOW 5-10, RED < 5
  - Change Failure Rate: GREEN < 5%, YELLOW 5-15%, RED > 15%

Look good? I can adjust the thresholds.

User: looks good

Agent: ✓ Created prompts/dashboards/custom_dora.md
       → URL is embedded in the file — no .env changes needed
       → Next daily run will include DORA metrics
       → This file won't conflict with future upstream upgrades
```
