#!/usr/bin/env python3
"""Render DX-style Build success rate HTML from dx_studio JSON output."""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

DEFINITION = (
    "Build success rate is the number of successful builds divided by total builds. "
    "Use this metric to assess the reliability of your build process and ensure "
    "consistent build quality."
)

CHART_W = 720
CHART_W_EMBED = 604
CHART_H = 280
PAD_L = 48
PAD_R = 16
PAD_T = 36
PAD_B = 40


def _parse_week_start(raw: str) -> datetime:
    raw = raw.strip().replace(" ", "T")
    if raw.endswith("+00"):
        raw = raw + ":00"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.strptime(raw[:10], "%Y-%m-%d")


def _week_range_label(week_start: datetime, *, today: datetime | None = None) -> str:
    today = today or datetime.now()
    end = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    week_end = end + timedelta(days=6)
    if week_start.date() <= today.date() <= week_end.date():
        week_end = today
    fmt = "%b %-d" if sys.platform != "win32" else "%b %d"
    try:
        return f"{week_start.strftime(fmt)} – {week_end.strftime(fmt)}"
    except ValueError:
        return week_start.strftime("%Y-%m-%d")


def _load_weeks(payload: dict) -> list[dict]:
    rows = payload.get("rows") or []
    weeks: list[dict] = []
    for r in rows:
        if isinstance(r, dict):
            rec = r
        else:
            continue
        ws = rec.get("week_start")
        if ws is None:
            continue
        dt = _parse_week_start(str(ws))
        total = int(rec.get("total_builds") or 0)
        succ = int(rec.get("successful_builds") or 0)
        rate_raw = rec.get("success_rate_pct")
        rate = float(rate_raw) if rate_raw is not None and total > 0 else None
        weeks.append(
            {
                "week_start": dt,
                "successful_builds": succ,
                "total_builds": total,
                "success_rate_pct": rate,
            }
        )
    weeks.sort(key=lambda w: w["week_start"])
    return weeks


def _linear_trend(values: list[float | None]) -> list[float | None]:
    pts = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(pts) < 2:
        return values
    n = len(pts)
    sx = sum(i for i, _ in pts)
    sy = sum(v for _, v in pts)
    sxx = sum(i * i for i, _ in pts)
    sxy = sum(i * v for i, v in pts)
    denom = n * sxx - sx * sx
    if denom == 0:
        return values
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return [slope * i + intercept if values[i] is not None else None for i in range(len(values))]


