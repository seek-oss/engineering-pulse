---
name: sprint-burndown
description: "Build an evidence-based sprint progress report from Jira for a team's delivery tickets under epics whose summary starts with a user-supplied prefix. Produces both a burn-up chart (primary, SDD-friendly) and a burn-down chart with a rolling-scope expectation line, plus event ledger and per-ticket table. Configured via one free-form SPRINT_BOARD sentence in .env. Use for sprint delivery tracking, scope-change analysis, remaining-work reports, and daily/scheduled progress email."
---

# Sprint Burndown

Generate a daily burndown for one team's delivery tickets on a mixed Jira board. Reconstruct historical work from evidence; distinguish completion from scope changes. Produce a team-scoped custom report.

## Quick start

Set `SPRINT_BOARD` in `.env` — one free-form sentence describing your sprint board. See the template and inline commentary in [`.env.example`](../../.env.example).

When you invoke the skill, the agent loads `SPRINT_BOARD`, parses the board URL for Atlassian host / project / board id, discovers `cloudId` and custom-field ids at runtime, and picks the active sprint. If more than one active sprint is a plausible match, it asks which one.

For one-off runs or overrides, paste the same sentence into the chat instead — chat input takes precedence over `.env`.

Every value the agent resolves is captured in the run's report so subsequent runs are reproducible. The rest of this file is the detailed spec the agent follows; you should not need to edit it to reuse the skill.

## Jira access and metadata

**Atlassian MCP only.** Do not open Jira in the IDE browser, do not use CDP, do not prompt the user to log in to Jira, and do not call Jira REST from a browser session. MCP is already authenticated. The IDE browser is a different, usually logged-out session — opening the board there is what triggers a login prompt.

If a needed Agile/REST endpoint is not an MCP tool, reconstruct from MCP issue search/get (sprint field on issues, `expand=changelog`, `statusCategory` fallback) and disclose the approximation. Never treat a missing Agile API as a reason to open a login tab. If MCP is unavailable or returns auth errors, stop and tell the user to reconnect the **Atlassian MCP** server.

Discover per-instance identifiers at runtime — do not hard-code them into the skill.

- Use Atlassian MCP: `getAccessibleAtlassianResources`, `searchJiraIssuesUsingJql`, `getJiraIssue`, and any other Jira MCP tools that are present. Do not invent HTTP calls to make up for tools that are absent.
- Host and `cloudId`: parse the host from the board URL; fetch `cloudId` via `getAccessibleAtlassianResources`. Pass the site hostname (e.g. `example.atlassian.net`) or the UUID as `cloudId`.
- Search: `searchJiraIssuesUsingJql` (Jira `POST /rest/api/3/search/jql`). Paginate with `nextPageToken` until `isLast`.
- Issue: `getJiraIssue`.
- History: `getJiraIssue` with `expand=changelog`. If the payload is truncated, label coverage partial — do not open a browser to paginate `/changelog`.
- Sprints: resolve from the Sprint custom field on issues (commonly `customfield_10018`) returned by MCP search. Collect unique sprint objects (`id`, `name`, `state`, `startDate`, `endDate`, `completeDate`) from those fields. Do not call `/rest/agile/1.0/board/{id}/sprint`.
- Board configuration: if no MCP tool returns column mappings or estimation settings, use `statusCategory = Done` as the completion fallback and label it. Do not fetch `/rest/agile/1.0/board/{id}/configuration` via browser.
- Custom-field ids: infer from issue payloads (`*all` or known sprint/points fields). Sprint is commonly `customfield_10018`; story points are commonly `customfield_10024` or `customfield_10025`. Choose one point field for the report, not a per-ticket mixture.

Paginate searches completely, split large JQL, and respect throttling. Request summary, issue type, status/id/category, assignee, parent/epic relationship, labels, sprint, selected point field and creation time. Fetch relevant sprint, status, point, parent and scope-field history via MCP. Capture retrieval time and source provenance; avoid inconsistent snapshots if tickets change during retrieval.

## Workflow

