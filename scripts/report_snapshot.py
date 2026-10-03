#!/usr/bin/env python3
"""Extract a small structured snapshot from a rendered report, for comparing reports.

Sprint report::

  {"totals": {"scope": 26, "completed": 12, "remaining": 14, "baseline": 3},
   "tickets": {"SEA-1": {"status": "Done", "summary": "...", "assignee": "...", "epic": "SEA-9"}}}

Engineering Pulse report::

  {"metrics": {"Catalogue Quality / Tech Fitness": {"value": "44%", "band": "red"}},
   "prs": {"<url>": {"repo": "...", "title": "...", "author": "...", "age": "3d"}},
   "stakeholders": {"Jane Doe": {"bullets": ["..."], "links": {"<url>": "<text>"}}}}

Usage:
  python scripts/report_snapshot.py --type sprint output/sprint-report-....html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "col", "area", "base", "wbr", "source"}
_PART_PREFIX_RE = re.compile(r"^Part [A-Z]+ — ")
_COUNT_SUFFIX_RE = re.compile(r"\s*\(\d+ open\)$")
_SVG_ATTR_RE = r'{}="(-?\d+(?:\.\d+)?)"'
_SPRINT_TOTALS = {
    "scope": "data-current-scope",
    "completed": "data-current-completed",
    "remaining": "data-remaining",
    "baseline": "data-baseline",
}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str], parent: Node | None):
        self.tag = tag
        self.attrs = attrs
        self.children: list[Node | str] = []
        self.parent = parent

    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            parts.append(child if isinstance(child, str) else child.text())
        return " ".join("".join(parts).split())

    def iter(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.iter()

    def find_all(self, tag: str | None = None, cls: str | None = None) -> list[Node]:
        return [
            n
            for n in self.iter()
            if (tag is None or n.tag == tag) and (cls is None or cls in n.classes())
        ]

    def find(self, tag: str | None = None, cls: str | None = None) -> Node | None:
        found = self.find_all(tag, cls)
        return found[0] if found else None


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: v or "" for k, v in attrs}, self.current)
        self.current.children.append(node)
        if tag not in VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def _section_name(text: str) -> str:
    return _COUNT_SUFFIX_RE.sub("", _PART_PREFIX_RE.sub("", text)).strip()


def _sections(root: Node) -> list[tuple[str, list[Node]]]:
    """Split the page into (section title, sibling nodes after the title) pairs."""
    out: list[tuple[str, list[Node]]] = []
    for title in root.find_all(cls="section-title"):
        parent = title.parent
        siblings = [c for c in parent.children if isinstance(c, Node)]
        start = siblings.index(title) + 1
        body: list[Node] = []
        for node in siblings[start:]:
            if "section-title" in node.classes():
                break
            body.append(node)
        out.append((_section_name(title.text()), body))
    return out


def _within(nodes: list[Node], tag: str | None = None, cls: str | None = None) -> list[Node]:
    found: list[Node] = []
    for node in nodes:
        if (tag is None or node.tag == tag) and (cls is None or cls in node.classes()):
            found.append(node)
        found.extend(node.find_all(tag, cls))
    return found


def _band(tile: Node) -> str:
    for cls in tile.classes():
        if cls.startswith("tile-"):
            return cls.removeprefix("tile-")
    return ""


def pulse_snapshot(html: str) -> dict:
    root = parse(html)
    metrics: dict[str, dict] = {}
    prs: dict[str, dict] = {}
    stakeholders: dict[str, dict] = {}
    for name, body in _sections(root):
        for tile in _within(body, cls="tile"):
            label, number = tile.find(cls="label"), tile.find(cls="big-number")
            if label and number:
                metrics[f"{name} / {label.text()}"] = {"value": number.text(), "band": _band(tile)}
        if name.startswith("PR Review Queue"):
            for row in _within(body, tag="tr"):
                cells = row.find_all("td")
                link = row.find("a")
                if len(cells) >= 4 and link is not None:
                    url = link.attrs.get("href", "")
                    prs[url] = {
                        "repo": cells[0].text(),
                        "title": link.text(),
                        "author": cells[2].text(),
                        "age": cells[3].text(),
                    }
        if name.startswith("Stakeholder Pulse"):
            for card in _within(body, cls="extra-card"):
                title = card.find(cls="extra-title")
                if title is None:
                    continue
                links = {
                    a.attrs["href"]: a.text() for a in card.find_all("a") if a.attrs.get("href")
                }
                stakeholders[title.text()] = {
                    "bullets": [li.text() for li in card.find_all("li")],
                    "links": links,
                }
    return {"metrics": metrics, "prs": prs, "stakeholders": stakeholders}


def sprint_snapshot(html: str) -> dict:
    totals = {}
    for key, attr in _SPRINT_TOTALS.items():
        m = re.search(_SVG_ATTR_RE.format(attr), html)
        if m:
            value = float(m.group(1))
            totals[key] = int(value) if value.is_integer() else value
    tickets: dict[str, dict] = {}
    root = parse(html)
    section = next((n for n in root.iter() if n.attrs.get("id") == "ticket-table"), None)
    if section is not None:
        headers = [th.text().lower() for th in section.find_all("th")]
        for row in section.find_all("tr"):
            cells = [td.text() for td in row.find_all("td")]
            if not cells or len(cells) != len(headers):
                continue
            data = dict(zip(headers, cells, strict=True))
            key = data.get("key")
            if key:
                tickets[key] = {
                    "status": data.get("status", ""),
                    "summary": data.get("summary", ""),
                    "assignee": data.get("assignee", ""),
                    "epic": data.get("epic", ""),
                }
    return {"totals": totals, "tickets": tickets}


EXTRACTORS = {"pulse": pulse_snapshot, "sprint": sprint_snapshot}


def extract(html: str, report_type: str) -> dict | None:
    """Return the snapshot for ``report_type``, or None when nothing useful was found."""
    extractor = EXTRACTORS.get(report_type)
    if extractor is None:
        return None
    try:
        snap = extractor(html)
    except Exception:
        return None
    return snap if any(snap.values()) else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print a report's structured snapshot as JSON")
    ap.add_argument("--type", required=True, choices=sorted(EXTRACTORS))
    ap.add_argument("report", type=Path)
    args = ap.parse_args(argv)
    snap = extract(args.report.read_text(encoding="utf-8"), args.type)
    print(json.dumps(snap, indent=2, ensure_ascii=False))
    return 0 if snap else 1


if __name__ == "__main__":
    sys.exit(main())
