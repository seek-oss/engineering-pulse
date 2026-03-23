"""Tests for scripts/send_report_smtp.py."""
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from scripts.send_report_smtp import _detect_html, main


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
                mock_smtp_cls = MagicMock(return_value=__import__("contextlib").nullcontext(mock_server))
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
