"""Transactional email delivery through SMTP or the Resend HTTPS API.

Verification codes and account-recovery links must actually leave the server, so
delivery failures are raised as EmailDeliveryError and logged by the caller
instead of being silently swallowed.
"""
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request

from .config import settings

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


class EmailDeliveryError(RuntimeError):
    """Raised when an email cannot be handed to a configured provider."""


def delivery_channel() -> str:
    """Return 'resend', 'smtp' or '' when no provider is configured."""
    if settings.resend_api_key:
        return "resend"
    if settings.smtp_host and settings.smtp_from:
        return "smtp"
    return ""


def sender_address() -> str:
    return settings.resend_from or settings.smtp_from


def _html_body(body: str) -> str:
    blocks: list[str] = []
    for line in body.splitlines():
        text = line.strip()
        if not text:
            blocks.append('<div style="height:8px"></div>')
        elif text.isdigit() and len(text) == 6:
            blocks.append(
                '<p style="font-size:30px;font-weight:700;letter-spacing:.32em;'
                'margin:20px 0;color:#12203a">' + escape(text) + "</p>"
            )
        else:
            blocks.append(f'<p style="margin:0 0 10px">{escape(line)}</p>')
    return (
        "<!doctype html><html><body style=\"margin:0;padding:24px;background:#f4f5f7;"
        "font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:#1f2430\">"
        '<div style="max-width:540px;margin:0 auto;background:#ffffff;border:1px solid #e3e6ec;'
        'border-radius:14px;padding:28px">'
        '<div style="font-size:12px;letter-spacing:.16em;color:#7a8190">FACTORYLINK</div>'
        f'<div style="font-size:15px;line-height:1.65;margin-top:14px">{"".join(blocks)}</div>'
        '<div style="margin-top:26px;font-size:12px;color:#8d94a3">'
        "FactoryLink · Manufacturing operations workspace</div>"
        "</div></body></html>"
    )


def build_message(to_email: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender_address()
    message["To"] = to_email
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=(sender_address().rsplit("@", 1)[-1].strip("> ") or "factorylink.jp"))
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(body)
    message.add_alternative(_html_body(body), subtype="html")
    return message


def _deliver_smtp(to_email: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise EmailDeliveryError("SMTP_HOST and SMTP_FROM must be configured for email delivery")
    message = build_message(to_email, subject, body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        client.ehlo()
        if settings.smtp_starttls:
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


def _deliver_resend(to_email: str, subject: str, body: str) -> None:
    if not settings.resend_api_key:
        raise EmailDeliveryError("RESEND_API_KEY must be configured for Resend delivery")
    if not sender_address() or "factorylink.local" in sender_address().lower():
        raise EmailDeliveryError("RESEND_FROM must be a verified sender address")
    payload = json.dumps({
        "from": sender_address(),
        "to": [to_email],
        "subject": subject,
        "text": body,
        "html": _html_body(body),
    }).encode("utf-8")
    request = urllib.request.Request(
        RESEND_ENDPOINT,
        data=payload,
        method="POST",
        headers={"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if not 200 <= response.status < 300:
                raise EmailDeliveryError(f"Resend rejected the message (HTTP {response.status})")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise EmailDeliveryError(f"Resend rejected the message (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise EmailDeliveryError(f"Resend is unreachable: {exc.reason}") from exc


def deliver_email(to_email: str, subject: str, body: str) -> str:
    """Deliver one email and return the channel used; never log code contents."""
    channel = delivery_channel()
    if not channel:
        raise EmailDeliveryError(
            "No email delivery channel is configured; set SMTP_HOST/SMTP_FROM (or SMTP credentials) "
            "or RESEND_API_KEY/RESEND_FROM"
        )
    if channel == "resend":
        _deliver_resend(to_email, subject, body)
    else:
        _deliver_smtp(to_email, subject, body)
    logger.info("Delivered transactional email %s to %s via %s", subject, to_email, channel)
    return channel
