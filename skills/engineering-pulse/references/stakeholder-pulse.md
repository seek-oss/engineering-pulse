# Step 2F — Stakeholder Pulse (Glean MCP)

Track named stakeholders in Slack over the past 7 days.

**Skip if `STAKEHOLDERS` is empty or unset.**

**Data source:** Glean MCP (`app: slack`, `from: <name>`, `updated: past_week`). Future:
read-only Slack token (not implemented). Card format: `prompts/_stakeholder-card-example.md`.

## Procedure

1. **Clean stale cards** — delete every `*.md` in `output/stakeholders/` not starting with `_`.

2. **For each name** in `STAKEHOLDERS` (comma-separated, strip whitespace):

   a. Read Glean MCP `search` schema; typical call:
      - `app`: `"slack"`
      - `from`: full name or email (try Glean spelling hints if no hits)
      - `updated`: `"past_week"`
      - `query`: keywords or `"*"`
      - `sort_by_recency`: `true`

   b. Summarize into three bullets: **Themes**, **Notable** (with link), **Top links** (≤3).

   c. Write `output/stakeholders/<slug>.md` (`Jane Doe` → `jane-doe.md`):

      ```markdown
      # <Display Name>

      - **Themes:** ...
      - **Notable:** [title](url) — context
      - **Top links:** [a](url), [b](url)
      ```

   d. No hits → single bullet: `No Slack activity in the last 7 days.`

3. Run `render_daily_dashboard_html.py` **after** cards exist (renderer default:
   `output/stakeholders/`).

## Caveats

- Glean indexes public Slack channels it can access — not DMs/private channels.
- Indexing delay (hours) may hide very recent messages.
