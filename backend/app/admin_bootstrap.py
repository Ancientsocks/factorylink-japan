"""One-time, operator-only bootstrap for the first FactoryLink factory tenant.

This module deliberately exposes no HTTP route and accepts no default
credentials. Run it from an authenticated deployment shell after migrations,
with the restricted runtime database URL configured.
"""
from __future__ import annotations

import getpass
import re
import sys
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import AuditLog, Organization, User
from .security import hash_password
from .database import set_request_context, set_tenant_context


class BootstrapError(RuntimeError):
    """Raised when the one-time first-administrator bootstrap is unsafe."""


def _acquire_first_admin_lock(db: Session) -> None:
    """Serialize first-tenant bootstrap across operator processes on PostgreSQL."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :resource)"),
            {"namespace": 7142026, "resource": 1},
        )


def create_first_factory_admin(
    db: Session,
    *,
    organization_name: str,
    organization_code: str,
    admin_email: str,
    admin_name: str,
    password: str,
) -> dict[str, Any]:
    """Create the first manufacturer tenant and its administrator atomically.

    Refuses to run if any tenant or user already exists. This is intentionally
    a first-install operation, not a general user-provisioning API.
    """
    # Prevent two operator shells from concurrently creating separate first
    # tenants. The lock is transaction-scoped and released automatically on
    # commit/rollback; SQLite tests keep their lightweight single-process path.
    _acquire_first_admin_lock(db)

    org_name = organization_name.strip()
    org_code = organization_code.strip().upper()
    email = admin_email.strip().lower()
    full_name = admin_name.strip()

    if not org_name or len(org_name) > 180:
        raise BootstrapError("Company name must contain 1–180 characters.")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{2,39}", org_code):
        raise BootstrapError("Company code must be 3–40 uppercase letters, numbers or hyphens.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 255:
        raise BootstrapError("Enter a valid administrator email address.")
    if not full_name or len(full_name) > 140:
        raise BootstrapError("Administrator name must contain 1–140 characters.")
    if len(password) < 14 or len(password) > 128:
        raise BootstrapError("Administrator password must contain 14–128 characters.")
    if password.lower() in {email, "factorylink2026!", "password123456"}:
        raise BootstrapError("Choose a unique password; common/demo passwords are not accepted.")

    set_request_context(db, "app.organization_provisioning", "on")
    existing_organizations = db.scalar(select(func.count()).select_from(Organization)) or 0
    existing_users = db.scalar(select(func.count()).select_from(User)) or 0
    if existing_organizations or existing_users:
        raise BootstrapError(
            "First-administrator bootstrap is allowed only on an empty database. "
            "Use an organisation invitation for subsequent users."
        )

    organization = Organization(
        name=org_name,
        code=org_code,
        org_type="MANUFACTURER",
        timezone="Asia/Tokyo",
        currency="JPY",
        postal_code="",
        prefecture="",
        address="",
    )
    db.add(organization)
    db.flush()

    # The audit table is tenant-RLS protected in PostgreSQL. Bind the tenant
    # before inserting the administrator and audit record in this transaction.
    set_tenant_context(db, organization.id)
    user = User(
        organization_id=organization.id,
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        role="ORG_ADMIN",
        language="ja",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(AuditLog(
        organization_id=organization.id,
        user_id=user.id,
        action="FIRST_ADMIN_BOOTSTRAP",
        entity_type="Organization",
        entity_id=str(organization.id),
        payload='{"source":"operator_cli"}',
    ))
    db.commit()
    return {
        "organization_id": organization.id,
        "organization_code": organization.code,
        "admin_user_id": user.id,
        "admin_email": user.email,
        "role": user.role,
    }


def main() -> int:
    """Interactive command-line entry point; password input is not echoed."""
    from .config import settings
    from .database import SessionLocal

    if settings.environment.lower() == "production" and settings.allow_public_registration:
        print("Refusing bootstrap: production public registration must be disabled.", file=sys.stderr)
        return 2

    print("FactoryLink first factory administrator setup")
    print("This creates the first manufacturer workspace. It cannot be used after any tenant exists.\n")
    name = input("Company name: ").strip()
    code = input("Company code (uppercase letters/numbers/hyphens): ").strip()
    admin_name = input("Administrator full name: ").strip()
    email = input("Administrator email: ").strip()
    password = getpass.getpass("Set administrator password (14+ characters): ")
    confirmation = getpass.getpass("Confirm administrator password: ")
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        created = create_first_factory_admin(
            db,
            organization_name=name,
            organization_code=code,
            admin_email=email,
            admin_name=admin_name,
            password=password,
        )
    except BootstrapError as exc:
        db.rollback()
        print(f"Bootstrap refused: {exc}", file=sys.stderr)
        return 2
    except Exception:
        db.rollback()
        print("Bootstrap failed. No credentials were printed; inspect restricted deployment logs.", file=sys.stderr)
        raise
    finally:
        db.close()

    print("\nFirst factory administrator created successfully.")
    print(f"Workspace code: {created['organization_code']}")
    print(f"Administrator: {created['admin_email']}")
    print("Sign in through the application and invite additional users from User Management.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
