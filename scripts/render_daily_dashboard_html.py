#!/usr/bin/env python3
"""
Build daily_dashboard_report.html from Datadog metric snapshots + GitHub + Todoist.

Expects:
  output/part_a_metric_results.json   — after Catalogue Quality extract + cp
  output/dashboard_metric_results.json — after Owner Metrics extract (overwrites)
  output/github_prs.json
  output/todos.json
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from todo_report import format_view_action_html  # noqa: E402


def _load(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _first_widget_block(results: List[Dict[str, Any]], title: str) -> List[Dict[str, Any]]:
    i = 0
    while i < len(results):
        if results[i].get("widget_title") == title:
            block: List[Dict[str, Any]] = []
            while i < len(results) and results[i].get("widget_title") == title:
                block.append(results[i])
                i += 1
            return block
        i += 1
    return []


def _sum_latest(block: List[Dict[str, Any]], sub: str) -> float:
    for row in block:
        if row.get("subquery") != sub:
            continue
        return float(sum(s.get("latest") or 0 for s in row.get("series") or []))
    return 0.0


def _scalar_latest(block: List[Dict[str, Any]], sub: str = "query1") -> Optional[float]:
    for row in block:
        if row.get("subquery") != sub:
            continue
        series = row.get("series") or []
        if not series:
            return None
        v = series[0].get("latest")
        return float(v) if v is not None else None
    return None


def part_a_metrics(part_a: Dict[str, Any]) -> Tuple[int, int, int, List[str]]:
    """Broad incomplete, no seal (excluding data-object-only), missing capability count, system names."""
    results = part_a.get("results") or []

    broad = int(_scalar_latest(_first_widget_block(results, "Incomplete Apps And Systems")) or 0)

    excl = _first_widget_block(
        results, "Incomplete Apps And Systems (excluding those only missing Data Object)"
    )
    no_seal = int(_scalar_latest(excl) or 0)

    own = _first_widget_block(
        results,
        "Incomplete Apps And Systems (excluding those only missing Data Object) - Owner's Responsibility",
    )
    miss_cap = 0
    systems: List[str] = []
    for row in own:
        if row.get("subquery") != "query1":
            continue
        for s in row.get("series") or []:
            scope = str(s.get("scope", ""))
            if "has-capability:false" in scope:
                miss_cap += 1
            if "has-approved-quality-seal:false" in scope:
                m = re.search(r"system:([^,]+)", scope)
                if m:
                    systems.append(m.group(1))
    seen = set()
    uniq = []
    for n in systems:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return broad, no_seal, miss_cap, uniq[:12]


def part_b_metrics(part_b: Dict[str, Any]) -> Dict[str, Any]:
    results = part_b.get("results") or []
    out: Dict[str, Any] = {}

    tf = _first_widget_block(results, "Tech Fitness Score")
    if tf:
        q2, q1 = _sum_latest(tf, "query2"), _sum_latest(tf, "query1")
        out["tech_fitness_pct"] = (100.0 * q2 / q1) if q1 else None
        out["tech_fitness_sub"] = f"{int(q2)} / {q1:g} target"
    else:
        out["tech_fitness_pct"] = out["tech_fitness_sub"] = None

    cq = _first_widget_block(results, "Catalog Quality")
    if cq:
        appr = _sum_latest(cq, "query2")
        npr = _sum_latest(cq, "query1")
        tot = appr + npr
        out["catalog_pct"] = (100.0 * appr / tot) if tot else None
        out["catalog_sub"] = f"{int(appr)} approved / {int(tot)} total"
    else:
        out["catalog_pct"] = out["catalog_sub"] = None

    osf = _first_widget_block(results, "Overdue Security Findings")
    if osf:
        out["overdue_sec"] = int(_sum_latest(osf, "query1"))
    else:
        out["overdue_sec"] = None

    out["incidents"] = None  # DORA widget — not queried by extract script

    ep = _first_widget_block(results, "Exercised Pipelines")
    if ep:
        ex = _sum_latest(ep, "query1")
        tot = _sum_latest(ep, "query2")
        out["exercised_pct"] = (100.0 * ex / tot) if tot else None
        out["exercised_sub"] = f"{int(ex)} / {int(tot)} pipelines"
    else:
        out["exercised_pct"] = out["exercised_sub"] = None

    sa = _first_widget_block(results, "Systems Assessed")
    if sa:
        comp = _sum_latest(sa, "query2")
        nonc = _sum_latest(sa, "query1")
        out["assessed_pct"] = (100.0 * comp / (comp + nonc)) if (comp + nonc) else None
        out["assessed_sub"] = f"{int(comp)} compliant · {int(nonc)} non-compliant"
    else:
        out["assessed_pct"] = out["assessed_sub"] = None

    return out


def _tile_class_b(key: str, b: Dict[str, Any]) -> str:
    pct = b.get(f"{key}_pct")
    num = b.get("overdue_sec")
    if key == "overdue_sec" or key == "security":
        if num is None:
            return "tile-grey"
        return "tile-green" if num == 0 else "tile-red"
    if key == "incidents":
        return "tile-grey"
    if pct is None:
        return "tile-grey"
    if key == "tech_fitness" or key == "catalog":
        if pct < 50:
            return "tile-red"
        if pct <= 75:
            return "tile-yellow"
        return "tile-green"
    if key == "exercised" or key == "assessed":
        if pct < 50:
            return "tile-red"
        if pct <= 80:
            return "tile-yellow"
        return "tile-green"
    return "tile-grey"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="daily_dashboard_report.html", help="Output HTML path")
    ap.add_argument(
        "--part-a",
        default="output/part_a_metric_results.json",
        help="Catalogue Quality metric snapshot",
    )
    ap.add_argument(
        "--part-b",
        default="output/dashboard_metric_results.json",
        help="Owner metrics snapshot",
    )
    ap.add_argument("--prs", default="output/github_prs.json")
    ap.add_argument("--todos", default="output/todos.json")
    args = ap.parse_args()

    part_a = _load(ROOT / args.part_a)
    part_b = _load(ROOT / args.part_b)
    prs_data = _load(ROOT / args.prs)
    todos = _load(ROOT / args.todos)

    team = os.environ.get("DATADOG_TEAMS", "team-a").split(",")[0].strip()
    today = date.today().isoformat()
    broad, no_seal, miss_cap, systems = part_a_metrics(part_a)
    b = part_b_metrics(part_b)

    def repo_short(full: str) -> str:
        return full.split("/")[-1] if "/" in full else full

    def pr_rows() -> str:
        rows = []
        for pr in prs_data.get("prs") or []:
            age = pr["age_days"]
            cls = "age-red" if age >= 5 else ("age-yellow" if age >= 2 else "")
            age_html = f'<span class="{cls}">{age}d</span>' if cls else f"{age}d"
            draft = ' <span class="draft-tag">(draft)</span>' if pr.get("draft") else ""
            title_esc = html_mod.escape(pr["title"][:200])
            rows.append(
                f'<tr><td>{html_mod.escape(repo_short(pr["repo"]))}</td>'
                f'<td><a href="{html_mod.escape(pr["url"])}">{title_esc}</a>{draft}</td>'
                f'<td>{html_mod.escape(pr["author"])}</td><td>{age_html}</td></tr>'
            )
        return "\n        ".join(rows)

    def _task_rows(task_list: List[Dict[str, Any]]) -> str:
        lines = []
        for t in task_list:
            p = t["priority"]
            prow = "age-red" if p == "high" else ("age-yellow" if p == "medium" else "")
            lines.append(
                f'<tr><td class="{prow}">{html_mod.escape(p)}</td>'
                f'<td>{html_mod.escape(t["title"])}</td><td>{t["age_days"]}d</td>'
                f'<td>{format_view_action_html(t)}</td></tr>'
            )
        return "\n        ".join(lines)

    def part_d() -> str:
        if not todos:
            return '<div class="banner-green" style="margin-top:8px">Queue clear — no open tasks or reading items.</div>'
        work_tasks = [
            t
            for t in todos
            if t["type"] == "task" and t.get("domain", "work") != "personal"
        ]
        personal_tasks = [t for t in todos if t["type"] == "task" and t.get("domain") == "personal"]
        reads = [t for t in todos if t["type"] == "read"]
        out: List[str] = []
        out.append('<div class="section-title" style="margin-top:4px">Part D — My Queue</div>')
        out.append('<div class="subsection-label">Work tasks</div>')
        if not work_tasks:
            out.append('<p class="muted">No open work tasks</p>')
        else:
            out.append(
                '<table class="pr-table"><thead><tr><th>Priority</th><th>Title</th><th>Age</th><th>Actions</th></tr></thead><tbody>'
            )
            out.append(_task_rows(work_tasks))
            out.append("</tbody></table>")
        out.append('<div class="subsection-label" style="margin-top:16px">Personal tasks</div>')
        if not personal_tasks:
            out.append('<p class="muted">No personal tasks</p>')
        else:
            out.append(
                '<table class="pr-table"><thead><tr><th>Priority</th><th>Title</th><th>Age</th><th>Actions</th></tr></thead><tbody>'
            )
            out.append(_task_rows(personal_tasks))
            out.append("</tbody></table>")
        out.append('<div class="subsection-label" style="margin-top:16px">Reading queue</div>')
        if not reads:
            out.append('<p class="muted">Reading queue empty</p>')
        else:
            out.append(
                '<table class="pr-table"><thead><tr><th>Title</th><th>Link</th><th>Age</th><th>Actions</th></tr></thead><tbody>'
            )
            for t in reads:
                url = t.get("url") or ""
                link_cell = (
                    f'<a href="{html_mod.escape(url)}">{html_mod.escape(t["title"])}</a>'
                    if url
                    else "—"
                )
                age_cls = "age-yellow" if t["age_days"] > 7 else ""
                age_cell = (
                    f'<span class="{age_cls}">{t["age_days"]}d</span>' if age_cls else f'{t["age_days"]}d'
                )
                out.append(
                    f"<tr><td>{html_mod.escape(t['title'])}</td><td>{link_cell}</td>"
                    f"<td>{age_cell}</td><td>{format_view_action_html(t)}</td></tr>"
                )
            out.append("</tbody></table>")
        return "\n    ".join(out)

    systems_html = (
        "<ul>"
        + "".join(f"<li>{html_mod.escape(s)}</li>" for s in systems)
        + (
            f'<li><span style="color:#a0aec0">+ more</span></li>'
            if len(systems) >= 12
            else ""
        )
        + "</ul>"
    )

    pr_list = prs_data.get("prs") or []
    part_c = (
        f'<div class="banner-green">No PRs awaiting review — inbox clear</div>'
        if not pr_list
        else f'''<div class="section-title">Part C — PR Review Queue ({len(pr_list)} open)</div>
    <table class="pr-table">
      <thead><tr><th>Repo</th><th>Title</th><th>Author</th><th>Age</th></tr></thead>
      <tbody>
        {pr_rows()}
      </tbody>
    </table>'''
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daily Dashboard — {html_mod.escape(team)} — {today}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f7f7f8; color: #1a1a2e; }}
  .wrapper {{ max-width: 660px; margin: 0 auto; padding: 24px 16px; }}
  .header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #fff; padding: 32px 28px; border-radius: 12px; margin-bottom: 24px;
  }}
  .header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 6px; letter-spacing: -0.3px; }}
  .header .subtitle {{ font-size: 14px; color: #a0aec0; margin-bottom: 14px; }}
  .header .links {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .header .links a {{ font-size: 13px; color: #63b3ed; text-decoration: none; }}
  .section-title {{
    font-size: 15px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.5px; color: #4a5568; margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 2px solid #e2e8f0;
  }}
  .subsection-label {{ font-size: 13px; font-weight: 700; color: #2d3748; margin-bottom: 8px; }}
  .muted {{ color: #a0aec0; font-size: 13px; margin: 8px 0; }}
  .section {{ margin-bottom: 28px; }}
  .tile-row {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }}
  .tile {{
    flex: 1 1 0%; min-width: 28%;
    padding: 12px 14px 10px; border-radius: 10px; text-align: center;
    border-top: 3px solid transparent; border-left: 1px solid; border-right: 1px solid; border-bottom: 1px solid;
  }}
  .tile .label {{ font-size: 11px; font-weight: 600; color: #4a5568; margin-bottom: 4px; }}
  .tile .big-number {{ font-size: 48px; font-weight: 800; line-height: 1.1; }}
  .tile .sublabel {{ font-size: 10px; color: #718096; margin-top: 4px; }}
  .tile-red {{ background: #fff5f5; border-color: #fed7d7 #fed7d7 #fed7d7 #fc8181; }}
  .tile-red .big-number {{ color: #c53030; }}
  .tile-yellow {{ background: #fffff0; border-color: #faf089 #faf089 #faf089 #f6e05e; }}
  .tile-yellow .big-number {{ color: #b7791f; }}
  .tile-orange {{ background: #fffaf0; border-color: #fbd38d #fbd38d #fbd38d #f6ad55; }}
  .tile-orange .big-number {{ color: #c05621; }}
  .tile-green {{ background: #f0fff4; border-color: #9ae6b4 #9ae6b4 #9ae6b4 #68d391; }}
  .tile-green .big-number {{ color: #276749; }}
  .tile-grey {{ background: #f7fafc; border-color: #e2e8f0 #e2e8f0 #e2e8f0 #cbd5e0; }}
  .tile-grey .big-number {{ color: #a0aec0; }}
  .system-list {{
    background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 14px 18px; margin-top: 8px; font-size: 13px; line-height: 1.8;
  }}
  .system-list ul {{ list-style: none; padding-left: 0; }}
  .system-list li::before {{ content: "•"; color: #e53e3e; margin-right: 8px; font-weight: 700; }}
  .banner-green {{
    background: #f0fff4; border: 2px solid #68d391; border-radius: 10px;
    padding: 18px 24px; text-align: center; font-size: 15px; font-weight: 600; color: #276749;
  }}
  table.pr-table {{
    width: 100%; border-collapse: collapse; font-size: 13px;
    background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;
  }}
  table.pr-table th {{
    background: #edf2f7; padding: 10px 12px; text-align: left;
    font-weight: 700; font-size: 12px; text-transform: uppercase;
    letter-spacing: 0.4px; color: #4a5568; border-bottom: 2px solid #e2e8f0;
  }}
  table.pr-table td {{ padding: 10px 12px; border-bottom: 1px solid #edf2f7; vertical-align: top; }}
  table.pr-table tr:last-child td {{ border-bottom: none; }}
  table.pr-table a {{ color: #2b6cb0; text-decoration: none; }}
  .age-red {{ color: #c53030; font-weight: 700; }}
  .age-yellow {{ color: #b7791f; font-weight: 600; }}
  .draft-tag {{ color: #a0aec0; font-style: italic; font-size: 12px; }}
  .footer {{
    margin-top: 32px; padding-top: 16px; border-top: 1px solid #e2e8f0;
    font-size: 12px; color: #a0aec0; text-align: center; line-height: 2;
  }}
  .footer a {{ color: #718096; text-decoration: none; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>Daily Dashboard — {html_mod.escape(team)}</h1>
    <div class="subtitle">{today} (past 2 days)</div>
    <div class="links">
      <a href="https://xxx/dashboard/***REMOVED***">Catalogue Quality ↗</a>
      <a href="https://xxx/dashboard/***REMOVED***/owner-engineering-metrics-beta">Owner Metrics ↗</a>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Part A — Catalogue Quality</div>
    <div class="tile-row">
      <div class="tile tile-red">
        <div class="label">Incomplete Systems</div>
        <div class="big-number">{broad}</div>
        <div class="sublabel">broad (incl. missing data objects)</div>
      </div>
      <div class="tile tile-yellow">
        <div class="label">No Quality Seal</div>
        <div class="big-number">{no_seal}</div>
        <div class="sublabel">excl. data-object-only gaps</div>
      </div>
      <div class="tile tile-orange">
        <div class="label">Missing Capability</div>
        <div class="big-number">{miss_cap}</div>
        <div class="sublabel">has-capability: false (owner breakdown)</div>
      </div>
    </div>
    <div class="system-list">
      <strong>Systems without quality seal (sample):</strong>
      {systems_html}
    </div>
  </div>

  <div class="section">
    <div class="section-title">Part B — Owner Engineering Metrics</div>
    <div class="tile-row">
      <div class="tile {_tile_class_b('tech_fitness', b)}">
        <div class="label">Tech Fitness Score</div>
        <div class="big-number">{_fmt_pct(b['tech_fitness_pct'])}</div>
        <div class="sublabel">{html_mod.escape(b['tech_fitness_sub'] or '—')}</div>
      </div>
      <div class="tile {_tile_class_b('catalog', b)}">
        <div class="label">Catalogue Quality</div>
        <div class="big-number">{_fmt_pct(b['catalog_pct'])}</div>
        <div class="sublabel">{html_mod.escape(b['catalog_sub'] or '—')}</div>
      </div>
      <div class="tile {_tile_class_b('security', b)}">
        <div class="label">Overdue Security</div>
        <div class="big-number">{b['overdue_sec'] if b['overdue_sec'] is not None else '—'}</div>
        <div class="sublabel">all severities</div>
      </div>
    </div>
    <div class="tile-row">
      <div class="tile tile-grey">
        <div class="label">Incidents / Deploy</div>
        <div class="big-number">—</div>
        <div class="sublabel">non-metric widget</div>
      </div>
      <div class="tile {_tile_class_b('exercised', b)}">
        <div class="label">Exercised Pipeline</div>
        <div class="big-number">{_fmt_pct(b['exercised_pct'])}</div>
        <div class="sublabel">{html_mod.escape(b['exercised_sub'] or '—')}</div>
      </div>
      <div class="tile {_tile_class_b('assessed', b)}">
        <div class="label">Systems Assessed</div>
        <div class="big-number">{_fmt_pct(b['assessed_pct'])}</div>
        <div class="sublabel">{html_mod.escape(b['assessed_sub'] or '—')}</div>
      </div>
    </div>
  </div>

  <div class="section">
    {part_c}
  </div>

  <div class="section">
    {part_d()}
  </div>

  <div class="footer">
    <a href="https://xxx/dashboard/***REMOVED***">Catalogue Quality</a> ·
    <a href="https://xxx/dashboard/***REMOVED***/owner-engineering-metrics-beta">Owner Metrics</a><br>
    Generated {today} · Past 2 days · Base metric queries only
  </div>
</div>
</body>
</html>"""

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