1. Resolve inputs, sprint, board settings and reporting dates.
2. Discover matching epics and candidate delivery tickets, including past sprint members.
3. Retrieve full relevant history and assess coverage.
4. Freeze baseline and reconstruct work at each observation time.
5. Calculate ideal, actual and change breakdowns.
6. Validate reconciliations, render the chart and save this run's report.

## 1. Dates and baseline

Before calculating anything, state the resolved board, prefix, sprint name/id, time window, baseline timestamp, unit and completion rule so the user can verify. Ask once for missing or ambiguous inputs; resolve casual phrases such as "Monday for two weeks" against actual board sprint objects in the configured timezone. Read-only discovery can precede this statement; no confirmation is needed when inputs are clear.

Keep these concepts separate:

- **Jira dates:** actual `startDate`, planned `endDate`, and `completeDate` if closed.
- **Team display window:** explicit team dates, else unambiguous dates on the sprint-goals card, else Jira's Melbourne calendar dates. Disclose any mismatch.
- **Baseline `t0`:** Jira's actual sprint start by default. A documented planning-complete timestamp may override it, but must be fixed independently of later completions.

Do not infer a planning timestamp from when cards happened to close. A goals card that supplies dates alone does not establish a different commitment timestamp. If Jira starts Sunday evening, keep that baseline as a labelled “Start” point before Monday. Do not replace it with Monday's end-of-day remaining work.

If an explicit alternative `t0` is used, label the report “baseline set at [timestamp]” and separately disclose activity between Jira start and `t0`. Do not claim an exact native Jira comparison. Reuse the same evidenced baseline convention on later runs, and disclose an intentional correction.

Include unfinished delivery tickets carried over and selected by `t0` in baseline work. Label them carryover when prior-sprint membership is evidenced. They burn down when completed in this sprint. Never exclude delivery work merely because it came from the previous sprint.

Exclude administrative/planning cards only through explicit user-agreed keys, labels or a documented rule; list exclusions and apply them throughout the calculation. Do not infer exclusions from age or summary alone. Already-Done tickets contribute zero at `t0`. A claimed late administrative status update requires evidence; otherwise use recorded transition time and disclose the discrepancy.

Validate that the endpoint is after `t0`. If a future sprint has no actual start, report planned scope only; do not fabricate an actual baseline or history.

## 2. Scope and ticket discovery

Never invent a sprint. When the board has multiple active sprints (common on mixed boards), narrow candidates to sprints containing at least one ticket under a prefix-matched epic; if more than one still fits, ask the user which one before proceeding.
**Always resolve to a specific sprint id before querying tickets.** Do not use `sprint in openSprints()` in the ticket-membership query. On mixed boards, that JQL function can silently return a truncated ticket set (its per-project resolution and pagination interact badly with `parent in (...)` compound queries — sometimes marking `isLast: true` well before all matches are returned). The correct two-step pattern is:

1. Discover active sprint objects from the Sprint custom field on a small MCP search under prefix-matched epics (request `customfield_10018` / the sprint field). Resolve the target `<sprintId>` from those objects. If more than one active sprint still fits, ask which one.
2. Query tickets with the specific id via `searchJiraIssuesUsingJql`: `sprint = <sprintId> AND parent in (<freshEpicKeys>) ORDER BY key ASC`. Paginate to `isLast: true`.

Re-query epics every run. Never keep a hard-coded epic-key list. Use JQL to retrieve candidates, then verify that the returned summary literally starts with the configured prefix; text search is not an exact prefix test.

