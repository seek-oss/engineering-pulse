#!/usr/bin/env python3
"""Fetch DX build-success data for dashboard parts (Type: dx-build-success).

Writes ``output/<slug>_dx_build_success.json`` for each matching dashboard ``.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from dashboards_plugin import (  # noqa: E402
    KIND_DX_BUILD_SUCCESS,
    discover_dashboards,
    parse_dashboard,
)
from dx_studio import (  # noqa: E402
    apply_sql_template,
    execute_query,
    fetch_team_meta,
    period_label,
    pooled_overall_pct,
    rows_to_records,
)
from user_data import dashboards_dir, env_file  # noqa: E402

DEFAULT_SQL = ROOT / "skills" / "dx-build-success" / "references" / "build-success-rate.sql"


def _resolve_team_period(dash) -> tuple[str, str]:
    team = (dash.team or os.environ.get("DX_BUILD_SUCCESS_TEAM") or "Example Team").strip()
    period = (dash.period or os.environ.get("DX_BUILD_SUCCESS_PERIOD") or "3 months").strip()
    return team, period


def extract_dashboard(dash, *, token: str, sql_path: Path, output_dir: Path) -> Path:
    team, period = _resolve_team_period(dash)
    sql = apply_sql_template(sql_path.read_text(encoding="utf-8"), period=period, team=team)
    results = execute_query(token, sql)
    records = rows_to_records(results)
    meta: dict = {
        "team": team,
        "period": period,
        "period_label": period_label(period),
        "overall_pct": pooled_overall_pct(records),
    }
    info = fetch_team_meta(token, team)
    if info:
        meta["team_name"] = info.get("name") or team
        meta["contributors"] = info.get("contributors")
        meta["dx_team_id"] = info.get("id")
        if info.get("id"):
            meta["dx_report_url"] = (
                os.environ.get("DX_BUILD_SUCCESS_REPORT_URL")
                or f"https://app.getdx.com/report/build-success-rate?period=l3m&teams={info['id']}"
            )
    out_path = output_dir / f"{dash.slug}_dx_build_success.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "columns": results.get("columns"), "rows": records}
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract DX build success snapshots for pulse")
    parser.add_argument("--slug", default=None, help="Only this dashboard slug (default: all DX parts)")
    parser.add_argument(
        "--dashboards-dir",
        default=str(dashboards_dir()),
        help="Dashboard definitions directory",
    )
    parser.add_argument("--output-dir", default=str(ROOT / "output"))
    parser.add_argument("--sql-file", default=str(DEFAULT_SQL))
    args = parser.parse_args()

    load_dotenv(env_file())
    token = os.environ.get("DX_TOKEN", "").strip()
    if not token:
        print("DX_TOKEN is not set.", file=sys.stderr)
        return 1

    dashboards_path = Path(args.dashboards_dir)
    output_dir = Path(args.output_dir)
    sql_path = Path(args.sql_file)
    if not sql_path.is_file():
        print(f"SQL file not found: {sql_path}", file=sys.stderr)
        return 1

    ran = 0
    for md_path in discover_dashboards(dashboards_path):
        dash = parse_dashboard(md_path)
        if dash.kind != KIND_DX_BUILD_SUCCESS:
            continue
        if args.slug and dash.slug != args.slug:
            continue
        out = extract_dashboard(dash, token=token, sql_path=sql_path, output_dir=output_dir)
        try:
            rel = out.relative_to(ROOT)
        except ValueError:
            rel = out
        print(f"Wrote {rel}")
        ran += 1

    if ran == 0:
        if args.slug:
            print(f"No dx-build-success dashboard with slug {args.slug!r}.", file=sys.stderr)
            return 1
        print("No dx-build-success dashboards found; nothing to do.", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
