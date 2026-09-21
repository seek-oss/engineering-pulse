---
name: sprint-burndown
description: "Build an evidence-based remaining-vs-ideal sprint burndown from Jira for a team's delivery tickets under epics whose summary starts with a user-supplied prefix. Configured via one free-form SPRINT_BOARD sentence in .env. Use for sprint burndown charts, remaining-work reports, scope-change analysis, or sprint delivery progress."
---

# Sprint Burndown

Generate a daily burndown for one team's delivery tickets on a mixed Jira board. Reconstruct historical work from evidence; distinguish completion from scope changes. Produce a team-scoped custom report.

## Quick start

Set `SPRINT_BOARD` in `.env` — one free-form sentence describing your sprint board. See the template and inline commentary in [`.env.example`](../../.env.example).

When you invoke the skill, the agent loads `SPRINT_BOARD`, parses the board URL for Atlassian host / project / board id, discovers `cloudId` and custom-field ids at runtime, and picks the active sprint. If more than one active sprint is a plausible match, it asks which one.

For one-off runs or overrides, paste the same sentence into the chat instead — chat input takes precedence over `.env`.

Every value the agent resolves is captured in the run's report so subsequent runs are reproducible. The rest of this file is the detailed spec the agent follows; you should not need to edit it to reuse the skill.

## Jira access and metadata

Discover per-instance identifiers at runtime — do not hard-code them into the skill.

- Prefer available Atlassian MCP tools, including `searchJiraIssuesUsingJql` and `getJiraIssue`.
- Host and `cloudId`: parse the host from the board URL in the Quick start template; fetch `cloudId` via Atlassian MCP `getAccessibleAtlassianResources` or `GET https://<host>/_edge/tenant_info`.
- REST search: `POST /rest/api/3/search/jql`.
- Issue: `GET /rest/api/3/issue/{key}`.
- Full issue history: `GET /rest/api/3/issue/{key}/changelog`, following pagination. Do not assume `expand=changelog` includes every entry.
- Sprints: `GET /rest/agile/1.0/board/{id}/sprint?state=active,future,closed`, following pagination.
- Board configuration: `GET /rest/agile/1.0/board/{id}/configuration`; resolve its saved filter, column mappings and estimation settings.
- Custom-field ids: look up via `GET /rest/api/3/field` (Sprint is commonly `customfield_10018`; story points are commonly `customfield_10024` or `customfield_10025`). Verify against the board's estimation config. Choose one point field for the report, not a per-ticket mixture.

Use only capabilities actually available. If permitted by the host environment, an authenticated Jira browser session may provide same-origin REST access; in Cursor this may use an available CDP connection. Do not assume CDP, a browser session or an API token exists. Follow the environment's browser/authentication rules. If access is unavailable or expired, explain the concrete access need. Never bypass access restrictions.

Paginate searches and histories completely, split large JQL, and respect throttling. Request summary, issue type, status/id/category, assignee, parent/epic relationship, labels, sprint, selected point field and creation time. Fetch relevant sprint, status, point, parent and scope-field history. Capture retrieval time and source provenance; avoid inconsistent snapshots if tickets change during retrieval.

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

1. Fetch active sprints once: `GET /rest/agile/1.0/board/{id}/sprint?state=active`, and resolve the target `<sprintId>` from that list.
2. Query tickets with the specific id: `sprint = <sprintId> AND parent in (<freshEpicKeys>) ORDER BY key ASC`. Paginate to `isLast: true`.

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

## 5. Ideal line, timing and interpretation

Freeze the ideal baseline B. Subsequent additions, removals, estimate changes or completions must not reset it.

Define the target endpoint from explicit team dates when provided, otherwise Jira's planned `endDate`. For date-only team windows use the end of the last working day. Disclose the exact endpoint and any difference from Jira. A closed sprint's actual endpoint is its completion timestamp; retain the original ideal target rather than recalculating the ideal to fit early/late closure.

Let N be the number of included working-day intervals between `t0` and the target endpoint. Each included date is one unit; if the first/last date is partial, count its available interval as one unit and disclose this daily-granularity convention.

```text
Start:                  ideal(0) = B
After working day k:    ideal(k) = B * (1 - k / N), k = 1 ... N
Completed-day delta:    actual(k) - ideal(k)
Original average pace:  B / N
```

Plot the explicit Start point plus daily endpoints. Example: B=20, N=10 gives Start=20, end of day 1=18, day 2=16, day 10=0. Reject N=0 as an invalid ideal window; do not divide by zero.

