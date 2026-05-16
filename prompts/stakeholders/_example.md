<!-- SKIP: This is a reference example only. Do NOT include this file in the report. -->

# Example — Stakeholder Pulse card

> **This file is a format reference only.** The renderer skips any file in
> this directory whose name starts with `_`.
>
> Real stakeholder cards are written here automatically by the daily
> dashboard agent — see **Step 2F — Stakeholder Pulse** in
> `prompts/daily-dashboard.md`. You should not need to edit these files
> by hand.

---

## How it works

Each `*.md` file in `prompts/stakeholders/` becomes one card under
**Stakeholder Pulse** (next dynamic Part letter) in the daily report — only
when `STAKEHOLDERS` in `.env` is non-empty (the HTML renderer enforces that).

- The first `# Heading` is used as the stakeholder's display name.
- Everything below is rendered as the card body (3-bullet summary).
- The agent regenerates this folder on every run: any non-`_*.md`
  files are deleted first, then one file is written per name in the
  `STAKEHOLDERS` env var.

## Expected per-stakeholder format

The agent should produce files that look like this:

```
# Jane Doe

- **Themes:** Spent the week pushing the new orchestrator design and
  unblocking the streaming team on schema migrations.
- **Notable:** [Decided to defer the v2 cutover to Q3](https://xyz.slack.com/archives/C123/p1700000000000000)
  — full thread in `#platform-eng`.
- **Top links:** [#platform-eng](https://xyz.slack.com/archives/C123),
  [thread on schema migration](https://xyz.slack.com/archives/C123/p1700000000000001),
  [RFC link drop](https://xyz.slack.com/archives/C123/p1700000000000002)
```

If the agent finds **no Slack activity** for a person in the last 7
days, the file should contain a single bullet:

```
# Jane Doe

- No Slack activity in the last 7 days.
```

## Privacy / scope notes

- Glean only indexes content it has been granted access to — typically
  **public Slack channels only**. DMs and private channels will not
  surface.
- Glean indexes on a delay (often a few hours), so very recent activity
  may not appear until the next run.
