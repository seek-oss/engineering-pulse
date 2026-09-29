#!/usr/bin/env python3
"""
Send an email via SMTP. Supports plain text (.txt) and HTML (.html).
Reads credentials from environment / .env (python-dotenv).

Required env:
  SMTP_USER, SMTP_PASSWORD, SMTP_FROM
Defaults (Gmail):
  SMTP_HOST=smtp.gmail.com, SMTP_PORT=587
Optional:
  SMTP_TO (required — set in .env)
  SMTP_USE_TLS (default: true for port 587 — STARTTLS)

Usage:
  python scripts/send_report_smtp.py "Subject line" report.html
  python scripts/send_report_smtp.py "Subject line" report.txt
  cat report.html | python scripts/send_report_smtp.py "Subject line" -

Inline <svg> charts are rasterised to PNG (resvg-py) and embedded as CID images
in the emailed copy only, because Gmail and Outlook drop inline SVG. The report
file on disk is not modified. If rasterising fails, each chart is replaced by a
short note and the original HTML is attached.
"""

import html
import os
import re
import smtplib
import ssl
import sys
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()


SVG_RE = re.compile(r"<svg\b[\s\S]*?</svg>", re.IGNORECASE)
_VIEWBOX_RE = re.compile(r'viewBox="\s*[\d.+-]+[\s,]+[\d.+-]+[\s,]+([\d.]+)', re.IGNORECASE)
_CHART_NAME_RE = re.compile(r'(?:data-chart|aria-label)="([^"]+)"', re.IGNORECASE)
PNG_ZOOM = 2
CHART_FALLBACK_NOTE = (
    '<p style="color:#667085;font-style:italic;">'
    "Chart not shown in email; open the attached HTML report to view it.</p>"
)


def _detect_html(body: str) -> bool:
    return body.strip().lower().startswith(("<!doctype", "<html"))


def _render_svg_png(svg: str) -> bytes:
    import resvg_py

    return resvg_py.svg_to_bytes(
        svg_string=svg,
        zoom=PNG_ZOOM,
        background="#ffffff",
        font_family="Helvetica",
        sans_serif_family="Helvetica",
    )


def inline_svg_charts(body: str, render=None) -> tuple[str, list[tuple[str, bytes]]]:
    """Replace each inline <svg> with a CID <img>; return (html, [(cid, png)]).

    A chart that fails to render is replaced with CHART_FALLBACK_NOTE and omitted
    from the returned image list.
    """
    render = render or _render_svg_png
    images: list[tuple[str, bytes]] = []

    def _replace(match: re.Match) -> str:
        svg = match.group(0)
        try:
            png = render(svg)
        except Exception as exc:
            print(f"Warning: could not rasterise chart for email: {exc}", file=sys.stderr)
            return CHART_FALLBACK_NOTE
        cid = f"chart-{len(images) + 1}@engineering-pulse"
        images.append((cid, png))
        name = _CHART_NAME_RE.search(svg)
        alt = html.escape(f"{name.group(1)} chart" if name else "Chart", quote=True)
        viewbox = _VIEWBOX_RE.search(svg)
        width = int(float(viewbox.group(1))) if viewbox else 600
        return (
            f'<img src="cid:{cid}" alt="{alt}" width="{width}" '
            f'style="display:block;width:100%;max-width:{width}px;height:auto;border:0;">'
        )

    return SVG_RE.sub(_replace, body), images


def _build_html_message(body: str, attachment: Path | None = None) -> MIMEMultipart:
    html_body, images = inline_svg_charts(body)
    chart_count = len(SVG_RE.findall(body))

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText("See HTML version of this report.", "plain", "utf-8"))
    alternative.attach(MIMEText(html_body, "html", "utf-8"))

    msg = alternative
    if images:
        msg = MIMEMultipart("related")
        msg.attach(alternative)
        for cid, png in images:
            part = MIMEImage(png, "png")
            part.add_header("Content-ID", f"<{cid}>")
            part.add_header("Content-Disposition", "inline", filename=f"{cid.split('@')[0]}.png")
            msg.attach(part)

    if len(images) < chart_count and attachment is not None:
        mixed = MIMEMultipart("mixed")
        mixed.attach(msg)
        report = MIMEApplication(attachment.read_bytes(), "html")
        report.add_header("Content-Disposition", "attachment", filename=attachment.name)
        mixed.attach(report)
        msg = mixed

    return msg


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    subject = sys.argv[1]
    path = sys.argv[2]

    if path == "-":
        body = sys.stdin.read()
    else:
        body = Path(path).read_text(encoding="utf-8")

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    from_addr = os.environ.get("SMTP_FROM")
    to_addr = os.environ.get("SMTP_TO", "")
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    missing = [
        k
        for k, v in [
            ("SMTP_USER", user),
            ("SMTP_PASSWORD", password),
            ("SMTP_FROM", from_addr),
            ("SMTP_TO", to_addr),
        ]
        if not v
    ]
    if missing:
        print(f"Missing env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    is_html = _detect_html(body) or (path.endswith(".html") and path != "-")

    if is_html:
        msg = _build_html_message(body, attachment=None if path == "-" else Path(path))
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    if port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
    else:
        with smtplib.SMTP(host, port) as server:
            if use_tls:
                server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())

    print(f"Sent to {to_addr}")


if __name__ == "__main__":
    main()
