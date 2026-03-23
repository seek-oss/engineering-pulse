# Part A — Catalogue Quality

- **URL env:** `DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY`
- **Slug:** `catalogue_quality`
- **Focus:** (none)

```bash
python3 scripts/datadog_dashboard_extract.py \
  --url-env DATADOG_DASHBOARD_URL_CATALOGUE_QUALITY \
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
