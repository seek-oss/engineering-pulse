<!-- SKIP: This is a reference example only. Do NOT execute this file. -->

# Example — DORA Metrics

> **This file is a format reference only.** The agent skips any file in this
> directory whose name starts with `_`.
>
> To add a real dashboard, run **`/add-dashboard`** (**Cursor**) or follow your harness (**Claude Code** / **Pi** — [`harness/`](../../harness/)):
>
> ```
> /add-dashboard add my DORA dashboard at https://app.datadoghq.com/dashboard/xyz-123, I care about deploy rate
> ```

---

- **URL:** `https://app.datadoghq.com/dashboard/abc-xyz-123/my-dashboard?tpl_var_team%5B0%5D=my-team&from_ts=1700000000000&to_ts=1700086400000&live=true`
- **Slug:** `dora`
- **Focus:** `Deployment Frequency,Change Failure Rate,Latency`

```bash
python3 scripts/datadog_dashboard_extract.py \
  --url 'https://app.datadoghq.com/dashboard/abc-xyz-123/my-dashboard?tpl_var_team%5B0%5D=my-team&from_ts=1700000000000&to_ts=1700086400000&live=true' \
  --output-slug dora \
  --days 7 \
  --focus "Deployment Frequency,Change Failure Rate,Latency"
```

**Metrics to extract — find and read the latest value for each:**

| Metric | Widget title contains |
|--------|-----------------------|
| Deploy Rate | `Deployment Frequency` |
| Error Rate | `Change Failure Rate` |
| P99 Latency | `Latency` |

For each, read the latest point from the returned series.

**Colouring rules:**

| Metric | RED | YELLOW | GREEN |
|--------|-----|--------|-------|
| Deploy Rate | < 1/week | 1–5/week | > 5/week |
| Error Rate | > 15% | 5–15% | < 5% |
| P99 Latency | > 500ms | 200–500ms | < 200ms |

If a widget returned no series / null, show `—` in a grey tile and note it.
