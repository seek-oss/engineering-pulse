"""Rasterize inline sprint-report SVG charts to PNG for HTML email clients.

Gmail and Outlook often strip SVG geometry (<polyline>, <path>, etc.) while leaving
<text>, which makes charts look empty. This module converts each top-level <svg>
in the report to a base64 <img> for the emailed copy only.
"""

from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

SVG_TAG_RE = re.compile(r"<svg\b[\s\S]*?</svg>", re.IGNORECASE)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_float(value: str | None, default: float = 0.0) -> float:
    if not value:
        return default
    value = value.strip().replace("px", "")
    if value.endswith("%"):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_color(value: str | None, default: str = "#000000") -> str:
    if not value:
        return default
    value = value.strip()
    if value.startswith("#") and len(value) in (4, 7):
        return value
    return default


def _parse_points(raw: str) -> list[tuple[float, float]]:
    nums = [p for p in re.split(r"[\s,]+", raw.strip()) if p]
    pts: list[tuple[float, float]] = []
    it = iter(nums)
    for x in it:
        try:
            y = next(it)
        except StopIteration:
            break
        pts.append((float(x), float(y)))
    return pts


def _parse_path_d(d: str) -> list[tuple[float, float]]:
    """Minimal path parser for M/L/Z commands used in sprint charts."""
    tokens = re.findall(
        r"([MLZmlz])|(-?\d*\.?\d+(?:e[-+]?\d+)?)",
        d.replace(",", " "),
    )
    pts: list[tuple[float, float]] = []
    i = 0
    cmd = "M"
    cur = (0.0, 0.0)
    while i < len(tokens):
        letter, num = tokens[i]
        if letter:
            cmd = letter.upper()
            i += 1
            continue
        if not num:
            i += 1
            continue
        x = float(num)
        if cmd == "Z":
            if pts:
                pts.append(pts[0])
            i += 1
            continue
        _, num2 = tokens[i + 1] if i + 1 < len(tokens) else ("", "")
        if not num2:
            break
        y = float(num2)
        cur = (x, y)
        pts.append(cur)
        i += 2
    return pts


def _svg_size(root: ET.Element) -> tuple[int, int]:
    vb = root.get("viewBox", "")
    vb_w = vb_h = None
    if vb:
        parts = vb.split()
        if len(parts) == 4:
            vb_w, vb_h = float(parts[2]), float(parts[3])
    w = _parse_float(root.get("width"), vb_w or 720.0)
    h = _parse_float(root.get("height"), vb_h or 280.0)
    if w <= 0:
        w = vb_w or 720.0
    if h <= 0:
        h = vb_h or 280.0
    return max(1, int(w)), max(1, int(h))


