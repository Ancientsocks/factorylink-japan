from unittest.mock import MagicMock, patch
import pytest
from app.config import settings
from app.mailer import deliver_email


def test_smtp_delivery_uses_starttls_and_authentication(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.jp")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "mailer@example.jp")
    monkeypatch.setattr(settings, "smtp_password", "smtp-secret")
    monkeypatch.setattr(settings, "smtp_from", "FactoryLink <no-reply@example.jp>")
    monkeypatch.setattr(settings, "smtp_starttls", True)
    fake = MagicMock()
    fake.__enter__.return_value = fake
    with patch("app.mailer.smtplib.SMTP", return_value=fake) as smtp:
        deliver_email("user@example.jp", "Password reset", "Use this one-time link")
    smtp.assert_called_once_with("smtp.example.jp", 587, timeout=15)
    assert fake.ehlo.call_count == 2
    fake.starttls.assert_called_once()
    fake.login.assert_called_once_with("mailer@example.jp", "smtp-secret")
    fake.send_message.assert_called_once()
    message = fake.send_message.call_args.args[0]
    assert message["To"] == "user@example.jp"
    assert message["Subject"] == "Password reset"


def test_smtp_delivery_refuses_missing_host(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        deliver_email("user@example.jp", "Hello", "Body")
