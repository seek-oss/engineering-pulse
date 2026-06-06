# Step 2F — Stakeholder Pulse (Glean MCP)

Track named stakeholders in Slack over the past 7 days.

**Skip if `STAKEHOLDERS` is empty or unset.**

**Data source:** Glean MCP (`app: slack`, `from: <name>`, `updated: past_week`). Future:
read-only Slack token (not implemented). Card format: `prompts/_stakeholder-card-example.md`.

## Procedure

The section is **fully driven by `STAKEHOLDERS`** — never hardcode names. Parse the
list once, then produce exactly one card per parsed name. Adding a name to `.env` is
the only action needed for it to appear in the report.

1. **Parse names** — split `STAKEHOLDERS` on commas, strip whitespace, drop empties.
   This list is the single source of truth for the rest of the step.

2. **Clean stale cards** — delete every `*.md` in `output/stakeholders/` not starting with `_`.

3. **For each name in the parsed list** (process every one — do not stop early):

   a. Read Glean MCP `search` schema; typical call:
      - `app`: `"slack"`
      - `from`: full name or email (try Glean spelling hints if no hits)
      - `updated`: `"past_week"`
      - `query`: keywords or `"*"`
      - `sort_by_recency`: `true`

   b. Summarize into three bullets: **Themes**, **Notable** (with link), **Top links** (≤3).

   c. Write `output/stakeholders/<slug>.md` (`Jane Doe` → `jane-doe.md`; slug =
      lowercase, non-alphanumeric runs → `-`):

      ```markdown
      # <Display Name>

      - **Themes:** ...
      - **Notable:** [title](url) — context
      - **Top links:** [a](url), [b](url)
      ```

   d. No hits → single bullet: `No Slack activity in the last 7 days.`
      (Still write the card — every parsed name must end with a `<slug>.md` file.)

4. **Verify completeness before rendering** — confirm that for **every** parsed name a
   matching `output/stakeholders/<slug>.md` exists. If any are missing, generate them
   now; do not proceed with a partial set.

5. Run `render_daily_dashboard_html.py` **after** all cards exist. Defaults:
   stakeholder cards read from `output/stakeholders/`; HTML at
   `output/daily_dashboard_report.html`. The renderer renders one card slot per
   configured name and prints `Warning: STAKEHOLDERS set but Step 2F produced no card
   for: …` on stderr for any name still missing a card — treat that warning as a
   signal to backfill, not ignore.

## Caveats

- Glean indexes public Slack channels it can access — not DMs/private channels.
- Indexing delay (hours) may hide very recent messages.
