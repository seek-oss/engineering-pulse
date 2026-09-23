"""Turn metric-result rows into the tiles a dashboard markdown asked for.

Query-value widgets on Datadog often display a formula (for example
``query2 / (query2 + query1) * 100``) rather than the first base query.
When a dashboard file sets **Focus**, the report keeps one tile per focus
term and evaluates that formula. Colour bands come from the markdown table.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Protocol

_PART_PREFIX = re.compile(r"^Part\s+[A-Z]\s+[—–-]\s+", re.IGNORECASE)


class ColorBands(Protocol):
    label: str
    red: str
    yellow: str
    green: str


@dataclass(frozen=True)
class WidgetSpec:
    title: str
    formula: str | None
    unit: str | None
    precision: int | None


@dataclass(frozen=True)
class Tile:
    title: str
    value: float | None
    display: str
    css_class: str


def section_suffix(title: str) -> str:
    """Drop a leading ``Part X —`` so the renderer does not number the title twice."""
    return _PART_PREFIX.sub("", title).strip() or title


def titles_match(left: str, right: str) -> bool:
    """True when two labels refer to the same widget, ignoring case and plural."""
    a, b = _norm(left), _norm(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    aw, bw = a.split(), b.split()
    if len(aw) != len(bw):
        return False
    return all(x == y or x.startswith(y) or y.startswith(x) for x, y in zip(aw, bw, strict=True))


def query_value_specs(dashboard: dict[str, Any]) -> dict[str, WidgetSpec]:
    """First query-value widget for each title, including its display formula."""
    specs: dict[str, WidgetSpec] = {}
    for widget in _flatten_widgets(dashboard.get("widgets") or []):
        definition = widget.get("definition") or {}
        if definition.get("type") != "query_value":
            continue
        title = definition.get("title") or ""
        if not title or title in specs:
            continue
        requests = definition.get("requests") or []
        request = requests[0] if requests else {}
        formulas = request.get("formulas") or []
        formula = None
        unit = None
        if formulas and isinstance(formulas[0], dict):
            formula = formulas[0].get("formula")
            unit_info = (formulas[0].get("number_format") or {}).get("unit") or {}
            unit = unit_info.get("unit_name")
        precision = definition.get("precision")
        specs[title] = WidgetSpec(
            title=title,
            formula=formula if isinstance(formula, str) else None,
            unit=unit if isinstance(unit, str) else None,
            precision=precision if isinstance(precision, int) else None,
        )
    return specs


def build_tiles(
    results: list[dict[str, Any]],
    *,
    focus: tuple[str, ...] = (),
    color_rules: tuple[ColorBands, ...] = (),
    specs: dict[str, WidgetSpec] | None = None,
) -> list[Tile]:
    """One tile per focus term, or one per first-seen widget when focus is empty."""
    specs = specs or {}
    groups = _first_groups(results)
    if not focus:
        return [_tile(title, _raw_latest(rows), None, None) for title, rows in groups]

    tiles = []
    for term in focus:
        group = next(((title, rows) for title, rows in groups if titles_match(term, title)), None)
        spec = _spec_for(term, group[0] if group else None, specs)
        title = group[0] if group else (spec.title if spec else term)
        value = _display_value(group[1], spec) if group else None
        rule = _rule_for(term, title, color_rules)
        tiles.append(_tile(title, value, spec, rule))
    return tiles


def eval_formula(expr: str, env: dict[str, float | None]) -> float | None:
    """Evaluate a Datadog query-value formula. Unknown calls or divide-by-zero → None."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    return _eval_node(tree.body, env)


def band_matches(value: float, expr: str) -> bool:
    """True when ``value`` falls in a markdown colour cell such as ``< 50%`` or ``50–80%``."""
    text = (
        expr.strip()
        .replace("—", "")
        .replace("–", "-")
        .replace("%", "")
        .replace("≤", "<=")
        .replace("≥", ">=")
        .strip()
    )
    if not text or text in {"-", "n/a"}:
        return False
    compared = re.fullmatch(r"([<>]=?)\s*(-?\d+(?:\.\d+)?)", text)
    if compared:
        op, number = compared.group(1), float(compared.group(2))
        return {
            "<": value < number,
            "<=": value <= number,
            ">": value > number,
            ">=": value >= number,
        }[op]
    span = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)", text)
    if span:
        low, high = float(span.group(1)), float(span.group(2))
        return low <= value <= high
    exact = re.fullmatch(r"-?\d+(?:\.\d+)?", text)
    if exact:
        return value == float(text)
    return False