def rasterize_svg_markup(svg_markup: str, scale: float = 2.0) -> bytes:
    """Return PNG bytes for one inline SVG fragment."""
    root = ET.fromstring(svg_markup)
    w, h = _svg_size(root)
    out_w = max(1, int(w * scale))
    out_h = max(1, int(h * scale))
    img = Image.new("RGB", (out_w, out_h), "#ffffff")
    draw = ImageDraw.Draw(img)

    sx = out_w / w
    sy = out_h / h

    def scaled_draw_element(el: ET.Element) -> None:
        tag = _local(el.tag)
        if tag == "rect":
            x = _parse_float(el.get("x")) * sx
            y = _parse_float(el.get("y")) * sy
            rw = _parse_float(el.get("width"), w) * sx
            rh = _parse_float(el.get("height"), h) * sy
            fill = el.get("fill")
            if fill and fill != "none":
                draw.rectangle([x, y, x + rw, y + rh], fill=_parse_color(fill, "#fafafa"))
            return
        if tag == "line":
            stroke = _parse_color(el.get("stroke"), "#000000")
            width = max(1, int(_parse_float(el.get("stroke-width"), 1.0) * scale))
            x1 = _parse_float(el.get("x1")) * sx
            y1 = _parse_float(el.get("y1")) * sy
            x2 = _parse_float(el.get("x2")) * sx
            y2 = _parse_float(el.get("y2")) * sy
            draw.line([x1, y1, x2, y2], fill=stroke, width=width)
            return
        if tag == "polyline":
            pts = [(px * sx, py * sy) for px, py in _parse_points(el.get("points", ""))]
            if len(pts) < 2:
                return
            stroke = _parse_color(el.get("stroke"), "#000000")
            width = max(1, int(_parse_float(el.get("stroke-width"), 1.0) * scale))
            draw.line(pts, fill=stroke, width=width, joint="curve")
            return
        if tag == "path":
            d = el.get("d", "")
            fill = el.get("fill")
            stroke = el.get("stroke")
            pts = [(px * sx, py * sy) for px, py in _parse_path_d(d)]
            if fill and fill != "none" and len(pts) >= 3:
                draw.polygon(pts, fill=_parse_color(fill, "#d1e9ff"))
            elif stroke and stroke != "none" and len(pts) >= 2:
                width = max(1, int(_parse_float(el.get("stroke-width"), 1.0) * scale))
                draw.line(pts, fill=_parse_color(stroke), width=width)
            return
        if tag == "circle":
            cx = _parse_float(el.get("cx")) * sx
            cy = _parse_float(el.get("cy")) * sy
            r = _parse_float(el.get("r"), 3.0) * scale
            fill = _parse_color(el.get("fill"), "#000000")
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
            return
        if tag == "text":
            x = _parse_float(el.get("x")) * sx
            y = _parse_float(el.get("y")) * sy
            text = (el.text or "").strip()
            if not text:
                return
            fill = _parse_color(el.get("fill"), "#444444")
            size = max(8, int(_parse_float(el.get("font-size"), 11.0) * scale))
            font = ImageFont.load_default(size=size)
            anchor = el.get("text-anchor", "start")
            if anchor == "middle":
                bbox = draw.textbbox((0, 0), text, font=font)
                x -= (bbox[2] - bbox[0]) / 2
            elif anchor == "end":
                bbox = draw.textbbox((0, 0), text, font=font)
                x -= bbox[2] - bbox[0]
            draw.text((x, y - size), text, fill=fill, font=font)
            return
        if tag in ("style", "defs"):
            return
        for child in el:
            scaled_draw_element(child)

    # Background from root rect or default
    bg = root.get("fill") or "#ffffff"
    for child in root:
        if _local(child.tag) == "rect" and child.get("width") in ("100%", None):
            bg_el = child.get("fill")
            if bg_el:
                bg = bg_el
    draw.rectangle([0, 0, out_w, out_h], fill=_parse_color(bg, "#ffffff"))

    for child in root:
        scaled_draw_element(child)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _img_tag(png_bytes: bytes, width: int, height: int, alt: str) -> str:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return (
        f'<img src="data:image/png;base64,{b64}" '
        f'width="{width}" height="{height}" alt="{alt}" '
        f'style="max-width:100%;height:auto;display:block;border:0;" />'
    )


def _svg_display_size(svg_markup: str) -> tuple[int, int]:
    root = ET.fromstring(svg_markup)
    return _svg_size(root)


def replace_svgs_with_png_images(html: str) -> tuple[str, int]:
    """Replace each inline SVG with a base64 PNG img. Returns (html, count)."""
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        svg = match.group(0)
        aria = re.search(r'aria-label="([^"]*)"', svg, re.I)
        alt = aria.group(1) if aria else "Chart"
        w, h = _svg_display_size(svg)
        png = rasterize_svg_markup(svg)
        count += 1
        return _img_tag(png, w, h, alt)

    out = SVG_TAG_RE.sub(repl, html)
    return out, count


def prepare_sprint_report_html_for_email(html: str) -> str:
    """Return HTML suitable for SMTP with rasterized chart images."""
    updated, n = replace_svgs_with_png_images(html)
    if n == 0:
        return html
    return updated


def is_sprint_report_html_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    return name.startswith("sprint-report-") and name.endswith(".html")
