# Repo-local Engineering Pulse data (optional)

Use this layout to test `/daily-dashboard` from a **git clone** without touching
`~/.engineering-pulse-data` yet.

```bash
export ENGINEERING_PULSE_DATA_DIR="$PWD/local/pulse-data"
mkdir -p local/pulse-data/dashboards local/pulse-data/extras
cp dev/pulse-data/dashboards/*.md local/pulse-data/dashboards/
```

Secrets stay in the clone root `.env` until you add `local/pulse-data/.env`.

Dashboard filename order sets Part letters (`a_owner_metrics` → Part A, `b_build_success` → Part B).

DX parts: `python3 scripts/dx_build_success_extract.py` before render (or full `/daily-dashboard`).
