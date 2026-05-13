#!/usr/bin/env python3
"""
Build daily_dashboard_report.html from per-dashboard Datadog snapshots,
GitHub PRs, Todoist tasks, and drop-in extras cards.

Dashboards are discovered from `prompts/dashboards/*.md` (skipping `_*.md`
templates). Each `.md` file declares a title + slug + URL; the matching
`output/<slug>_metric_results.json` snapshot is loaded and rendered with
the generic tile renderer (one tile per unique widget, latest value).

Sections are numbered dynamically (Part A, B, C, …) based on what is
actually present:
  - one Part per dashboard `.md` (sorted by filename)
  - one Part per `--extra LABEL:FILE` argument (CLI order)
  - PR Review Queue
  - My Queue (Todoist)
  - Extras cards (from `prompts/extras/*.md`)
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import os
import string
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from dashboards_plugin import (  # noqa: E402
    Dashboard,
    discover_dashboards,
    load_snapshot,
    parse_dashboard,
)
from extras_plugin import render_extras_section  # noqa: E402
from todo_report import format_view_action_html  # noqa: E402


def _load(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _part_letter(idx: int) -> str:
    """0 → A, 1 → B, …, 25 → Z. Beyond that, fall back to AA, AB, …"""
    letters = string.ascii_uppercase
    if idx < len(letters):
        return letters[idx]
    first, second = divmod(idx - len(letters), len(letters))
    return letters[first] + letters[second]


# ── Section renderers ──────────────────────────────────────────────────────


def _render_generic_section(label: str, data: Dict[str, Any]) -> str:
    """Render a generic dashboard section with one tile per unique widget."""
    label_esc = html_mod.escape(label)
    results = data.get("results") or []
    if not results:
        return f'<div class="section-title">{label_esc}</div><p class="muted">No metric data</p>'

    seen: Dict[str, Optional[float]] = {}
    for row in results:
        title = row.get("widget_title", "—")
        if title in seen:
            continue
        series = row.get("series") or []
        val = series[0].get("latest") if series else None
        seen[title] = float(val) if val is not None else None

    tiles: List[str] = []
    for widget_title, val in seen.items():
        val_str = f"{val:.1f}" if val is not None else "—"
        tile_cls = "tile-grey" if val is None else "tile-green"
        tiles.append(
            f'<div class="tile {tile_cls}">'
            f'<div class="label">{html_mod.escape(widget_title)}</div>'
            f'<div class="big-number">{val_str}</div></div>'
        )

    rows: List[str] = []
    for i in range(0, len(tiles), 3):
        rows.append('<div class="tile-row">' + "\n      ".join(tiles[i:i + 3]) + '</div>')

    return (
        f'<div class="section-title">{label_esc}</div>\n    '
        + "\n    ".join(rows)
    )


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="daily_dashboard_report.html", help="Output HTML path")
    ap.add_argument(
        "--dashboards-dir",
        default="prompts/dashboards",
        help="Folder of dashboard *.md files (default: prompts/dashboards)",
    )
    ap.add_argument(
        "--output-dir",
        default="output",
        help="Folder containing <slug>_metric_results.json snapshots (default: output)",
    )
    ap.add_argument("--prs", default="output/github_prs.json")
    ap.add_argument("--todos", default="output/todos.json")
    ap.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="LABEL:FILE",
        help="One-off dashboard snapshot not tied to a *.md file (repeatable). "
        "Example: --extra 'DORA Metrics:output/dora_metric_results.json'",
    )
    ap.add_argument(
        "--extras-dir",
        default="prompts/extras",
        help="Folder of drop-in *.md cards (default: prompts/extras)",
    )
    args = ap.parse_args()

    prs_data = _load(ROOT / args.prs)
    todos = _load(ROOT / args.todos)

    output_dir = ROOT / args.output_dir

    # Discover dashboards and pair each with its snapshot.
    dashboard_records: List[Tuple[Dashboard, Dict[str, Any]]] = []
    for md_path in discover_dashboards(ROOT / args.dashboards_dir):
        dash = parse_dashboard(md_path)
        snap = load_snapshot(dash.slug, output_dir)
        if snap is None:
            print(
                f"Warning: snapshot output/{dash.slug}_metric_results.json not "
                f"found for dashboard '{dash.title}' ({md_path.name}); skipping. "
                f"Run scripts/datadog_dashboard_extract.py --output-slug {dash.slug} "
                f"to populate it.",
                file=sys.stderr,
            )
            continue
        dashboard_records.append((dash, snap))

    # Build numbered section list. Each entry: (label, html_body).
    sections: List[Tuple[str, str]] = []

    def next_label(suffix: str) -> str:
        return f"Part {_part_letter(len(sections))} — {suffix}"

    # 1) Dashboards from *.md
    for dash, snap in dashboard_records:
        label = next_label(dash.title)
        sections.append((label, _render_generic_section(label, snap)))

    # 2) Ad-hoc --extra dashboards (CLI order)
    for spec in args.extra:
        if ":" not in spec:
            print(f"Warning: skipping --extra '{spec}' (expected LABEL:FILE)", file=sys.stderr)
            continue
        extra_label, fpath = spec.split(":", 1)
        try:
            data = _load(ROOT / fpath.strip())
        except FileNotFoundError:
            print(
                f"Warning: skipping --extra '{extra_label}' — file not found: {fpath.strip()}",
                file=sys.stderr,
            )
            continue
        label = next_label(extra_label.strip())
        sections.append((label, _render_generic_section(label, data)))

    # 3) PR Review Queue
    pr_list = prs_data.get("prs") or []
    pr_label = next_label("PR Review Queue")
    sections.append((pr_label, _render_pr_section(pr_label, pr_list)))

    # 4) My Queue (Todoist)
    queue_label = next_label("My Queue")
    sections.append((queue_label, _render_my_queue_section(queue_label, todos)))

    # 5) Extras (.md cards) — only if any files
    extras_label = f"Part {_part_letter(len(sections))} — Extras"
    extras_html = render_extras_section(ROOT / args.extras_dir, label=extras_label)
    if extras_html:
        sections.append((extras_label, extras_html))

    team = os.environ.get("DATADOG_TEAMS", "team-a").split(",")[0].strip()
    today = date.today().isoformat()

    # Header / footer dashboard links
    header_links = "\n      ".join(
        f'<a href="{html_mod.escape(d.url)}">{html_mod.escape(d.title)} ↗</a>'
        for d, _ in dashboard_records
        if d.url
    )
    footer_links = " · ".join(
        f'<a href="{html_mod.escape(d.url)}">{html_mod.escape(d.title)}</a>'
        for d, _ in dashboard_records
        if d.url
    )

    body_sections = "\n\n  ".join(
        f'<div class="section">\n    {body}\n  </div>' for _, body in sections
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
  .extra-card {{
    background: #fff; border: 1px solid #e2e8f0; border-left: 3px solid #4299e1;
    border-radius: 8px; padding: 14px 18px; margin-bottom: 12px;
  }}
  .extra-title {{ font-size: 14px; font-weight: 700; color: #1a1a2e; margin-bottom: 8px; }}
  .extra-body {{ font-size: 13px; color: #2d3748; line-height: 1.6; }}
  .extra-body p {{ margin: 6px 0; }}
  .extra-body h2, .extra-body h3, .extra-body h4 {{ margin: 10px 0 4px; font-size: 13px; color: #2d3748; }}
  .extra-body ul, .extra-body ol {{ margin: 6px 0 6px 20px; }}
  .extra-body li {{ margin: 2px 0; }}
  .extra-body a {{ color: #2b6cb0; text-decoration: none; }}
  .extra-body code {{ background: #edf2f7; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
  .extra-body pre {{ background: #1a202c; color: #e2e8f0; padding: 10px 12px; border-radius: 6px; overflow-x: auto; font-size: 12px; }}
  .extra-body pre code {{ background: transparent; padding: 0; color: inherit; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>Daily Dashboard — {html_mod.escape(team)}</h1>
    <div class="subtitle">{today} (past 7 days)</div>
    <div class="links">
      {header_links}
    </div>
  </div>

  {body_sections}

  <div class="footer">
    {footer_links + '<br>' if footer_links else ''}
    Generated {today} · Past 7 days · Base metric queries only
  </div>
</div>
</body>
</html>"""

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}")


