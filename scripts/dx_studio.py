#!/usr/bin/env python3
"""Run read-only SQL against DX Data Studio (studio.queryRuns.*)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.user_data import env_file  # noqa: E402

API_BASE = "https://api.getdx.com"
ALLOWED_PERIODS = frozenset({"3 months", "12 weeks"})
PLACEHOLDER_PERIOD = "__PERIOD__"
PLACEHOLDER_TEAM = "__TEAM_ILIKE__"


def _token() -> str:
    tok = os.environ.get("DX_TOKEN", "").strip()
    if not tok:
        raise SystemExit("DX_TOKEN is not set. Add it to ~/.engineering-pulse-data/.env")
    return tok


def _team_ilike(team: str) -> str:
    team = team.strip()
    if not team:
        raise SystemExit("Team name is empty")
    if any(c in team for c in ("'", ";", "--", "/*")):
        raise SystemExit("Team name contains disallowed characters")
    if "%" in team:
        return team
    return f"%{team}%"


def apply_sql_template(sql: str, *, period: str, team: str) -> str:
    if period not in ALLOWED_PERIODS:
        raise SystemExit(f"Period must be one of: {', '.join(sorted(ALLOWED_PERIODS))}")
    pattern = _team_ilike(team)
    return sql.replace(PLACEHOLDER_PERIOD, period).replace(PLACEHOLDER_TEAM, pattern)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def execute_query(token: str, sql: str, *, poll_timeout: float = 120.0) -> dict:
    resp = requests.post(
        f"{API_BASE}/studio.queryRuns.execute",
        headers=_headers(token),
        json={"sql": sql},
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("ok"):
        raise RuntimeError(body.get("error", body))
    run_id = body["query_run"]["id"]
    deadline = time.monotonic() + poll_timeout
    while time.monotonic() < deadline:
        info = requests.get(
            f"{API_BASE}/studio.queryRuns.info",
            headers=_headers(token),
            params={"id": run_id},
            timeout=30,
        )
        info.raise_for_status()
        qr = info.json().get("query_run", {})
        status = qr.get("status")
        if status == "succeeded":
            results = requests.get(
                f"{API_BASE}/studio.queryRuns.results",
                headers=_headers(token),
                params={"id": run_id},
                timeout=60,
            )
            results.raise_for_status()
            data = results.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("error", data))
            return data["results"]
        if status == "failed":
            err = qr.get("error") or qr
            raise RuntimeError(f"Query failed: {err}")
        time.sleep(float(info.headers.get("Retry-After", 1)))
    raise TimeoutError(f"Query {run_id} did not finish within {poll_timeout}s")


def fetch_team_meta(token: str, team_substring: str) -> dict | None:
    """Best-effort match on teams.list by name (case-insensitive)."""
    resp = requests.get(
        f"{API_BASE}/teams.list",
        headers=_headers(token),
        params={"limit": 100},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        return None
    needle = team_substring.strip().lower()
    for team in data.get("teams") or []:
        name = (team.get("name") or "").lower()
        if needle in name or name in needle:
            return {
                "id": team.get("id"),
                "name": team.get("name"),
                "contributors": team.get("contributors"),
                "reference_id": team.get("reference_id"),
            }
    return None


def rows_to_records(results: dict) -> list[dict]:
    cols = results.get("columns") or []
    rows = results.get("rows") or []
    out: list[dict] = []
    for row in rows:
        out.append(dict(zip(cols, row, strict=False)))
    return out


def pooled_overall_pct(records: list[dict]) -> float | None:
    succ = sum(int(r.get("successful_builds") or 0) for r in records)
    total = sum(int(r.get("total_builds") or 0) for r in records)
    if total == 0:
        return None
    return round(100.0 * succ / total, 2)


def period_label(period: str) -> str:
    if period == "3 months":
        return "Last 3 months"
    if period == "12 weeks":
        return "Last 12 weeks"
    return period


def team_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "team"


def cmd_run(args: argparse.Namespace) -> int:
    load_dotenv(env_file())
    token = _token()
    team = args.team or os.environ.get("DX_BUILD_SUCCESS_TEAM", "Example Team")
    period = args.period or os.environ.get("DX_BUILD_SUCCESS_PERIOD", "3 months")

    sql_path = Path(args.sql_file)
    sql = apply_sql_template(sql_path.read_text(encoding="utf-8"), period=period, team=team)
    results = execute_query(token, sql)
    records = rows_to_records(results)

    meta: dict = {
        "team": team,
        "period": period,
        "period_label": period_label(period),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_pct": pooled_overall_pct(records),
    }

    if args.enrich_team:
        info = fetch_team_meta(token, team)
        if info:
            meta["team_name"] = info.get("name") or team
            meta["contributors"] = info.get("contributors")
            meta["dx_team_id"] = info.get("id")
            if info.get("id"):
                # URL uses numeric segment matching base64 decode of id in some DX links
                meta["dx_report_url"] = (
                    os.environ.get("DX_BUILD_SUCCESS_REPORT_URL")
                    or f"https://app.getdx.com/report/build-success-rate?period=l3m&teams={info['id']}"
                )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "columns": results.get("columns"), "rows": records}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DX Data Studio query runner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="Execute SQL file and write JSON results")
    run_p.add_argument("--sql-file", required=True)
    run_p.add_argument("--out", required=True)
    run_p.add_argument("--team", default=None)
    run_p.add_argument("--period", default=None)
    run_p.add_argument(
        "--enrich-team",
        action="store_true",
        help="Fetch team name, contributors, and DX report URL from teams.list",
    )
    run_p.set_defaults(func=cmd_run)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
