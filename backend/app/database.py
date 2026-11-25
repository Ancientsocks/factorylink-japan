"""Database access with lazy engine construction.

Keeping engine creation lazy allows API modules and SQLite tests to import the
application without requiring the PostgreSQL driver until a real DB connection
is requested. Production uses PostgreSQL through DATABASE_URL.
"""
from functools import lru_cache
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session as SASession, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine():
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)


@event.listens_for(SASession, "after_begin")
def _apply_tenant_context_after_begin(session, transaction, connection):
    """Reapply tenant scope for every transaction in an authenticated request.

    PostgreSQL SET LOCAL is transaction-scoped. API handlers may commit and
    continue querying in the same request, so the tenant id is kept in the
    Session.info dictionary and reapplied whenever SQLAlchemy starts a new
    outer transaction. SQLite intentionally skips the PostgreSQL-only GUC.
    """
    tenant_org_id = session.info.get("tenant_org_id")
    if tenant_org_id is not None and connection.dialect.name == "postgresql" and not transaction.nested:
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, true)"),
            {"org_id": str(int(tenant_org_id))},
        )


def set_tenant_context(db: SASession, organization_id: int) -> None:
    """Bind this request/session to one tenant for PostgreSQL RLS policies."""
    db.info["tenant_org_id"] = int(organization_id)
    if db.get_bind().dialect.name == "postgresql":
        # This also starts the transaction and triggers after_begin. The
        # explicit call makes the intent clear if an existing transaction was
        # opened before the tenant was resolved.
        db.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, true)"),
            {"org_id": str(int(organization_id))},
        )


def set_request_context(db: SASession, name: str, value: str) -> None:
    """Set a narrowly scoped transaction-local context used by RLS policies."""
    allowed = {
        "app.auth_email",
        "app.auth_user_id",
        "app.auth_refresh_token_hash",
        "app.auth_action_token_hash",
        "app.organization_provisioning",
        "app.supplier_organization_code",
        "app.system_job",
    }
    if name not in allowed:
        raise ValueError("Unsupported database request context.")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT set_config(:setting_name, :setting_value, true)"),
            {"setting_name": name, "setting_value": str(value)},
        )


def set_system_job_context(db: SASession, job_name: str) -> None:
    if job_name != "maintenance-reminders":
        raise ValueError("Unsupported database system job.")
    set_request_context(db, "app.system_job", job_name)


def SessionLocal():
    """Create a fresh session bound to the configured engine."""
    factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)
    return factory()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
