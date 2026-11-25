"""Email delivery selection and failure reporting for verification codes."""
import pytest

from app import mailer
from app import main as main_module
from app.mailer import EmailDeliveryError, deliver_email, delivery_channel


def test_no_provider_means_no_channel(monkeypatch):
    monkeypatch.setattr(mailer.settings, "resend_api_key", "")
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    assert delivery_channel() == ""
    with pytest.raises(EmailDeliveryError):
        deliver_email("someone@example.jp", "Subject", "Body")


def test_resend_takes_precedence_over_smtp(monkeypatch):
    monkeypatch.setattr(mailer.settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(mailer.settings, "smtp_host", "smtp.example.jp")
    monkeypatch.setattr(mailer.settings, "smtp_from", "FactoryLink <no-reply@example.jp>")
    assert delivery_channel() == "resend"


def test_smtp_is_used_when_configured(monkeypatch):
    monkeypatch.setattr(mailer.settings, "resend_api_key", "")
    monkeypatch.setattr(mailer.settings, "smtp_host", "smtp.example.jp")
    monkeypatch.setattr(mailer.settings, "smtp_from", "FactoryLink <no-reply@example.jp>")
    assert delivery_channel() == "smtp"


def test_queue_action_email_returns_false_without_a_provider(monkeypatch):
    monkeypatch.setattr(main_module.settings, "resend_api_key", "")
    monkeypatch.setattr(main_module.settings, "smtp_host", "")
    assert main_module.queue_action_email("someone@example.jp", "Subject", "Body") is False


def test_queue_action_email_sends_directly_outside_production(monkeypatch):
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "resend_api_key", "")
    monkeypatch.setattr(main_module.settings, "smtp_host", "smtp.example.jp")
    monkeypatch.setattr(main_module.settings, "smtp_from", "FactoryLink <no-reply@example.jp>")
    sent = {}
    monkeypatch.setattr(mailer, "deliver_email", lambda to, subject, body: sent.update(to=to) or "smtp")
    assert main_module.queue_action_email("someone@example.jp", "Subject", "Body") is True
    assert sent["to"] == "someone@example.jp"


def test_queue_action_email_reports_provider_failure(monkeypatch):
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "smtp_host", "smtp.example.jp")
    monkeypatch.setattr(main_module.settings, "smtp_from", "FactoryLink <no-reply@example.jp>")

    def fail(to, subject, body):
        raise EmailDeliveryError("SMTP login rejected")

    monkeypatch.setattr(mailer, "deliver_email", fail)
    assert main_module.queue_action_email("someone@example.jp", "Subject", "Body") is False


def test_html_body_highlights_the_code():
    html = mailer._html_body("Hello,\n\nYour code is:\n\n123456\n\nThanks")
    assert "123456" in html
    assert "letter-spacing" in html
