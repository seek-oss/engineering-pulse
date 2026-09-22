"""Rasterize inline sprint-report SVG charts to PNG for HTML email clients.

Gmail and Outlook often strip SVG geometry (<polyline>, <path>, etc.) while leaving
<text>, which makes charts look empty. This module converts each top-level <svg>
in the report to a base64 <img> for the emailed copy only.
"""

from __future__ import annotations

import base64
import io
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SVG_TAG_RE = re.compile(r"<svg\b[\s\S]*?</svg>", re.IGNORECASE)
EMAIL_CHART_WRAP = (
    '<div style="background:#fff;border:1px solid #eaecf0;border-radius:8px;'
    'padding:8px 8px 4px;margin:8px 0;">{img}</div>'
)

_FONT_CACHE: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


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


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = _parse_color(color)
    if len(color) == 4:
        r = int(color[1] * 2, 16)
        g = int(color[2] * 2, 16)
        b = int(color[3] * 2, 16)
        return r, g, b
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _blend(fg: str, bg: str, alpha: float) -> str:
    if alpha >= 1.0:
        return _parse_color(fg)
    fr, fg_g, fb = _hex_to_rgb(fg)
    br, bg_g, bb = _hex_to_rgb(bg)
    t = max(0.0, min(1.0, alpha))
    r = int(fr * t + br * (1 - t))
    g = int(fg_g * t + bg_g * (1 - t))
    b = int(fb * t + bb * (1 - t))
    return f"#{r:02x}{g:02x}{b:02x}"


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
        pts.append((x, y))
        i += 2
    return pts


def _parse_dash(raw: str | None) -> tuple[float, float] | None:
    if not raw:
        return None
    parts = [float(p) for p in raw.replace(",", " ").split() if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], parts[0]
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            font = ImageFont.truetype(path, size=size)
            _FONT_CACHE[size] = font
            return font
    font = ImageFont.load_default(size=size)
    _FONT_CACHE[size] = font
    return font


