"""Google sign-in and sign-up: OAuth hand-off, one-time exchange, workspace creation."""
from urllib.parse import parse_qs, urlsplit

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


@pytest.fixture()
def context(monkeypatch):
    monkeypatch.setattr(main_module.settings, "malware_scan_enabled", False)
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "allow_public_registration", True)
    monkeypatch.setattr(main_module.settings, "frontend_base_url", "http://localhost:5173")
    monkeypatch.setattr(main_module.settings, "google_client_id", "google-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(main_module.settings, "google_client_secret", "google-client-secret")
    monkeypatch.setattr(main_module.settings, "google_redirect_uri", "http://127.0.0.1:8000/api/v1/auth/google/callback")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = Session()
    organization = models.Organization(name="Sakura Google", code="SAKURA-GOOGLE", org_type="MANUFACTURER")
    db.add(organization); db.flush()
    db.add(models.User(organization_id=organization.id, email="owner@google.jp", full_name="Google Owner",
                       password_hash=hash_password(PASSWORD), role="ORG_ADMIN"))
    db.add(models.User(organization_id=organization.id, email="inactive@google.jp", full_name="Gone",
                       password_hash=hash_password(PASSWORD), role="OPERATOR", is_active=False))
    db.commit(); db.close()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield {"client": TestClient(app), "Session": Session}
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def google_claims(email: str, name: str = "Google User", sub: str = "google-sub-123"):
    return {"sub": sub, "email": email, "email_verified": True, "name": name}


def start_flow(client):
    response = client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return query["state"][0]


def callback(client, claims, monkeypatch, state=None, code="google-code"):
    monkeypatch.setattr(main_module, "exchange_google_code", lambda raw, redirect_uri: claims)
    state = state or start_flow(client)
    response = client.get(
        "/api/v1/auth/google/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = urlsplit(response.headers["location"])
    return parse_qs(location.query)


def test_start_requires_server_configuration(context, monkeypatch):
    monkeypatch.setattr(main_module.settings, "google_client_id", "")
    response = context["client"].get("/api/v1/auth/google/start", follow_redirects=False)
    assert response.status_code == 503


def test_start_redirects_to_google_with_state(context):
    query = parse_qs(urlsplit(context["client"].get(
        "/api/v1/auth/google/start", follow_redirects=False).headers["location"]).query)
    assert query["client_id"][0].endswith(".apps.googleusercontent.com")
    assert query["redirect_uri"][0] == "http://127.0.0.1:8000/api/v1/auth/google/callback"
    assert query["scope"][0] == "openid email profile"
    assert query["state"][0]


def test_callback_rejects_a_forged_state(context, monkeypatch):
    params = callback(context["client"], google_claims("owner@google.jp"), monkeypatch, state="not-a-valid-state")
    assert params["google_error"] == ["google_failed"]


def test_callback_reports_google_failure(context, monkeypatch):
    state = start_flow(context["client"])

    def explode(raw, redirect_uri):
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="Google is unavailable")

    monkeypatch.setattr(main_module, "exchange_google_code", explode)
    response = context["client"].get(
        "/api/v1/auth/google/callback", params={"code": "x", "state": state}, follow_redirects=False)
    assert parse_qs(urlsplit(response.headers["location"]).query)["google_error"] == ["google_failed"]


def test_existing_user_signs_in_with_a_single_use_code(context, monkeypatch):
    params = callback(context["client"], google_claims("owner@google.jp"), monkeypatch)
    handoff = params["google_code"][0]
    first = context["client"].post("/api/v1/auth/google/exchange", json={"code": handoff})
    assert first.status_code == 200
    assert first.json()["user"]["email"] == "owner@google.jp"
    replay = context["client"].post("/api/v1/auth/google/exchange", json={"code": handoff})
    assert replay.status_code == 400


def test_unknown_email_must_create_a_workspace_then_can_sign_in(context, monkeypatch):
    params = callback(context["client"], google_claims("new@google.jp", "New Owner"), monkeypatch)
    exchange = context["client"].post("/api/v1/auth/google/exchange", json={"code": params["google_code"][0]})
    assert exchange.status_code == 200
    body = exchange.json()
    assert body["needs_registration"] is True
    assert body["email"] == "new@google.jp"
    assert "access_token" not in body
    registered = context["client"].post("/api/v1/auth/google/register", json={
        "signup_token": body["signup_token"],
        "organization_name": "Google Works",
        "organization_code": "google-works",
        "organization_type": "MANUFACTURER",
        "owner_name": "New Owner",
        "language": "en",
    })
    assert registered.status_code == 201
    assert registered.json()["user"]["organization_name"] == "Google Works"
    session = context["Session"]()
    user = session.scalar(select(models.User).where(models.User.email == "new@google.jp"))
    assert user.password_hash is None
    assert user.google_sub == "google-sub-123"
    session.close()
    # A Google-only account cannot use the password form until it sets one.
    assert context["client"].post("/api/v1/auth/login", json={
        "email": "new@google.jp", "password": PASSWORD}).status_code == 401
    # The sign-up token is single-use for a fresh workspace.
    replay = context["client"].post("/api/v1/auth/google/register", json={
        "signup_token": body["signup_token"],
        "organization_name": "Second Works",
        "organization_code": "second-works",
        "organization_type": "MANUFACTURER",
        "owner_name": "New Owner",
        "language": "en",
    })
    assert replay.status_code == 409


def test_google_register_rejects_a_taken_organisation_code(context, monkeypatch):
    params = callback(context["client"], google_claims("another@google.jp"), monkeypatch)
    signup = context["client"].post("/api/v1/auth/google/exchange", json={"code": params["google_code"][0]}).json()
    response = context["client"].post("/api/v1/auth/google/register", json={
        "signup_token": signup["signup_token"],
        "organization_name": "Duplicate",
        "organization_code": "SAKURA-GOOGLE",
        "organization_type": "MANUFACTURER",
        "owner_name": "Another",
        "language": "ja",
    })
    assert response.status_code == 409


def test_inactive_account_cannot_sign_in_with_google(context, monkeypatch):
    params = callback(context["client"], google_claims("inactive@google.jp"), monkeypatch)
    assert params["google_error"] == ["account_inactive"]


def test_google_signup_respects_registration_switch(context, monkeypatch):
    params = callback(context["client"], google_claims("closed@google.jp"), monkeypatch)
    signup = context["client"].post("/api/v1/auth/google/exchange", json={"code": params["google_code"][0]}).json()
    monkeypatch.setattr(main_module.settings, "allow_public_registration", False)
    response = context["client"].post("/api/v1/auth/google/register", json={
        "signup_token": signup["signup_token"],
        "organization_name": "Closed Works",
        "organization_code": "closed-works",
        "organization_type": "MANUFACTURER",
        "owner_name": "Closed",
        "language": "ja",
    })
    assert response.status_code == 403