Use the latest completed working-day observation for the headline daily comparison. Optionally show a separate live point labelled “as of [timestamp]”; do not compare a morning live actual against an evening target as if the day had ended. If no working day has finished, report baseline and live remaining without a daily pace verdict.

Calculate required average pace from the same completed-day cutoff: remaining at that cutoff divided by working days left until the target. If none remain, report “target reached” when remaining is zero, or “unfinished at target” otherwise. Do not calculate an infinite/undefined pace. For an active sprint beyond target, extend actual observations through now, keep ideal at zero after the original endpoint, and label overdue work. Do not stretch the ideal.

Use “above,” “at,” or “below the ideal line.” Do not mechanically convert that result into “delivery on track.” Explain original-scope completion, scope added/removed, reopenings, estimate changes and known blockers. Any delivery-confidence assessment is qualitative and must be separated from the arithmetic. Ticket-count pace measures ticket throughput, not equal-sized effort or individual productivity.

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

Fetch data anew for each run; never reuse a previous report as evidence. Produce a readable report with:

- Sprint, board, prefix, team window, baseline timestamp, target, as-of time, timezone, unit and completion rule.
- Coverage label: complete for stated scope, partial, or snapshot only; enumerate missing history and approximations.
- Baseline, current in-scope Done/unfinished counts, carryover, additions, removals and unestimated coverage where applicable. Distinguish current Done inventory from completion events during this sprint.
- Actual versus ideal chart; no future actual zeroes, no smoothed invented values, and visible gaps for unknowns.
- Latest completed-day comparison, required pace and a separate live count if useful.
- Completion versus scope/estimate/reopening breakdown; status mix and remaining by epic.
- Tickets completed while in scope during this sprint, identifying any subsequently reopened or removed. Do not include pre-sprint Done tickets as this sprint's delivery.
- Ticket table: linked key, summary, epic, current status, assignee, estimate if relevant, known membership intervals, carryover/added/removed flags and history limitations. Link keys with the `<Jira host>/browse/{key}` pattern.
- Methods caption and explicit exclusions. List date/filter/mapping differences from Jira's native report.

### Output

Always write a **self-contained standalone HTML file** to `output/burndown-<safe-prefix>-sprint<sprintId>-<YYYY-MM-DD>.html`.

- Inline SVG for the chart, inline CSS for styling, **no external assets** — the file must render cleanly in Gmail and Outlook without fetching any resource at open time.
- Include the sections listed above (calendar strip, headline stats, chart, event ledger, ticket table, methods).
- Use safe filename characters throughout. Link the resulting file's absolute path in the chat reply, and open it in a browser when running interactively.

The scheduled runner emails the same file via `scripts/send_report_smtp.py` with a team-agnostic subject like `Sprint burndown report — <YYYY-MM-DD>`, reusing the existing SMTP env vars (`SMTP_HOST`, `SMTP_TO`, etc.) so the report lands in the same inbox as the daily dashboard as a second, separately-subjected email.

Include a CSV of the daily series when useful, with timestamps, actual, ideal, delta and coverage; leave unknown/future actuals blank. Provide an event CSV when needed to make scope changes auditable. For Slack sharing, offer a PNG export. Do not send messages, publish externally or write to Confluence/SharePoint without authorization.

## Validation before delivery

- Reconcile each observation with the event ledger and reconcile the latest state with retrieved issues at the same cutoff.
- Verify baseline includes selected unfinished carryover, and excludes already-Done and explicitly excluded administrative work.
- Verify a completed/reopened ticket re-enters remaining and a removed/rejoined ticket follows both membership intervals.
- Verify added work never changes B, removals never count as completion, and point changes affect only their effective historical periods.
- Verify Start=B and the ideal reaches zero at the original target; no future actuals and no post-close activity.
- **Sanity-check the ticket count against team scale.** For a team of N engineers ~40% through a two-week sprint, a total ticket count in single digits with zero completions is a strong hint the query missed results. Cross-check by re-running the query with a different JQL shape (e.g. swap `sprint = <id>` for `sprint = "<sprint name>"`, or invert the `AND` order); the two must agree. If they disagree, trust the larger set and disclose the discrepancy.
- Inspect the rendered output for readable labels, correct dates, gaps and units. If history is incomplete, qualify results rather than invent values to force reconciliation.
- Keep credentials, tokens and `.env` contents out of generated files.