def _chart_svg(weeks: list[dict], overall: float | None, *, chart_w: int = CHART_W) -> str:
    rates = [w["success_rate_pct"] for w in weeks]
    plot_w = chart_w - PAD_L - PAD_R
    plot_h = CHART_H - PAD_T - PAD_B
    n = max(len(weeks), 1)

    def x_at(i: int) -> float:
        if n == 1:
            return PAD_L + plot_w / 2
        return PAD_L + (i / (n - 1)) * plot_w

    def y_at(pct: float) -> float:
        return PAD_T + plot_h * (1 - pct / 100.0)

    grid_lines = []
    for pct in (0, 25, 50, 75, 100):
        y = y_at(pct)
        grid_lines.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{chart_w - PAD_R}" y2="{y:.1f}" '
            f'stroke="#e8e8ef" stroke-width="1"/>'
        )
        grid_lines.append(
            f'<text x="{PAD_L - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#666">{pct}%</text>'
        )

    month_labels: dict[str, float] = {}
    for i, w in enumerate(weeks):
        key = w["week_start"].strftime("%b %Y")
        if key not in month_labels:
            month_labels[key] = x_at(i)
    x_labels = "".join(
        f'<text x="{x:.1f}" y="{CHART_H - 8}" text-anchor="middle" '
        f'font-size="11" fill="#666">{html.escape(m)}</text>'
        for m, x in month_labels.items()
    )

    valid_pts = [
        (i, w["success_rate_pct"]) for i, w in enumerate(weeks) if w["success_rate_pct"] is not None
    ]
    area_path = ""
    line_path = ""
    if valid_pts:
        first_i, _ = valid_pts[0]
        last_i, _ = valid_pts[-1]
        baseline = y_at(0)
        parts = [f"M {x_at(first_i):.1f} {baseline:.1f}"]
        for i, rate in valid_pts:
            parts.append(f"L {x_at(i):.1f} {y_at(rate):.1f}")
        parts.append(f"L {x_at(last_i):.1f} {baseline:.1f} Z")
        area_path = f'<path d="{" ".join(parts)}" fill="url(#areaGrad)"/>'

        line_parts = [f"M {x_at(valid_pts[0][0]):.1f} {y_at(valid_pts[0][1]):.1f}"]
        for i, rate in valid_pts[1:]:
            line_parts.append(f"L {x_at(i):.1f} {y_at(rate):.1f}")
        line_path = (
            f'<path d="{" ".join(line_parts)}" fill="none" stroke="#6B4EE6" '
            f'stroke-width="2.5" stroke-linejoin="round"/>'
        )

    trend = _linear_trend(rates)
    trend_line = ""
    trend_pts = [(i, t) for i, t in enumerate(trend) if t is not None]
    if len(trend_pts) >= 2:
        t0 = trend_pts[0]
        t1 = trend_pts[-1]
        trend_line = (
            f'<line x1="{x_at(t0[0]):.1f}" y1="{y_at(t0[1]):.1f}" '
            f'x2="{x_at(t1[0]):.1f}" y2="{y_at(t1[1]):.1f}" '
            f'stroke="#9B8FD9" stroke-width="1.5" stroke-dasharray="6 4"/>'
        )

    dots = []
    for i, w in enumerate(weeks):
        rate = w["success_rate_pct"]
        if rate is None:
            continue
        cx, cy = x_at(i), y_at(rate)
        label = _week_range_label(w["week_start"])
        dots.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="#6B4EE6">'
            f"<title>{html.escape(label)}: {rate:.2f}%</title></circle>"
        )

    kpi = f"{overall:.2f} %" if overall is not None else "—"
    kpi_block = (
        f'<text x="{PAD_L}" y="{PAD_T - 8}" font-size="28" font-weight="700" '
        f'fill="#1a1a1a">{html.escape(kpi)}</text>'
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {chart_w} {CHART_H}" role="img" aria-label="Build success rate weekly chart">
  <defs>
    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#6B4EE6" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#6B4EE6" stop-opacity="0.05"/>
    </linearGradient>
  </defs>
  {"".join(grid_lines)}
  {area_path}
  {trend_line}
  {line_path}
  {"".join(dots)}
  {x_labels}
  {kpi_block}
</svg>"""


def _sparkline_svg(rates: list[float | None], width: int = 120, height: int = 32) -> str:
    vals = [v for v in rates if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = hi - lo or 1.0
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = 2 + (i / (n - 1)) * (width - 4)
        y = height - 2 - ((v - lo) / span) * (height - 4)
        pts.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'aria-hidden="true"><polyline points="{" ".join(pts)}" fill="none" '
        f'stroke="#6B4EE6" stroke-width="1.5"/></svg>'
    )


def _overall_from_payload(payload: dict, weeks: list[dict]) -> float | None:
    meta = payload.get("meta") or {}
    overall = meta.get("overall_pct")
    if overall is None and weeks:
        succ = sum(w["successful_builds"] for w in weeks)
        total = sum(w["total_builds"] for w in weeks)
        if total:
            overall = round(100.0 * succ / total, 2)
    return overall


def render_body(payload: dict, *, embed: bool = False) -> str:
    """Chart + table markup (no document wrapper). ``embed=True`` fits the pulse report width."""
    meta = payload.get("meta") or {}
    weeks = _load_weeks(payload)
    overall = _overall_from_payload(payload, weeks)

    team_display = meta.get("team_name") or meta.get("team") or "Team"
    period_label = meta.get("period_label") or meta.get("period") or ""
    contributors = meta.get("contributors")
    dx_url = meta.get("dx_report_url") or ""

    chart_w = CHART_W_EMBED if embed else CHART_W
    chart = _chart_svg(weeks, overall, chart_w=chart_w)
    rates = [w["success_rate_pct"] for w in weeks]
    spark = _sparkline_svg(rates)

    recent = list(reversed([w for w in weeks if w["total_builds"] > 0][-3:]))

    week_headers = "".join(
        f"<th>{html.escape(_week_range_label(w['week_start']))}</th>" for w in recent
    )
    week_cells = "".join(
        f"<td>{w['success_rate_pct']:.2f}%</td>"
        if w["success_rate_pct"] is not None
        else "<td>—</td>"
        for w in recent
    )
    for _ in range(3 - len(recent)):
        week_headers += "<th></th>"
        week_cells += "<td></td>"

    contrib_cell = str(contributors) if contributors is not None else "—"
    overall_cell = f"{overall:.2f}%" if overall is not None else "—"
    dx_link = (
        f'<p class="dx-bs-footer"><a href="{html.escape(dx_url)}">Open in DX</a></p>' if dx_url else ""
    )

    root = "dx-build-success-embed" if embed else "dx-build-success"
    title = "" if embed else "<h1>Build success rate</h1>"
    return f"""<div class="{root}">
  {title}
  <p class="dx-bs-def">{html.escape(DEFINITION)}</p>
  <div class="dx-bs-chips">
    <span class="dx-bs-chip">{html.escape(period_label)}</span>
    <span class="dx-bs-chip">Team: {html.escape(team_display)}</span>
  </div>
  <div class="dx-bs-chart-wrap">{chart}</div>
  <p class="dx-bs-legend">Trendlines</p>
  <div class="dx-bs-table-card">
  <table class="dx-bs-table">
    <thead>
      <tr>
        <th>Team</th>
        <th>Contributors</th>
        <th>Overall average</th>
        <th>Trend</th>
        {week_headers}
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>{html.escape(team_display)}</td>
        <td>{html.escape(contrib_cell)}</td>
        <td>{html.escape(overall_cell)}</td>
        <td>{spark}</td>
        {week_cells}
      </tr>
    </tbody>
  </table>
  {dx_link}
  </div>
</div>"""


PAGE_STYLE = """
  body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 24px; color: #1a1a1a; background: #fafafa; }
  .dx-build-success { max-width: 960px; margin: 0 auto; }
  .dx-build-success h1 { font-size: 1.5rem; margin: 0 0 8px; }
"""

SHARED_STYLE = """
  .dx-bs-def { color: #555; font-size: 0.95rem; line-height: 1.45; margin-bottom: 16px; }
  .dx-bs-chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
  .dx-bs-chip { background: #f0eef8; color: #4a3d8f; padding: 4px 10px; border-radius: 999px; font-size: 0.85rem; }
  .dx-bs-chart-wrap svg { width: 100%; height: auto; display: block; }
  .dx-bs-legend { font-size: 0.8rem; color: #666; text-align: right; margin-top: 4px; }
  .dx-bs-table-card { background: #fff; border-radius: 12px; padding: 16px; margin-top: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .dx-bs-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .dx-bs-table th, .dx-bs-table td { text-align: left; padding: 8px 6px; border-bottom: 1px solid #eee; }
  .dx-bs-table th { color: #666; font-weight: 600; }
  .dx-bs-footer { margin-top: 12px; font-size: 0.85rem; }
  .dx-bs-footer a, .dx-build-success a { color: #6B4EE6; }
"""

EMBED_EXTRA_STYLE = """
  .dx-build-success-embed .dx-bs-table-card { box-shadow: none; border: 1px solid #e2e8f0; padding: 12px; }
  .dx-build-success-embed .dx-bs-def { font-size: 0.85rem; }
"""


def render_pulse_section(label: str, payload: dict) -> str:
    """One Engineering Pulse Part: section title + embedded DX build-success chart."""
    label_esc = html.escape(label)
    body = render_body(payload, embed=True)
    style = f"<style>{SHARED_STYLE}{EMBED_EXTRA_STYLE}</style>"
    return f'{style}\n<div class="section-title">{label_esc}</div>\n{body}'


def render_html(payload: dict) -> str:
    team_display = (payload.get("meta") or {}).get("team_name") or (payload.get("meta") or {}).get(
        "team"
    ) or "Team"
    inner = render_body(payload, embed=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Build success rate — {html.escape(team_display)}</title>
<style>
{PAGE_STYLE}
{SHARED_STYLE}
  .dx-build-success .dx-bs-chart-wrap,
  .dx-build-success .dx-bs-table-card {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
</style>
</head>
<body>
{inner}
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="JSON from dx_studio.py")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.data).read_text(encoding="utf-8"))
    html_out = render_html(payload)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
