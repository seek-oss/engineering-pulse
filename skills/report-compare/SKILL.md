---
name: report-compare
description: "Compare two archived Engineering Pulse or sprint reports from the local report calendar and write a short HTML comparison report: what changed, what is at risk, and what to look at next. Started from the calendar's Compare view (engineering-pulse:// link) or `make compare A=<id> B=<id>`; the runner passes a prepared context file. Use when asked to compare two reports, explain what changed between report runs, or summarise progress over a period."
---

# Report Compare

Write a comparison of two archived reports of the same type. The runner
(`scripts/run_compare.sh`) has already validated the two report ids and written a
context file; its path is given at the end of this prompt as
`Context file for this run: <path>`.

Do not query Datadog, GitHub, Jira, Todoist or Glean. Everything you need is in the
context file and the two archived HTML files. Do not ask questions: this runs headless.

## 1. Read the context

The context file (`output/compare/context-<A>-vs-<B>.json`) contains:

| Key | Meaning |
|-----|---------|
| `type`, `type_label` | `pulse` (Engineering Pulse) or `sprint` (Sprint report) |
| `older`, `newer` | `id`, `date`, `time`, `title`, `html` (absolute path of the archived report) and `snapshot` |
| `output_html` | Where to write the comparison (absolute path) |
| `subject` | Subject line to use when delivering |

`older` is always the earlier report. A `snapshot` is structured data extracted from
the report (see `scripts/report_snapshot.py`). It is `null` for reports in an older
format; then read the facts from the HTML instead.

- **Sprint snapshot:** `totals` (`scope`, `completed`, `remaining`, `baseline`) and
  `tickets` keyed by issue key, each with `status`, `summary`, `assignee`, `epic`.
- **Pulse snapshot:** `metrics` keyed by `"<section> / <tile>"` with `value` (as
  displayed) and `band` (`red`, `yellow`, `green`, `grey`); `prs` keyed by PR URL with
  `repo`, `title`, `author`, `age`; `stakeholders` keyed by name with `bullets` and
  `links` (URL → link text, mostly Slack threads).

Compute the changes from the two snapshots first. Then read the two HTML files only
where you need context the snapshot does not carry (for example a stakeholder's
themes, an epic's progress, or the event ledger in a sprint report). The HTML files
can be large; search them for the sections you need instead of reading them whole.

## 2. Decide what matters

Report facts that come from the two reports only. Do not guess causes that the
reports do not show; if a reason is unclear, say so.

**Sprint reports:**

- Tickets finished (status moved to Done, Closed, Resolved or Released), with assignee.
- Other status changes, for example New → In Progress, or tickets moving backwards.
- Tickets added to or removed from the sprint (scope change), and the net scope change.
- Completed and remaining totals, and whether the burn rate between the two dates is
  enough to finish the remaining work by the sprint end shown in the newer report.
- Tickets with no status change across the whole period when the period is longer
  than a few days (possible blockers).

**Engineering Pulse reports:**

- Health metrics whose band changed (worse first), then the largest value changes.
- New PRs awaiting review and PRs that left the queue; PRs that stayed in the queue
  for the whole period and are getting old.
- New stakeholder messages: links present in the newer card but not the older one,
  with one line on what each thread is about (from the newer card's bullets).

When the two reports are far apart (more than about a week), describe the trend over
the period instead of listing every small change.

## 3. Write the comparison

Write one self-contained HTML file to `output_html`, with inline CSS and no external
assets or scripts. Keep it short: a reader should get the point in under a minute.

- `<title>`: `<type_label> comparison — <older date> → <newer date>`. The calendar
  shows this title.
- **Headline:** two or three sentences on the most important change.
- **What changed:** grouped lists as in step 2, with counts. Link sprint tickets to
  the issue URLs found in the HTML report, and PRs and Slack threads to their URLs.
- **Watch:** at most five items that need attention, each with the evidence.
- **Next steps:** at most three concrete suggestions.
- **Footer:** both report titles with their date and time, and a link back to the
  calendar compare view: `../../../index.html#/compare/<older id>/<newer id>`
  (the comparison is archived three folders below `index.html`).

Use the colour convention of the other reports: red for attention, yellow (amber) for
watch, green for healthy. Use fictional examples only if you need to explain a format;
never invent names or numbers.

## 4. Deliver

Deliver the comparison once:

```bash
python3 scripts/deliver_report.py send --type compare --subject "<subject>" "<output_html>"
```

This archives it to the calendar (grey dot) and sends a notification that opens it.
If you do not deliver, the runner delivers `output_html` itself when the file is new,
or records a failed comparison on the calendar.