Example candidate epic search (substitute the user's supplied prefix):

```jql
summary ~ "\"[TEAM-PREFIX]\"" AND issuetype = Epic ORDER BY key ASC
```

If punctuation/tokenization makes this unreliable, retrieve board-relevant epics more broadly and apply the literal prefix check locally.

### Counting level

Count standard-level delivery tickets directly under matching epics: Stories, Bugs, Tasks, Spikes, Tests, Incidents, or equivalent configured standard types. Exclude Epics and Subtasks. Use issue-type metadata rather than assuming names exist. These are **standard-level tickets**, not “leaves”; a Story may itself have subtasks. Never count both a Story and its Subtasks.

Use this only as a current-membership discovery seed:

```jql
parent in (<freshEpicKeys>) AND sprint = <sprintId>
```

Apply the board saved-filter scope as well. Never require the epic prefix on child summaries. Resolve legacy epic-link fields if this project's hierarchy needs them.

### Historical membership coverage

Current `sprint = <sprintId>` results alone are insufficient: removed tickets may no longer match. The candidate set must cover every ticket that could have belonged to this report during the interval.

Prefer an available authoritative sprint report/export containing original, added and removed issues. Otherwise search the relevant board projects broadly enough to include removed/reparented issues and inspect their full history. Bound searches only using conditions that cannot exclude valid historical members. Do not assume `sprint WAS` is supported. Record the discovery route and its coverage.

Reconstruct membership in the target sprint and epic scope at each timestamp. Treat moves into/out of this team's epics as scope changes. Retrieve historical parent epics and relevant summary history where necessary; a rename must not silently rewrite the whole report. If historical board-filter membership cannot be evaluated, disclose the current-filter approximation and its consequences. Never silently treat current parent/filter/prefix membership as historical fact.

List deleted, inaccessible or otherwise unrecoverable issues when known. If complete historical discovery cannot be established, label coverage partial; do not claim a complete historical burndown solely because all currently visible tickets were fetched.

## 3. Completion and units

### Completion rule

Use the statuses mapped to the board's rightmost column as Done, listing their IDs/names in the caption. Reconstruct each issue's status at each timestamp; do not use the first Done date or resolution date as permanent completion.

If board mapping is unavailable, use an explicit team definition when supplied. Otherwise clearly label `statusCategory = Done` as a fallback and state that native Jira results may differ. Map historical status IDs to the rule. If configuration changed during the sprint and old mappings are unavailable, disclose that current mappings are applied consistently.

### Unit selection

- Honor an explicit ticket-count choice: each eligible unfinished ticket weighs 1.
- With no explicit choice, use points only if the board uses story points and every included delivery ticket has a known valid estimate across the reported states. Otherwise default to ticket count and explain why.
- Keep one unit for the whole chart. Never switch units midway or add counts to points.
- Treat an empty estimate as unknown, not zero. A deliberately assigned numeric zero is different.
- If the user explicitly requests points despite missing estimates, label it “estimated-work burndown,” report unestimated unfinished ticket counts alongside it, and withhold overall delivery judgments. Missing historical estimates also limit historical totals.
- Reconstruct point changes over time. Do not apply today's points to all prior days. Distinguish estimate increases/decreases from added/removed tickets and completion.
- Display “unestimated” or “N/A” for empty point fields, not “0 SP.”

## 4. Reconstruct actual remaining work

Use a deterministic calculation over chronological events, not a visual guess or manually invented daily values. For each issue, reconstruct initial state plus every relevant change. Use both `from` and `to` values and verified creation state; sprint membership may already exist at creation. Do not equate creation time with join time without evidence.

### Two-tier changelog scan (mandatory)

Fetch the full changelog via `getJiraIssue` with `expand=changelog` for **every** ticket in these two tiers:

1. **Tier 1 — every currently-Done ticket in scope.** Needed for exact completion timestamps and to detect any reopen/rejoin events.
2. **Tier 2 — every ticket whose current Sprint field lists more than one sprint id, OR whose `created` timestamp is on or after `t0`.** Needed to distinguish original commitments from carryover, bulk-load additions, out-of-plan (OPM) session additions, and post-`t0` creation.

Do not approximate sprint-join timestamps from `created` when the changelog is fetchable — approximation is only acceptable when MCP blocks the changelog (Bedrock guardrail, throttling, etc.). Affected tickets must be flagged as "partial history" in the ticket table and coverage labelled partial. If any Tier-1 changelog is blocked, do not assume the current `resolutiondate` is the completion time — it may reflect a reopen. Disclose.

Track all join, remove and rejoin events, status transitions including reopenings, estimate changes, and scope-membership changes. Match the target sprint by ID within the sprint-ID set; a change mentioning an old sprint is not automatically a new join.

Let `eligible(issue, t)` mean: the issue exists, is an included standard-level delivery ticket, belongs to the target sprint and team/board scope at `t`, and is not explicitly excluded.

```text
weight(issue, t)    = 1 for ticket count, or the selected point value at t
contribution(i, t)  = weight(i, t) if eligible(i, t) and not Done(i, t), else 0
remaining(t)       = sum(contribution(i, t))
B                  = remaining(t0)
```

Process same-history-entry changes atomically. Preserve source order where known; if simultaneous changes make cause attribution ambiguous, disclose a combined event rather than inventing a sequence. An unknown relevant state makes that issue's historical contribution unknown, not zero.

Take baseline state after changes effective at `t0`; changes strictly after `t0` are subsequent events. An addition after `t0` is labelled “added after baseline”; do not assume it was unexpected or unauthorized. Show carryover separately from later additions.

For completed weekday snapshots, use local end-of-day boundaries consistently (events before the next Melbourne midnight). Include weekend events in the next weekday snapshot; preserve their actual timestamps in the event table. Never discard weekend activity.

Stop observations at now for an active sprint and at `completeDate` for a closed sprint. Do not include post-close changes. Keep unknown observations as gaps, never zeroes, and do not connect lines across unknown intervals as though verified. If baseline or historical coverage is unknown, show a clearly labelled partial series or current snapshot; suppress a precise ideal/delta when B is unknown.

Never copy another ticket's join time, estimate or status history. Captioning a guess does not make it historical evidence.

## 5. Charts, timing and interpretation

The report includes **two charts** for the same underlying evidence: a **burn-up** (primary — see §5b) and a **burn-down** (secondary — see §5a). Both share the baseline `B`, the event ledger, and the pace calculations defined in §5c.

### 5a. Burn-down chart (secondary)

Freeze the ideal baseline `B`. Subsequent additions, removals, estimate changes or completions must not reset `B`.

Define the target endpoint from explicit team dates when provided, otherwise Jira's planned `endDate`. For date-only team windows use the end of the last working day. Disclose the exact endpoint and any difference from Jira. A closed sprint's actual endpoint is its completion timestamp; retain the original ideal target rather than recalculating the ideal to fit early/late closure.

Let `N` be the number of included working-day intervals between `t0` and the target endpoint. Each included date is one unit; if the first/last date is partial, count its available interval as one unit and disclose this daily-granularity convention.

```text
Start:                  ideal(0) = B
After working day k:    ideal(k) = B * (1 - k / N), k = 1 ... N
Completed-day delta:    actual(k) - ideal(k)
Original average pace:  B / N
```

Plot the explicit Start point plus daily endpoints. Example: `B=20`, `N=10` gives Start=20, end of day 1=18, day 2=16, day 10=0. Reject `N=0` as an invalid ideal window; do not divide by zero.

**Rolling-scope expectation line (SDD-friendly overlay).** A frozen ideal is misleading when total scope grows substantially after `t0` — actuals exceed the ideal by construction, not by delivery performance, which is common under Spec-Driven Development. Alongside the frozen ideal, plot a **piecewise-linear expectation line**:

- At `t0`, the expectation starts at `B` and drops linearly to `0` at the endpoint.
- **On every scope-add event of ≥1 unit**, the expectation resets: from that date's `(now, current_remaining)`, draw a fresh linear drop to `(endpoint, 0)`.
- Completions do **not** reset the line (they move the actual line down against a stable target, so good news is visible as "below expectation").
- Scope-removals do **not** reset the line (removing work already in flight must not create a false credit).

The result is a stepped line with upward jumps at scope adds and flat descents between. Actual vs. expectation measures true delivery pace at each moment: above = falling behind the running commitment; below = ahead of it. The frozen `B` remains in the header for the audit trail.

Use "above," "at," or "below the ideal line." Do not mechanically convert that result into "delivery on track." Explain original-scope completion, scope added/removed, reopenings, estimate changes and known blockers. Any delivery-confidence assessment is qualitative and must be separated from the arithmetic. Ticket-count pace measures ticket throughput, not equal-sized effort or individual productivity.

### 5b. Burn-up chart (primary)

Plot two cumulative lines from `t0` to the endpoint:

- **Total scope** — number of eligible tickets in scope at each observation (rises with adds, dips with removes, ignores completions).
- **Completed** — cumulative completions of tickets that were in scope at the moment of completion.

Fill the area between the two lines lightly to visualise remaining work at each date.

**Reading rules.**

- Delivery pace = slope of the completed line.
- Scope stability = slope of the scope line.
- Remaining work = vertical gap between the lines.
- Sprint is delivered when the two lines meet; the x-coordinate of the intersection is the delivery date.

**Two "on-track" overlays are required.**

1. **Projection lines** (dashed, faint) from today's marker:
   - Extend the **completed line** at trailing-`M`-working-day pace (default `M=5`; drop to `M=3` if fewer than 5 completed working days have elapsed).
   - Extend the **scope line** flat at its current value (assumes no further scope changes).
   - Where they cross is the projected delivery date. If they do not cross within the plotted window, state so explicitly.
2. **Pace ratio** (headline tile, not a chart line):

   ```text
   recent_pace   = completions in trailing M working days / M
   required_pace = (current_scope − current_completed) / working_days_left_to_endpoint
   ratio         = recent_pace / required_pace
   ```

   Report `ratio`, both raw paces, and a qualitative bucket: **`≥1.0 = on pace`, `0.8–1.0 = watch`, `<0.8 = intervene`**. Do not convert "watch" or "intervene" into an unqualified "off track" verdict — it is a pace call, not a delivery call.

Optionally overlay a **target reference line** from `(t0, 0)` to `(endpoint, current_scope)` — the linear ideal completion trajectory for the current committed scope. If drawn, note that this line swings upward as scope grows (so it is not comparable across days at different scope levels).

Do not use "above/below the ideal" language for the burn-up itself; the pace ratio and projection intersection carry that signal instead.

### 5c. Shared calculations

Use the latest completed working-day observation for the headline daily comparison in both charts. Optionally show a separate live point labelled "as of [timestamp]"; do not compare a morning live actual against an evening target as if the day had ended. If no working day has finished, report baseline and live remaining without a daily pace verdict.

Calculate required average pace from the completed-day cutoff: remaining at that cutoff divided by working days left until the target. If none remain, report "target reached" when remaining is zero, or "unfinished at target" otherwise. Do not calculate an infinite/undefined pace. For an active sprint beyond target, extend actual observations through now, keep the burn-down ideal at zero after the original endpoint, and label overdue work. Do not stretch the ideal.

Reconcile remaining changes with an event ledger:

```text
remaining = B
          + unfinished work added to scope
          - unfinished work removed from scope
          + reopened work
          - work completed while in scope
          + net estimate changes affecting unfinished in-scope work
```

Record both gross scope changes (including already-Done additions/removals) and their actual effect on remaining. Do not count removal as delivery. For atomic combined events, keep a separate combined adjustment with before/after contribution so the ledger still reconciles without double counting. Unknown attribution remains explicitly unknown.

## 6. Report and files

Fetch data anew for each run; never reuse a previous report as evidence.

### Required layout (top to bottom)

Produce a single HTML file with these sections in this exact order:

1. **Header** — sprint, board, prefix, team window, baseline timestamp, target, as-of time, timezone, unit, completion rule, and coverage label (complete / partial / snapshot-only). Enumerate missing history and approximations here or in Methods.
2. **At-a-glance tile row** — 5–6 stat tiles prominent at the top, before any chart. Required tiles: **Total scope**, **Completed**, **Remaining today (gap)**, **Recent pace** (trailing-M-working-day, per §5b), **Required pace** (per §5b), and **Pace ratio bucket** (`on pace` / `watch` / `intervene`). Every tile has a subtitle giving the reference window (e.g. "as of 21 Sep 21:40", "trailing 5 wd", "last done Thu 17"). All values are live, not end-of-last-completed-day.
3. **Sprint calendar strip** — one visible cell per calendar day from sprint start to end. Weekends greyed. Public holidays flagged with location and emoji. Today highlighted. Each cell shows date and per-day team capacity where applicable (e.g. `4/6` on a holiday for one location).
4. **Burn-up chart** (primary, per §5b) with the two required overlays (projection lines + pace ratio referenced from the at-a-glance tile).
5. **Burn-down chart** (secondary, per §5a) with the frozen ideal and the rolling-scope expectation line overlaid.
6. **Event ledger** — every scope-add / removal / completion / reopening in chronological order, with columns: timestamp (AEST or configured tz), event description, delta, running scope, running completed.
7. **Ticket table** — all in-scope tickets. Columns: linked key (using `<Jira host>/browse/{key}`), current status pill (colour by status category), epic (linked), summary, assignee, estimate if relevant, membership interval, flags (`carryover` / `added after t0` / `removed/rejoined` / `done in sprint` / `inferred join` / `partial history`).
8. **Methods and exclusions** — data source (MCP tools used), JQL used for epics and ticket membership, sanity-check outcome (cross-check with an inverted-order or name-based JQL, per §2), approximations and their scope, and excluded epics with the literal-prefix rationale.

Do not include a "current Done inventory" figure without distinguishing it from completions-while-in-scope-this-sprint (a pre-sprint-Done ticket that joined mid-sprint is not this sprint's delivery). Distinguish current Done inventory from in-sprint completion events.

Both charts must show visible gaps for unknown observations, no future actual zeroes, and no smoothed invented values.

### Output

Always write a **self-contained standalone HTML file** to `output/burndown-<safe-prefix>-sprint<sprintId>-<YYYY-MM-DD>.html`.

- The `burndown-` filename prefix is retained for scheduled-runner compatibility (the runner globs for `output/burndown-*-<YYYY-MM-DD>.html`); the file itself now leads with the burn-up chart and includes the burn-down as secondary.
- Inline SVG for both charts, inline CSS for styling, **no external assets** — the file must render cleanly in Gmail and Outlook without fetching any resource at open time.
- Use safe filename characters throughout. Link the resulting file's absolute path in the chat reply, and open **that local HTML file** (not Jira) in a browser when running interactively.

The scheduled runner emails the same file via `scripts/send_report_smtp.py` with a team-agnostic subject like `Sprint burndown report — <YYYY-MM-DD>`, reusing the existing SMTP env vars (`SMTP_HOST`, `SMTP_TO`, etc.) so the report lands in the same inbox as the daily dashboard as a second, separately-subjected email.

Include a CSV of the daily series when useful, with timestamps, scope, completed, remaining, ideal, expectation, delta and coverage; leave unknown/future actuals blank. Provide an event CSV when needed to make scope changes auditable. For Slack sharing, offer a PNG export. Do not send messages, publish externally or write to Confluence/SharePoint without authorization.

## Validation before delivery

- Reconcile each observation with the event ledger and reconcile the latest state with retrieved issues at the same cutoff.
- Verify baseline includes selected unfinished carryover, and excludes already-Done and explicitly excluded administrative work.
- Verify a completed/reopened ticket re-enters remaining and a removed/rejoined ticket follows both membership intervals.
- Verify added work never changes B, removals never count as completion, and point changes affect only their effective historical periods.
- **Burn-down checks.** Verify Start=B and the frozen ideal reaches zero at the original target; no future actuals and no post-close activity. Verify the rolling-scope expectation line resets only on scope-add events (not on completions or removals), and that its most recent segment terminates at `(endpoint, 0)`.
- **Burn-up checks.** Verify the total-scope line ends at `current_scope` on the as-of date, the completed line ends at `current_completed`, and the gap equals `remaining_today`. Verify the projection uses the declared trailing-M-day window and no data from before that window. Verify pace-ratio bucket matches the numeric ratio.
- **Sanity-check the ticket count against team scale.** For a team of N engineers ~40% through a two-week sprint, a total ticket count in single digits with zero completions is a strong hint the query missed results. Cross-check by re-running the query with a different JQL shape (e.g. swap `sprint = <id>` for `sprint = "<sprint name>"`, or invert the `AND` order); the two must agree. If they disagree, trust the larger set and disclose the discrepancy.
- **Two-tier changelog coverage.** Confirm every currently-Done ticket has a fetched changelog. Confirm every ticket with multiple sprint ids on the current Sprint field, or `created ≥ t0`, either has a fetched changelog or is flagged "partial history" in the ticket table.
- Inspect the rendered output for readable labels, correct dates, gaps and units. If history is incomplete, qualify results rather than invent values to force reconciliation.
- Keep credentials, tokens and `.env` contents out of generated files.