def _norm(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.lower().replace("catalogue", "catalog")).strip()
    return collapsed


def _flatten_widgets(widgets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for widget in widgets:
        flat.append(widget)
        nested = (widget.get("definition") or {}).get("widgets") or []
        if nested:
            flat.extend(_flatten_widgets(nested))
    return flat


def _first_groups(results: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Keep the first run of rows for each widget title. Later repeats are breakdowns."""
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    seen: set[str] = set()
    current_title: str | None = None
    current_rows: list[dict[str, Any]] = []

    def close() -> None:
        nonlocal current_rows
        if current_title and current_title not in seen and current_rows:
            groups.append((current_title, current_rows))
            seen.add(current_title)
        current_rows = []

    for row in results:
        title = str(row.get("widget_title") or "—")
        if title != current_title:
            close()
            current_title = title
        if title not in seen:
            current_rows.append(row)
    close()
    return groups


def _spec_for(
    term: str,
    title: str | None,
    specs: dict[str, WidgetSpec],
) -> WidgetSpec | None:
    if title and title in specs:
        return specs[title]
    for spec in specs.values():
        if titles_match(term, spec.title) or (title and titles_match(title, spec.title)):
            return spec
    return None


def _rule_for(term: str, title: str, rules: tuple[ColorBands, ...]) -> ColorBands | None:
    for rule in rules:
        if titles_match(rule.label, title) or titles_match(rule.label, term):
            return rule
    return None


def _raw_latest(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    series = rows[0].get("series") or []
    if not series:
        return None
    latest = series[0].get("latest")
    return float(latest) if latest is not None else None


def _display_value(rows: list[dict[str, Any]], spec: WidgetSpec | None) -> float | None:
    if spec and spec.formula:
        env: dict[str, float | None] = {}
        for row in rows:
            name = row.get("subquery")
            if isinstance(name, str):
                env[name] = _raw_latest([row])
        if env:
            return eval_formula(spec.formula, env)
    return _raw_latest(rows)


def _format_value(value: float | None, spec: WidgetSpec | None) -> str:
    if value is None:
        return "—"
    if spec and spec.precision is not None:
        text = f"{value:.{spec.precision}f}"
    else:
        text = f"{value:.1f}"
    if spec and spec.unit == "percent":
        return f"{text}%"
    return text


def _tile_class(value: float | None, rule: ColorBands | None) -> str:
    if value is None:
        return "tile-grey"
    if rule is None:
        return "tile-green"
    for css, expr in (
        ("tile-red", rule.red),
        ("tile-yellow", rule.yellow),
        ("tile-green", rule.green),
    ):
        if band_matches(value, expr):
            return css
    return "tile-grey"


def _tile(
    title: str,
    value: float | None,
    spec: WidgetSpec | None,
    rule: ColorBands | None,
) -> Tile:
    return Tile(
        title=title,
        value=value,
        display=_format_value(value, spec),
        css_class=_tile_class(value, rule),
    )


def _eval_node(node: ast.AST, env: dict[str, float | None]) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _eval_node(node.operand, env)
        return None if value is None else -value
    if isinstance(node, ast.BinOp) and type(node.op) in {ast.Add, ast.Sub, ast.Mult, ast.Div}:
        left = _eval_node(node.left, env)
        right = _eval_node(node.right, env)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            return None
        return left / right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [_eval_node(arg, env) for arg in node.args]
        if node.func.id == "default_zero":
            value = args[0] if args else None
            return 0.0 if value is None else float(value)
        if node.func.id == "clamp_max" and len(args) == 2:
            value, limit = args
            if value is None or limit is None:
                return None
            return min(value, limit)
        if node.func.id == "clamp_min" and len(args) == 2:
            value, limit = args
            if value is None or limit is None:
                return None
            return max(value, limit)
    return None
