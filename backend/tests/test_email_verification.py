"""Email-code verification for sign-up and password reset.

The code proves the address is reachable before a password is set, is single
use, expires, tolerates only a few wrong guesses, and never leaks outside
development when SMTP is not configured.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app import main as main_module
from app.database import Base, get_db
from app.main import app
from app.security import hash_password

PASSWORD = "FactoryLink2026!"
NEW_PASSWORD = "ReplacementPass2026!"


@pytest.fixture()
def context(monkeypatch):
    monkeypatch.setattr(main_module.settings, "malware_scan_enabled", False)
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", True)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = Session()
    organization = models.Organization(name="Sakura Verify", code="SAKURA-VERIFY", org_type="MANUFACTURER")
    db.add(organization); db.flush()
    db.add(models.User(organization_id=organization.id, email="owner@verify.jp", full_name="Verify Owner",
                       password_hash=hash_password(PASSWORD), role="ORG_ADMIN"))
    db.commit(); db.close()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield {"client": client, "Session": Session, "organization_id": organization.id}
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def request_code(client, email, purpose):
    return client.post("/api/v1/auth/email-verification/request", json={"email": email, "purpose": purpose})


def verify_code(client, email, purpose, code):
    return client.post("/api/v1/auth/email-verification/verify", json={"email": email, "purpose": purpose, "code": code})


def registration_payload(email, token, code="VERIFY-REG"):
    return {
        "organization_name": "Verified Works", "organization_code": code, "organization_type": "MANUFACTURER",
        "owner_name": "Verified Owner", "email": email, "password": NEW_PASSWORD, "language": "en",
        "email_verification_token": token,
    }


def test_registration_requires_code_before_password_and_creates_account(context):
    client = context["client"]
    requested = request_code(client, "new@verify.jp", "REGISTRATION")
    assert requested.status_code == 202, requested.text
    code = requested.json()["development_code"]
    assert len(code) == 6 and code.isdigit()

    verified = verify_code(client, "new@verify.jp", "REGISTRATION", code)
    assert verified.status_code == 200, verified.text
    ticket = verified.json()["verification_token"]

    created = client.post("/api/v1/organizations/register", json=registration_payload("new@verify.jp", ticket))
    assert created.status_code == 201, created.text
    assert created.json()["user"]["role"] == "ORG_ADMIN"
    login = client.post("/api/v1/auth/login", json={"email": "new@verify.jp", "password": NEW_PASSWORD})
    assert login.status_code == 200


def test_registration_without_verification_is_rejected(context):
    client = context["client"]
    payload = registration_payload("unverified@verify.jp", "x" * 32)
    assert client.post("/api/v1/organizations/register", json=payload).status_code == 400
    with context["Session"]() as db:
        assert db.scalar(select(models.Organization).where(models.Organization.code == "VERIFY-REG")) is None


def test_registration_token_cannot_be_reused(context):
    client = context["client"]
    code = request_code(client, "reuse@verify.jp", "REGISTRATION").json()["development_code"]
    ticket = verify_code(client, "reuse@verify.jp", "REGISTRATION", code).json()["verification_token"]
    first = registration_payload("reuse@verify.jp", ticket, code="VERIFY-REUSE-1")
    assert client.post("/api/v1/organizations/register", json=first).status_code == 201
    second = registration_payload("reuse@verify.jp", ticket, code="VERIFY-REUSE-2")
    response = client.post("/api/v1/organizations/register", json=second)
    # The account now exists, so the duplicate-email guard answers first; the
    # ticket itself is also already consumed for any other address.
    assert response.status_code == 409
    other = registration_payload("other@verify.jp", ticket, code="VERIFY-REUSE-3")
    assert client.post("/api/v1/organizations/register", json=other).status_code == 400


def test_registration_email_already_registered(context):
    client = context["client"]
    response = request_code(client, "owner@verify.jp", "REGISTRATION")
    assert response.status_code == 409


def test_wrong_code_is_rejected_and_attempts_are_limited(context):
    client = context["client"]
    request_code(client, "guess@verify.jp", "REGISTRATION")
    for _ in range(5):
        assert verify_code(client, "guess@verify.jp", "REGISTRATION", "000000").status_code == 400
    blocked = verify_code(client, "guess@verify.jp", "REGISTRATION", "000000")
    assert blocked.status_code == 429
    # A fresh code resets the attempt counter.
    with context["Session"]() as db:
        row = db.scalars(select(models.EmailVerificationCode).where(models.EmailVerificationCode.email == "guess@verify.jp")).one()
        row.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    assert request_code(client, "guess@verify.jp", "REGISTRATION").status_code == 202


def test_expired_code_is_rejected(context):
    client = context["client"]
    code = request_code(client, "expired@verify.jp", "REGISTRATION").json()["development_code"]
    with context["Session"]() as db:
        row = db.scalars(select(models.EmailVerificationCode).where(models.EmailVerificationCode.email == "expired@verify.jp")).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    response = verify_code(client, "expired@verify.jp", "REGISTRATION", code)
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_code_requests_are_rate_limited_per_address(context):
    client = context["client"]
    assert request_code(client, "fast@verify.jp", "REGISTRATION").status_code == 202
    second = request_code(client, "fast@verify.jp", "REGISTRATION")
    assert second.status_code == 429
    assert "wait" in second.json()["detail"].lower()


def test_password_reset_with_verified_code(context):
    client = context["client"]
    requested = request_code(client, "owner@verify.jp", "PASSWORD_RESET")
    assert requested.status_code == 202
    code = requested.json()["development_code"]
    ticket = verify_code(client, "owner@verify.jp", "PASSWORD_RESET", code).json()["verification_token"]
    changed = client.post("/api/v1/auth/password-reset/confirm", json={"verification_token": ticket, "password": NEW_PASSWORD})
    assert changed.status_code == 200, changed.text
    assert client.post("/api/v1/auth/login", json={"email": "owner@verify.jp", "password": PASSWORD}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "owner@verify.jp", "password": NEW_PASSWORD}).status_code == 200
    # A reset ticket is single use.
    again = client.post("/api/v1/auth/password-reset/confirm", json={"verification_token": ticket, "password": PASSWORD})
    assert again.status_code == 400


def test_password_reset_does_not_reveal_unknown_accounts(context):
    client = context["client"]
    response = request_code(client, "nobody@verify.jp", "PASSWORD_RESET")
    assert response.status_code == 202
    assert "development_code" not in response.json()
    assert "expires_in_seconds" in response.json()
    # Nothing was actually stored or sent for the unknown address.
    with context["Session"]() as db:
        assert db.scalars(select(models.EmailVerificationCode).where(models.EmailVerificationCode.email == "nobody@verify.jp")).all() == []


def test_verification_tickets_are_purpose_specific(context):
    client = context["client"]
    code = request_code(client, "purpose@verify.jp", "REGISTRATION").json()["development_code"]
    ticket = verify_code(client, "purpose@verify.jp", "REGISTRATION", code).json()["verification_token"]
    response = client.post("/api/v1/auth/password-reset/confirm", json={"verification_token": ticket, "password": NEW_PASSWORD})
    assert response.status_code == 400


def test_development_code_is_never_returned_outside_development(context, monkeypatch):
    client = context["client"]
    monkeypatch.setattr(main_module.settings, "environment", "staging")
    response = request_code(client, "staging@verify.jp", "REGISTRATION")
    assert response.status_code == 202
    assert "development_code" not in response.json()


def test_reset_confirm_requires_a_proof(context):
    client = context["client"]
    assert client.post("/api/v1/auth/password-reset/confirm", json={"password": NEW_PASSWORD}).status_code == 422
    both = client.post("/api/v1/auth/password-reset/confirm", json={"token": "t" * 32, "verification_token": "v" * 32, "password": NEW_PASSWORD})
    assert both.status_code == 422
