# Part A — Catalogue Quality

- **URL:** `https://xxx/dashboard/***REMOVED***?fromUser=false&offset=1&refresh_mode=monthly&tpl_var_criticality%5B0%5D=%2A&tpl_var_team%5B0%5D=team-a&from_ts=1771143508740&to_ts=1773562708739&live=true`
- **Slug:** `catalogue_quality`
- **Focus:** (none)

```bash
python3 scripts/datadog_dashboard_extract.py \
  --url 'https://xxx/dashboard/***REMOVED***?fromUser=false&offset=1&refresh_mode=monthly&tpl_var_criticality%5B0%5D=%2A&tpl_var_team%5B0%5D=team-a&from_ts=1771143508740&to_ts=1773562708739&live=true' \
  --output-slug catalogue_quality \
  --days 2
```

**Metrics to extract:**

| Metric | Widget title contains |
|--------|-----------------------|
| Incomplete systems (broad) | `Incomplete Apps And Systems` (the broad one with `has-data-objects`) |
| Systems without quality seal | `Incomplete Apps And Systems (excluding` (no `data-objects` filter) |
| Systems missing capability | from the per-system breakdown — count series where `has-capability:false` |

**Report rendering:** 3 big-number tiles in a row:
- Incomplete Systems → RED tile
- No Quality Seal → YELLOW tile
- Missing Capability → ORANGE tile

Below tiles: named list of systems without quality seal.