# ── PR + My Queue helpers (extracted from previous inline main) ─────────────


def _repo_short(full: str) -> str:
    return full.split("/")[-1] if "/" in full else full


def _render_pr_section(label: str, pr_list: List[Dict[str, Any]]) -> str:
    if not pr_list:
        return f'<div class="section-title">{html_mod.escape(label)}</div>\n    <div class="banner-green">No PRs awaiting review — inbox clear</div>'
    rows: List[str] = []
    for pr in pr_list:
        age = pr["age_days"]
        cls = "age-red" if age >= 5 else ("age-yellow" if age >= 2 else "")
        age_html = f'<span class="{cls}">{age}d</span>' if cls else f"{age}d"
        draft = ' <span class="draft-tag">(draft)</span>' if pr.get("draft") else ""
        title_esc = html_mod.escape(pr["title"][:200])
        rows.append(
            f'<tr><td>{html_mod.escape(_repo_short(pr["repo"]))}</td>'
            f'<td><a href="{html_mod.escape(pr["url"])}">{title_esc}</a>{draft}</td>'
            f'<td>{html_mod.escape(pr["author"])}</td><td>{age_html}</td></tr>'
        )
    rows_html = "\n        ".join(rows)
    return f"""<div class="section-title">{html_mod.escape(label)} ({len(pr_list)} open)</div>
    <table class="pr-table">
      <thead><tr><th>Repo</th><th>Title</th><th>Author</th><th>Age</th></tr></thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>"""


def _task_rows(task_list: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for t in task_list:
        p = t["priority"]
        prow = "age-red" if p == "high" else ("age-yellow" if p == "medium" else "")
        lines.append(
            f'<tr><td class="{prow}">{html_mod.escape(p)}</td>'
            f'<td>{html_mod.escape(t["title"])}</td><td>{t["age_days"]}d</td>'
            f'<td>{format_view_action_html(t)}</td></tr>'
        )
    return "\n        ".join(lines)


def _render_my_queue_section(label: str, todos: List[Dict[str, Any]]) -> str:
    label_esc = html_mod.escape(label)
    if not todos:
        return (
            f'<div class="section-title">{label_esc}</div>\n    '
            '<div class="banner-green">Queue clear — no open tasks or reading items.</div>'
        )
    work_tasks = [
        t for t in todos
        if t["type"] == "task" and t.get("domain", "work") != "personal"
    ]
    personal_tasks = [t for t in todos if t["type"] == "task" and t.get("domain") == "personal"]
    reads = [t for t in todos if t["type"] == "read"]
    out: List[str] = [f'<div class="section-title">{label_esc}</div>']
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
                f'<span class="{age_cls}">{t["age_days"]}d</span>'
                if age_cls
                else f'{t["age_days"]}d'
            )
            out.append(
                f"<tr><td>{html_mod.escape(t['title'])}</td><td>{link_cell}</td>"
                f"<td>{age_cell}</td><td>{format_view_action_html(t)}</td></tr>"
            )
        out.append("</tbody></table>")
    return "\n    ".join(out)


if __name__ == "__main__":
    main()
