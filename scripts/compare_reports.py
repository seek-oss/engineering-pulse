#!/usr/bin/env python3
"""Prepare a two-report comparison for the report-compare agent skill.

Validates two archived report ids and writes a context file the agent reads:
``output/compare/context-<A>-vs-<B>.json`` with both entries, their snapshots,
the absolute paths of the archived HTML, and where to write the comparison.

The ids come from a URL (``engineering-pulse://compare?a=…&b=…``), so they are
checked strictly against the manifest before anything else uses them.

Usage:
  python scripts/compare_reports.py prepare --a pulse-20261002-090012 --b pulse-20261003-090008
  python scripts/compare_reports.py parse-url 'engineering-pulse://compare?a=…&b=…'
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from scripts.report_archive import OUTPUT, TYPE_LABELS, load_manifest, reports_dir

console = Console(stderr=True)
ID_RE = re.compile(r"^[a-z]+-\d{8}-\d{6}(-failed)?(-\d+)?$")
URL_SCHEME = "engineering-pulse"


class CompareError(ValueError):
    pass


def validate(a_id: str, b_id: str, root: Path) -> tuple[dict, dict]:
    """Return the manifest entries for two comparable report ids, or raise CompareError."""
    for rid in (a_id, b_id):
        if not ID_RE.fullmatch(rid or ""):
            raise CompareError(f"not a report id: {rid!r}")
    if a_id == b_id:
        raise CompareError("pick two different reports")
    by_id = {e.get("id"): e for e in load_manifest(root)}
    pair = []
    for rid in (a_id, b_id):
        entry = by_id.get(rid)
        if entry is None:
            raise CompareError(f"report {rid} is not in the archive")
        if entry.get("status") != "ok" or not entry.get("path"):
            raise CompareError(f"report {rid} is a failed run")
        if not (root / entry["path"]).is_file():
            raise CompareError(f"report file for {rid} is missing")
        pair.append(entry)
    a, b = pair
    if a["type"] != b["type"]:
        raise CompareError(f"reports have different types ({a['type']} vs {b['type']})")
    if a["type"] == "compare":
        raise CompareError("cannot compare two comparison reports")
    return a, b


def parse_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme != URL_SCHEME or parsed.netloc != "compare":
        raise CompareError(f"unsupported link: {url!r}")
    query = parse_qs(parsed.query)
    a, b = query.get("a", [""])[0], query.get("b", [""])[0]
    for rid in (a, b):
        if not ID_RE.fullmatch(rid):
            raise CompareError(f"not a report id: {rid!r}")
    return a, b


def output_paths(a_id: str, b_id: str, output: Path = OUTPUT) -> tuple[Path, Path]:
    stem = f"{a_id}-vs-{b_id}"
    return output / "compare" / f"context-{stem}.json", output / f"compare-{stem}.html"


def _entry_view(entry: dict, root: Path) -> dict:
    return {
        "id": entry["id"],
        "date": entry["date"],
        "time": entry["time"],
        "title": entry.get("title", ""),
        "html": str((root / entry["path"]).resolve()),
        "snapshot": entry.get("snapshot"),
    }


def prepare(a_id: str, b_id: str, *, root: Path | None = None, output: Path = OUTPUT) -> Path:
    root = root or reports_dir()
    a, b = validate(a_id, b_id, root)
    if a["timestamp"] > b["timestamp"]:
        a, b = b, a
    context_path, report_path = output_paths(a["id"], b["id"], output)
    context = {
        "type": a["type"],
        "type_label": TYPE_LABELS[a["type"]],
        "older": _entry_view(a, root),
        "newer": _entry_view(b, root),
        "output_html": str(report_path.resolve()),
        "subject": f"{TYPE_LABELS[a['type']]}: {a['date']} {a['time']} vs {b['date']} {b['time']}",
    }
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(json.dumps(context, indent=2, ensure_ascii=False), encoding="utf-8")
    return context_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_prep = sub.add_parser("prepare", help="validate two report ids and write the context file")
    p_prep.add_argument("--a", required=True, help="first report id")
    p_prep.add_argument("--b", required=True, help="second report id")
    p_url = sub.add_parser("parse-url", help="print the two ids from an engineering-pulse:// link")
    p_url.add_argument("url")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "parse-url":
            print(" ".join(parse_url(args.url)))
            return 0
        print(prepare(args.a, args.b))
        return 0
    except CompareError as exc:
        console.print(f"[red]Cannot compare:[/red] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
