"""Send one test email through the configured delivery channel.

Run from the backend directory after setting SMTP_* or RESEND_* variables:

    python scripts/check_email.py you@example.com

The script prints the selected channel and the provider error, if any, without
ever printing credentials or verification codes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mailer import EmailDeliveryError, deliver_email, delivery_channel  # noqa: E402

BODY = (
    "This is a FactoryLink delivery test.\n\n"
    "If you can read this, verification codes and password-reset mail will reach\n"
    "your inbox from this server.\n"
)


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("usage: python scripts/check_email.py you@example.com")
        return 2
    address = sys.argv[1].strip()
    channel = delivery_channel()
    print(f"channel: {channel or 'none configured'}")
    if not channel:
        print("Set SMTP_HOST + SMTP_FROM (and credentials), or RESEND_API_KEY + RESEND_FROM.")
        return 1
    try:
        used = deliver_email(address, "FactoryLink email delivery test", BODY)
    except EmailDeliveryError as exc:
        print(f"failed via {channel}: {exc}")
        return 1
    print(f"sent via {used} to {address}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
