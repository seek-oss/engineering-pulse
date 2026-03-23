# Customising for your team

You don't need to touch any scripts. Just fill in the template below and paste it into a Cursor chat — the agent will figure out the rest.

---

## Step 1 — Add your dashboard URLs to `.env`

```bash
DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY=https://app.datadoghq.com/dashboard/your-id/your-slug
DATADOG_DASHBOARD_URL_OWNER_METRICS=https://app.datadoghq.com/dashboard/your-id/your-slug
DATADOG_TEAMS=your-team-slug
```

Copy the URLs straight from your browser's address bar. That's it.

---

## Step 2 — Describe what you care about

Copy this template, fill in your answers, and paste it into Cursor:

```
I want to customise prompts/daily-dashboard.md for my team.

My Datadog dashboards:
- Catalogue / quality dashboard: <paste URL>
- Engineering metrics dashboard: <paste URL>
- My team name(s): <e.g. platform-engineering>

What I care about in Part A (catalogue / system health):
<describe in plain English — e.g. "how many services are missing an owner",
 "how many repos haven't had a deployment in 30 days", anything really>

What I care about in Part B (engineering metrics):
<describe in plain English — e.g. "deployment frequency, MTTR, test coverage,
 open CVEs, tech debt score — whatever your dashboard shows">

My thresholds (optional — skip if you're not sure):
<e.g. "deployment frequency below 1/day is bad, above 5 is good",
 "any open critical CVE is red, otherwise green">

Please update the prompt file and the HTML report colouring rules to match.
```

The agent will inspect your dashboards, find the matching widget titles, and rewrite the prompt for you.

---

## That's it

No scripts to run. No config files to edit by hand. Just describe what matters to you and let the agent do the work.

If something looks wrong in the report, just tell the agent: *"the number for X looks off"* or *"I don't see Y in my dashboard"* and it will fix it.
