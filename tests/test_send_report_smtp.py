"""Tests for scripts/send_report_smtp.py."""

import email
import sys
from unittest.mock import MagicMock, patch

import pytest
from scripts.send_report_smtp import (
    CHART_FALLBACK_NOTE,
    _build_html_message,
    _detect_html,
    _render_svg_png,
    inline_svg_charts,
    main,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHART_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 980 380" '
    'data-chart="burn-up"><polyline points="0,0 980,380" stroke="#4f6bed" '
    'stroke-width="2" fill="none"/><text x="10" y="20">0</text></svg>'
)
REPORT_HTML = f"<!doctype html><html><body><h2>Burn-up</h2>{CHART_SVG}</body></html>"

# ---------------------------------------------------------------------------
# _detect_html
# ---------------------------------------------------------------------------


class TestDetectHtml:
    def test_html_doctype_lowercase(self):
        assert _detect_html("<!doctype html><html><body></body></html>") is True

    def test_html_doctype_uppercase(self):
        assert _detect_html("<!DOCTYPE HTML><html></html>") is True

    def test_html_tag(self):
        assert _detect_html("<html><body>Hello</body></html>") is True

    def test_html_tag_with_leading_whitespace(self):
        assert _detect_html("  \n<!doctype html>") is True

    def test_plain_text(self):
        assert _detect_html("Hello, this is a plain text report.") is False

    def test_empty_string(self):
        assert _detect_html("") is False

    def test_partial_html_not_at_start(self):
        assert _detect_html("Some text <html>then html") is False

    def test_xml_not_detected_as_html(self):
        assert _detect_html('<?xml version="1.0"?><root/>') is False


# ---------------------------------------------------------------------------
# Inline SVG charts → CID PNG images
# ---------------------------------------------------------------------------


class TestInlineSvgCharts:
    def test_render_svg_png_produces_png(self):
        png = _render_svg_png(CHART_SVG)
        assert png.startswith(PNG_SIGNATURE)

    def test_replaces_svg_with_cid_img(self):
        out, images = inline_svg_charts(REPORT_HTML, render=lambda svg: PNG_SIGNATURE)
        assert "<svg" not in out
        assert '<img src="cid:chart-1@engineering-pulse"' in out
        assert 'alt="burn-up chart"' in out
        assert 'width="980"' in out
        assert images == [("chart-1@engineering-pulse", PNG_SIGNATURE)]

    def test_multiple_charts_get_unique_cids(self):
        body = REPORT_HTML.replace(CHART_SVG, CHART_SVG + CHART_SVG)
        out, images = inline_svg_charts(body, render=lambda svg: PNG_SIGNATURE)
        assert [cid for cid, _ in images] == [
            "chart-1@engineering-pulse",
            "chart-2@engineering-pulse",
        ]
        assert out.count("<img ") == 2

    def test_html_without_svg_is_unchanged(self):
        body = "<!doctype html><html><body><p>No charts</p></body></html>"
        out, images = inline_svg_charts(body, render=lambda svg: PNG_SIGNATURE)
        assert out == body
        assert images == []

    def test_render_failure_uses_fallback_note(self):
        def boom(svg):
            raise ValueError("bad svg")

        out, images = inline_svg_charts(REPORT_HTML, render=boom)
        assert "<svg" not in out
        assert CHART_FALLBACK_NOTE in out
        assert images == []


class TestBuildHtmlMessage:
    def test_charts_embedded_as_related_inline_images(self):
        msg = email.message_from_string(_build_html_message(REPORT_HTML).as_string())
        assert msg.get_content_type() == "multipart/related"
        images = [p for p in msg.walk() if p.get_content_type() == "image/png"]
        assert len(images) == 1
        assert images[0]["Content-ID"] == "<chart-1@engineering-pulse>"
        assert images[0].get_content_disposition() == "inline"
        assert images[0].get_payload(decode=True).startswith(PNG_SIGNATURE)
        html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
        html_body = html_part.get_payload(decode=True).decode()
        assert "cid:chart-1@engineering-pulse" in html_body
        assert "<svg" not in html_body

    def test_no_svg_keeps_plain_alternative(self):
        body = "<!doctype html><html><body><p>Dashboard</p></body></html>"
        msg = _build_html_message(body)
        assert msg.get_content_type() == "multipart/alternative"

    def test_render_failure_attaches_original_report(self, tmp_path):
        report = tmp_path / "sprint-report.html"
        report.write_text(REPORT_HTML)
        with patch("scripts.send_report_smtp._render_svg_png", side_effect=ValueError("x")):
            msg = _build_html_message(REPORT_HTML, attachment=report)
        assert msg.get_content_type() == "multipart/mixed"
        attachments = [p for p in msg.walk() if p.get_content_disposition() == "attachment"]
        assert [p.get_filename() for p in attachments] == ["sprint-report.html"]
        assert not [p for p in msg.walk() if p.get_content_type() == "image/png"]


