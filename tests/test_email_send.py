"""Tests for email sending functionality."""

from unittest.mock import MagicMock, patch, ANY

import pytest

from koda.integrations.imap_client import IMAPClient


class TestIMAPClientSMTP:
    """Test IMAP client SMTP sending capability."""

    def test_infer_smtp_host_gmail(self):
        """Test SMTP host inference for Gmail."""
        assert IMAPClient._infer_smtp_host("imap.gmail.com") == "smtp.gmail.com"

    def test_infer_smtp_host_outlook(self):
        """Test SMTP host inference for Outlook."""
        assert IMAPClient._infer_smtp_host("outlook.office365.com") == "smtp.office365.com"

    def test_infer_smtp_host_icloud(self):
        """Test SMTP host inference for iCloud."""
        assert IMAPClient._infer_smtp_host("imap.mail.me.com") == "smtp.mail.me.com"

    def test_infer_smtp_host_generic(self):
        """Test SMTP host inference for generic IMAP."""
        assert IMAPClient._infer_smtp_host("imap.example.com") == "smtp.example.com"

    def test_infer_smtp_host_unknown(self):
        """Test SMTP host inference for unknown host."""
        assert IMAPClient._infer_smtp_host("mail.custom.org") == ""

    def test_infer_smtp_host_empty(self):
        """Test SMTP host inference for empty string."""
        assert IMAPClient._infer_smtp_host("") == ""

    @patch("koda.integrations.imap_client.IMAPClient._infer_smtp_host", return_value="smtp.gmail.com")
    @patch("smtplib.SMTP")
    def test_send_email_starttls(self, mock_smtp_class, mock_infer):
        """Test sending email with STARTTLS."""
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        client = IMAPClient(
            host="imap.gmail.com",
            port=993,
            username="user@gmail.com",
            password="pass123",
        )

        result = client.send_email(
            to="recipient@example.com",
            subject="Test Subject",
            body="Test Body",
        )

        mock_smtp_class.assert_called_once_with("smtp.gmail.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@gmail.com", "pass123")
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()

        assert result["status"] == "sent"
        assert result["to"] == ["recipient@example.com"]
        assert result["subject"] == "Test Subject"

    @patch("smtplib.SMTP_SSL")
    def test_send_email_ssl(self, mock_smtp_ssl_class):
        """Test sending email with SSL."""
        mock_server = MagicMock()
        mock_smtp_ssl_class.return_value = mock_server

        client = IMAPClient(
            host="imap.example.com",
            port=993,
            username="user@example.com",
            password="pass123",
        )

        result = client.send_email(
            to="recipient@example.com",
            subject="SSL Test",
            body="Body",
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_use_tls=False,
            smtp_use_ssl=True,
        )

        mock_smtp_ssl_class.assert_called_once_with("smtp.example.com", 465)
        mock_server.login.assert_called_once()
        assert result["status"] == "sent"

    @patch("smtplib.SMTP")
    def test_send_email_with_cc(self, mock_smtp_class):
        """Test sending email with CC recipients."""
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        client = IMAPClient(
            host="imap.gmail.com",
            port=993,
            username="user@gmail.com",
            password="pass123",
        )

        result = client.send_email(
            to="to@example.com",
            subject="CC Test",
            body="Body",
            cc="cc1@example.com, cc2@example.com",
            smtp_host="smtp.gmail.com",
        )

        assert result["cc"] == ["cc1@example.com", "cc2@example.com"]
        # sendmail should include both to and cc recipients
        call_args = mock_server.sendmail.call_args
        all_recipients = call_args[0][1]
        assert "to@example.com" in all_recipients
        assert "cc1@example.com" in all_recipients
        assert "cc2@example.com" in all_recipients

    def test_send_email_no_smtp_host_raises(self):
        """Test that sending without SMTP host raises error."""
        client = IMAPClient(
            host="mail.custom.org",  # No known SMTP mapping
            port=993,
            username="user@custom.org",
            password="pass123",
        )

        with pytest.raises(ValueError, match="Cannot determine SMTP server"):
            client.send_email(
                to="recipient@example.com",
                subject="Test",
                body="Body",
            )

    @patch("smtplib.SMTP")
    def test_send_email_list_recipients(self, mock_smtp_class):
        """Test sending to a list of recipients."""
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        client = IMAPClient(
            host="imap.gmail.com",
            port=993,
            username="user@gmail.com",
            password="pass123",
        )

        result = client.send_email(
            to=["a@example.com", "b@example.com"],
            subject="List Test",
            body="Body",
            smtp_host="smtp.gmail.com",
        )

        assert result["to"] == ["a@example.com", "b@example.com"]