def _polyline_length(pts: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        total += math.hypot(dx, dy)
    return total


def _point_at(pts: list[tuple[float, float]], dist: float) -> tuple[float, float]:
    if dist <= 0:
        return pts[0]
    walked = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        seg = math.hypot(dx, dy)
        if walked + seg >= dist:
            t = (dist - walked) / seg if seg else 0
            return pts[i - 1][0] + dx * t, pts[i - 1][1] + dy * t
        walked += seg
    return pts[-1]


def _draw_stroked_polyline(
    draw: ImageDraw.ImageDraw,
    pts: list[tuple[float, float]],
    fill: str,
    width: int,
    dash: tuple[float, float] | None,
    opacity: float,
) -> None:
    if len(pts) < 2:
        return
    color = fill
    if opacity < 1.0:
        color = _blend(fill, "#ffffff", opacity)
    if not dash:
        draw.line(pts, fill=color, width=width, joint="curve")
        return
    on, off = dash
    total = _polyline_length(pts)
    dist = 0.0
    drawing = True
    while dist < total:
        seg_len = on if drawing else off
        start = _point_at(pts, dist)
        end = _point_at(pts, min(dist + seg_len, total))
        if drawing:
            draw.line([start, end], fill=color, width=width)
        dist += seg_len
        drawing = not drawing


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


def rasterize_svg_markup(svg_markup: str, scale: float = 3.0) -> bytes:
    """Return PNG bytes for one inline SVG fragment."""
    root = ET.fromstring(svg_markup)
    w, h = _svg_size(root)
    out_w = max(1, int(w * scale))
    out_h = max(1, int(h * scale))
    img = Image.new("RGB", (out_w, out_h), "#ffffff")
    draw = ImageDraw.Draw(img)

    sx = out_w / w
    sy = out_h / h

    bg = "#ffffff"
    for child in root:
        if _local(child.tag) == "rect":
            rw = child.get("width", "")
            if rw.endswith("%") or rw == "100%":
                fill = child.get("fill")
                if fill and fill != "none":
                    bg = fill
    draw.rectangle([0, 0, out_w, out_h], fill=_parse_color(bg, "#ffffff"))

    def scaled_draw_element(el: ET.Element) -> None:
        tag = _local(el.tag)
        if tag == "style":
            return
        if tag == "rect":
            x = _parse_float(el.get("x")) * sx
            y = _parse_float(el.get("y")) * sy
            rw_attr = el.get("width", "")
            rh_attr = el.get("height", "")
            if rw_attr.endswith("%"):
                rw = out_w * float(rw_attr[:-1]) / 100.0
            else:
                rw = _parse_float(rw_attr, w) * sx
            if rh_attr.endswith("%"):
                rh = out_h * float(rh_attr[:-1]) / 100.0
            else:
                rh = _parse_float(rh_attr, h) * sy
            fill = el.get("fill")
            if fill and fill != "none":
                draw.rectangle([x, y, x + rw, y + rh], fill=_parse_color(fill, "#fafafa"))
            return
        if tag == "line":
            stroke = _parse_color(el.get("stroke"), "#000000")
            width = max(1, int(_parse_float(el.get("stroke-width"), 1.0) * scale))
            opacity = _parse_float(el.get("opacity"), 1.0)
            x1 = _parse_float(el.get("x1")) * sx
            y1 = _parse_float(el.get("y1")) * sy
            x2 = _parse_float(el.get("x2")) * sx
            y2 = _parse_float(el.get("y2")) * sy
            dash = _parse_dash(el.get("stroke-dasharray"))
            _draw_stroked_polyline(draw, [(x1, y1), (x2, y2)], stroke, width, dash, opacity)
            return
        if tag == "polyline":
            pts = [(px * sx, py * sy) for px, py in _parse_points(el.get("points", ""))]
            stroke = _parse_color(el.get("stroke"), "#000000")
            width = max(1, int(_parse_float(el.get("stroke-width"), 1.0) * scale))
            opacity = _parse_float(el.get("opacity"), 1.0)
            dash = _parse_dash(el.get("stroke-dasharray"))
            _draw_stroked_polyline(draw, pts, stroke, width, dash, opacity)
            return
        if tag == "path":
            d = el.get("d", "")
            fill = el.get("fill")
            stroke = el.get("stroke")
            pts = [(px * sx, py * sy) for px, py in _parse_path_d(d)]
            fill_opacity = _parse_float(el.get("fill-opacity"), 1.0)
            if fill and fill != "none" and len(pts) >= 3:
                color = _blend(fill, bg, fill_opacity)
                draw.polygon(pts, fill=color)
            elif stroke and stroke != "none" and len(pts) >= 2:
                width = max(1, int(_parse_float(el.get("stroke-width"), 1.0) * scale))
                dash = _parse_dash(el.get("stroke-dasharray"))
                _draw_stroked_polyline(draw, pts, _parse_color(stroke), width, dash, 1.0)
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
            size = max(9, int(_parse_float(el.get("font-size"), 11.0) * scale))
            font = _load_font(size)
            anchor = el.get("text-anchor", "start")
            if anchor == "middle":
                bbox = draw.textbbox((0, 0), text, font=font)
                x -= (bbox[2] - bbox[0]) / 2
            elif anchor == "end":
                bbox = draw.textbbox((0, 0), text, font=font)
                x -= bbox[2] - bbox[0]
            draw.text((x, y - size * 0.85), text, fill=fill, font=font)
            return

    for el in root.iter():
        if el is root:
            continue
        scaled_draw_element(el)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _img_tag(png_bytes: bytes, width: int, height: int, alt: str) -> str:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    img = (
        f'<img src="data:image/png;base64,{b64}" '
        f'width="{width}" height="{height}" alt="{alt}" '
        f'style="max-width:100%;height:auto;display:block;border:0;" />'
    )
    return EMAIL_CHART_WRAP.format(img=img)


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
