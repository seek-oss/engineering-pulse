# DX Web API (Data Studio)

Engineering Pulse uses the [DX Web API](https://docs.getdx.com/webapi/overview/) for read-only Data Studio queries.

## Authentication

```http
Authorization: Bearer <DX_TOKEN>
```

Create a **Personal access token** in DX (Settings → Personal access tokens) with scope **`datacloud:query`**. Store it as `DX_TOKEN` in `~/.engineering-pulse-data/.env`.

## Run a query

1. `POST https://api.getdx.com/studio.queryRuns.execute`  
   Body: `{"sql": "<single SELECT>"}`  
   Returns `query_run.id` with status `queued`.

2. Poll `GET https://api.getdx.com/studio.queryRuns.info?id=<id>` until `status` is `succeeded` or `failed`.

3. `GET https://api.getdx.com/studio.queryRuns.results?id=<id>`  
   JSON: `{ "results": { "columns": [...], "rows": [[...], ...] } }`.

Use `python3 scripts/dx_studio.py run` instead of calling curl by hand.

## Team metadata (optional)

`GET https://api.getdx.com/teams.list` returns DX teams (`name`, `id`, `contributors`, `reference_id`). The build-success renderer uses this for the breakdown table when `--enrich-team` is passed.

## Rate limits

1000 requests/minute per account; on `429`, back off and retry.