# ---------------------------------------------------------------------------
# main() — argument validation and SMTP dispatch
# ---------------------------------------------------------------------------

FULL_ENV = {
    "SMTP_USER": "sender@gmail.com",
    "SMTP_PASSWORD": "secret",
    "SMTP_FROM": "sender@gmail.com",
    "SMTP_TO": "recipient@example.com",
}


class TestMain:
    def test_exits_when_too_few_args(self):
        with patch.object(sys, "argv", ["send_report_smtp.py"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_exits_when_missing_env_vars(self, tmp_path):
        report = tmp_path / "report.txt"
        report.write_text("Hello")
        with patch.object(sys, "argv", ["send_report_smtp.py", "Subject", str(report)]):
            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1

    def test_sends_plain_text_via_starttls(self, tmp_path):
        report = tmp_path / "report.txt"
        report.write_text("Plain text body")
        with patch.object(sys, "argv", ["send_report_smtp.py", "My Subject", str(report)]):
            with patch.dict("os.environ", FULL_ENV):
                mock_server = MagicMock()
                MagicMock(return_value=__import__("contextlib").nullcontext(mock_server))
                with patch("scripts.send_report_smtp.smtplib.SMTP") as mock_smtp:
                    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
                    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
                    main()
                mock_server.starttls.assert_called_once()
                mock_server.login.assert_called_once_with("sender@gmail.com", "secret")
                mock_server.sendmail.assert_called_once()

    def test_sends_html_when_file_ends_with_dot_html(self, tmp_path):
        report = tmp_path / "report.html"
        report.write_text("plain content")  # not real HTML but .html extension
        with patch.object(sys, "argv", ["send_report_smtp.py", "Subject", str(report)]):
            with patch.dict("os.environ", FULL_ENV):
                with patch("scripts.send_report_smtp.smtplib.SMTP") as mock_smtp:
                    mock_server = MagicMock()
                    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
                    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
                    # Capture what was sent
                    sent_messages = []
                    mock_server.sendmail.side_effect = lambda f, t, m: sent_messages.append(m)
                    main()
                # HTML emails use MIMEMultipart — message should contain both parts
                assert len(sent_messages) == 1
                assert "text/html" in sent_messages[0]

    def test_sends_via_ssl_when_port_465(self, tmp_path):
        report = tmp_path / "report.txt"
        report.write_text("body")
        env = {**FULL_ENV, "SMTP_PORT": "465"}
        with patch.object(sys, "argv", ["send_report_smtp.py", "Subject", str(report)]):
            with patch.dict("os.environ", env):
                with patch("scripts.send_report_smtp.smtplib.SMTP_SSL") as mock_ssl:
                    mock_server = MagicMock()
                    mock_ssl.return_value.__enter__ = MagicMock(return_value=mock_server)
                    mock_ssl.return_value.__exit__ = MagicMock(return_value=False)
                    main()
                mock_ssl.assert_called_once()
                mock_server.starttls.assert_not_called()

    def test_reads_from_stdin_when_path_is_dash(self):
        with patch.object(sys, "argv", ["send_report_smtp.py", "Subject", "-"]):
            with patch.dict("os.environ", FULL_ENV):
                with patch("sys.stdin") as mock_stdin:
                    mock_stdin.read.return_value = "stdin content"
                    with patch("scripts.send_report_smtp.smtplib.SMTP") as mock_smtp:
                        mock_server = MagicMock()
                        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
                        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
                        main()
                    mock_server.sendmail.assert_called_once()

    def test_no_starttls_when_use_tls_false(self, tmp_path):
        report = tmp_path / "report.txt"
        report.write_text("body")
        env = {**FULL_ENV, "SMTP_USE_TLS": "false"}
        with patch.object(sys, "argv", ["send_report_smtp.py", "Subject", str(report)]):
            with patch.dict("os.environ", env):
                with patch("scripts.send_report_smtp.smtplib.SMTP") as mock_smtp:
                    mock_server = MagicMock()
                    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
                    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
                    main()
                mock_server.starttls.assert_not_called()
