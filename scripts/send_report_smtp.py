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
"""

import os
import smtplib
import ssl
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

def _detect_html(body: str) -> bool:
    return body.strip().lower().startswith(("<!doctype", "<html"))


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

    missing = [k for k, v in [
        ("SMTP_USER", user),
        ("SMTP_PASSWORD", password),
        ("SMTP_FROM", from_addr),
        ("SMTP_TO", to_addr),
    ] if not v]
    if missing:
        print(f"Missing env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    is_html = _detect_html(body) or (path.endswith(".html") and path != "-")

    if is_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText("See HTML version of this report.", "plain", "utf-8"))
        msg.attach(MIMEText(body, "html", "utf-8"))
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
