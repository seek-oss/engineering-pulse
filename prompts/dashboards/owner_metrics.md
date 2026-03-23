# Part B — Owner Metrics

- **URL:** `https://xxx/dashboard/***REMOVED***/owner-engineering-metrics-beta?fromUser=false&refresh_mode=paused&tpl_var_team%5B0%5D=team-a&from_ts=1756648800000&to_ts=1759240799999&live=false`
- **Slug:** `owner_metrics`
- **Focus:** `Tech Fitness,Catalogue,Security Findings,Incidents per deployment,Exercised pipeline,System assessed`

```bash
python3 scripts/datadog_dashboard_extract.py \
  --url 'https://xxx/dashboard/***REMOVED***/owner-engineering-metrics-beta?fromUser=false&refresh_mode=paused&tpl_var_team%5B0%5D=team-a&from_ts=1756648800000&to_ts=1759240799999&live=false' \
  --output-slug owner_metrics \
  --days 2 \
  --focus "Tech Fitness,Catalogue,Security Findings,Incidents per deployment,Exercised pipeline,System assessed"
```

**Metrics to extract — find and read the latest value for each:**

| Metric | Widget title contains |
|--------|-----------------------|
| Tech Fitness Score | `Tech Fitness` |
| Catalogue Quality | `Catalogue` |
| Overdue Security Findings | `Security Findings` |
| Incidents per deployment | `Incidents per deployment` |
| Exercised pipeline | `Exercised pipeline` |
| System assessed | `System assessed` |

For each, read the latest point from the returned series.

**Colouring rules:**

| Metric | RED | YELLOW | GREEN |
|--------|-----|--------|-------|
| Tech Fitness Score | < 50% | 50–75% | > 75% |
| Catalogue Quality | < 50% | 50–75% | > 75% |
| Overdue Security Findings | > 0 | — | 0 |
| Incidents per deployment | > 1 | 0.5–1 | ≤ 0.5 |
| Exercised pipeline | < 50% | 50–80% | > 80% |
| System assessed | < 50% | 50–80% | > 80% |

If a widget returned no series / null, show `—` in a grey tile and note it.
