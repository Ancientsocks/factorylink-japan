"""Render deployment helpers with a migration-owner / runtime-role split.

Commands:
  python -m app.render_deploy prepare        # Render pre-deploy command
  python -m app.render_deploy api            # private FastAPI service
  python -m app.render_deploy worker         # Celery worker service
  python -m app.render_deploy scheduler      # Celery beat service
  python -m app.render_deploy bootstrap-admin # one-time first tenant setup

The Render Blueprint injects OWNER_DATABASE_URL from Render Postgres. This
module uses it only for migrations and runtime-role provisioning. Long-running
services are always started with a derived non-owner DATABASE_URL.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

# Keep aligned with scripts/db/create-runtime-role.sql and the PostgreSQL
# migration's reviewed RUNTIME_UPDATE_COLUMNS. New mutable fields must be
# reviewed and added deliberately here, in SQL bootstrap and regression tests.
RUNTIME_UPDATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "users": ("language", "password_hash", "is_active", "full_name", "role"),
    "refresh_tokens": ("revoked_at", "replaced_by_id"),
    "suppliers": (
        "code", "name", "contact_name", "email", "phone", "prefecture", "status",
        "supplier_organization_id",
    ),
    "purchase_orders": (
        "status", "supplier_note", "received_quantity", "supplier_id", "po_number",
        "item_name", "quantity", "unit", "unit_price", "due_date",
    ),
    "material_batches": ("quantity_on_hand", "quantity_reserved", "status"),
    "production_orders": (
        "status", "reserved_batch_ids", "completed_quantity", "rejected_quantity",
        "order_number", "product_name", "quantity", "due_date", "track_serials",
    ),
    "equipment": ("status", "total_downtime_minutes", "code", "name", "location", "next_maintenance"),
    "maintenance_tasks": (
        "status", "downtime_minutes", "notes", "maintenance_type", "equipment_id", "title", "due_date",
    ),
    "notifications": ("is_read",),
    "auth_action_tokens": ("used_at",),
    "quality_templates": ("is_active", "name", "process_type", "criteria_json"),
    "corrective_actions": (
        "status", "containment_action", "root_cause", "corrective_action",
        "preventive_action", "verification", "owner", "due_date", "updated_at", "closed_at",
    ),
    "finished_product_serials": ("status", "customer_name", "shipment_reference", "shipped_at"),
    "finished_product_batches": ("status",),
}

# Records staff may remove outright. Everything else is deactivated or retired
# so operational history stays attributable.
RUNTIME_DELETE_TABLES: tuple[str, ...] = (
    "suppliers",
    "purchase_orders",
    "production_orders",
    "equipment",
    "maintenance_tasks",
    "attachments",
)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required deployment environment variable {name} is missing.")
    return value


def _sqlalchemy_url(value: str, *, username: str | None = None, password: str | None = None) -> URL:
    url = make_url(value)
    if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise RuntimeError("Render deployment requires a PostgreSQL connection URL.")
    query = dict(url.query)
    query["sslmode"] = "require"
    return url.set(
        drivername="postgresql+psycopg",
        username=username if username is not None else url.username,
        password=password if password is not None else url.password,
        query=query,
    )


def _identifier(connection, value: str) -> str:
    return connection.dialect.identifier_preparer.quote(value)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _validate_runtime_identity(role_row: tuple | None, role_name: str) -> None:
    """Reject runtime logins with cluster-level powers or inherited memberships.

    Render-managed credentials are provisioned outside this application. A
    plain PostgreSQL LOGIN role normally has INHERIT enabled by default, so we
    do not reject INHERIT by itself; we reject every actual role membership,
    which is the source of inherited privileges.
    """
    if role_row is None:
        raise RuntimeError(
            f"Runtime PostgreSQL role {role_name!r} does not exist. Create a separate "
            "Render-managed credential before deploying the services."
        )
    is_superuser, can_create_db, can_create_role, bypass_rls, membership_count = role_row
    unsafe = []
    if is_superuser:
        unsafe.append("SUPERUSER")
    if can_create_db:
        unsafe.append("CREATEDB")
    if can_create_role:
        unsafe.append("CREATEROLE")
    if bypass_rls:
        unsafe.append("BYPASSRLS")
    if membership_count:
        unsafe.append("role membership/inherited privileges")
    if unsafe:
        raise RuntimeError(
            f"Runtime role {role_name!r} has unsafe privileges: {', '.join(unsafe)}. "
            "Use a dedicated restricted database credential."
        )


def _validate_database_pair(owner_url: URL, runtime_url: URL) -> None:
    if not owner_url.username or not owner_url.database:
        raise RuntimeError("OWNER_DATABASE_URL must include a username and database name.")
    if not runtime_url.username or not runtime_url.database:
        raise RuntimeError("RUNTIME_DATABASE_URL must include a username and database name.")
    if runtime_url.username == owner_url.username:
        raise RuntimeError("Runtime and migration-owner database credentials must be different.")
    if (owner_url.host, owner_url.port, owner_url.database) != (
        runtime_url.host, runtime_url.port, runtime_url.database
    ):
        raise RuntimeError("OWNER_DATABASE_URL and RUNTIME_DATABASE_URL must target the same database host and name.")


def _apply_runtime_grants(connection, role_name: str, owner_name: str, database_name: str) -> None:
    q_role = _identifier(connection, role_name)
    q_owner = _identifier(connection, owner_name)
    q_database = _identifier(connection, database_name)
    connection.exec_driver_sql(f"GRANT CONNECT ON DATABASE {q_database} TO {q_role}")
    connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {q_role}")
    connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    connection.exec_driver_sql(f"REVOKE CREATE ON SCHEMA public FROM {q_role}")
    connection.exec_driver_sql(f"REVOKE UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM {q_role}")
    connection.exec_driver_sql(f"GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO {q_role}")

    table_columns = connection.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public'"
    )).all()
    available: dict[str, set[str]] = {}
    for table_name, column_name in table_columns:
        available.setdefault(table_name, set()).add(column_name)

    for table_name, columns in RUNTIME_UPDATE_COLUMNS.items():
        if table_name not in available:
            continue
        allowed_columns = [column for column in columns if column in available[table_name]]
        if not allowed_columns:
            continue
        q_table = _identifier(connection, table_name)
        q_columns = ", ".join(_identifier(connection, column) for column in allowed_columns)
        connection.exec_driver_sql(f"GRANT UPDATE ({q_columns}) ON TABLE public.{q_table} TO {q_role}")

    for table_name in RUNTIME_DELETE_TABLES:
        if table_name not in available:
            continue
        q_table = _identifier(connection, table_name)
        connection.exec_driver_sql(f"GRANT DELETE ON TABLE public.{q_table} TO {q_role}")

    if "alembic_version" in available:
        connection.exec_driver_sql(f"REVOKE INSERT, UPDATE, DELETE ON TABLE public.alembic_version FROM {q_role}")
    connection.exec_driver_sql(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {q_role}")
    # Default privileges apply to tables created later by the migration owner.
    connection.exec_driver_sql(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {q_owner} IN SCHEMA public "
        f"REVOKE UPDATE, DELETE ON TABLES FROM {q_role}"
    )
    connection.exec_driver_sql(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {q_owner} IN SCHEMA public "
        f"GRANT SELECT, INSERT ON TABLES TO {q_role}"
    )
    connection.exec_driver_sql(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {q_owner} IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {q_role}"
    )


def grant_existing_runtime_role(owner_url: URL, runtime_url: URL) -> None:
    """Grant reviewed application permissions to a pre-created managed role.

    Render creates and manages credentials in its dashboard/API. This path
    intentionally does not CREATE/ALTER ROLE and therefore does not require
    CREATEROLE on the migration owner.
    """
    _validate_database_pair(owner_url, runtime_url)
    role_name = runtime_url.username or ""
    owner_name = owner_url.username or ""
    engine = create_engine(owner_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            role_row = connection.execute(text(
                "SELECT r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolbypassrls, "
                "(SELECT count(*) FROM pg_auth_members m WHERE m.member = r.oid) "
                "FROM pg_roles r WHERE r.rolname = :role_name"
            ), {"role_name": role_name}).one_or_none()
            _validate_runtime_identity(tuple(role_row) if role_row is not None else None, role_name)
            _apply_runtime_grants(connection, role_name, owner_name, owner_url.database or "")
    finally:
        engine.dispose()


def bootstrap_runtime_role(owner_url: URL, role_name: str, role_password: str) -> None:
    """Create/update the restricted role for self-managed Postgres (Compose/CI)."""
    owner_name = owner_url.username
    database_name = owner_url.database
    if not owner_name or not database_name:
        raise RuntimeError("OWNER_DATABASE_URL must include its database username and database name.")
    if role_name == owner_name:
        raise RuntimeError("RUNTIME_DB_USER must be different from the Postgres owner account.")
    if len(role_password) < 24:
        raise RuntimeError("RUNTIME_DB_PASSWORD must contain at least 24 characters.")

    engine = create_engine(owner_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            q_role = _identifier(connection, role_name)
            exists = connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role_name)"),
                {"role_name": role_name},
            ).scalar_one()
            role_ddl = (
                f"ALTER ROLE {q_role} WITH LOGIN PASSWORD {_literal(role_password)} "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT"
                if exists else
                f"CREATE ROLE {q_role} LOGIN PASSWORD {_literal(role_password)} "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT"
            )
            connection.exec_driver_sql(role_ddl)
            _apply_runtime_grants(connection, role_name, owner_name, database_name)
    finally:
        engine.dispose()

def prepare() -> None:
    owner_url = _sqlalchemy_url(_required("OWNER_DATABASE_URL"))
    # Render-managed Postgres credentials are provisioned in the Dashboard.
    # Compose/CI may instead supply RUNTIME_DB_USER + RUNTIME_DB_PASSWORD and
    # let this helper create the role because their database owner is admin.
    runtime_url_value = os.environ.get("RUNTIME_DATABASE_URL", "").strip()
    if runtime_url_value:
        runtime_url = _sqlalchemy_url(runtime_url_value)
        _validate_database_pair(owner_url, runtime_url)
        role_name = runtime_url.username or ""
        grant_existing_runtime_role(owner_url, runtime_url)
    else:
        role_name = _required("RUNTIME_DB_USER")
        role_password = _required("RUNTIME_DB_PASSWORD")
        bootstrap_runtime_role(owner_url, role_name, role_password)

    env = os.environ.copy()
    # Alembic needs only the one-shot owner URL as DATABASE_URL. Do not copy
    # duplicate owner/runtime connection strings or role passwords into its
    # environment; the migration process must not become a credential stash.
    env.pop("OWNER_DATABASE_URL", None)
    env.pop("RUNTIME_DATABASE_URL", None)
    env.pop("RUNTIME_DB_PASSWORD", None)
    env["DATABASE_URL"] = owner_url.render_as_string(hide_password=False)
    env["RUNTIME_DB_USER"] = role_name
    env["AUTO_CREATE_SCHEMA"] = "false"
    env["SEED_DEMO_DATA"] = "false"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
    )
    if runtime_url_value:
        grant_existing_runtime_role(owner_url, runtime_url)
    else:
        bootstrap_runtime_role(owner_url, role_name, role_password)
    print("Render database migration and restricted runtime-role provisioning completed.", flush=True)


def use_runtime_database() -> None:
    runtime_value = os.environ.get("RUNTIME_DATABASE_URL", "").strip()
    if runtime_value:
        runtime_url = _sqlalchemy_url(runtime_value)
    else:
        owner = _sqlalchemy_url(_required("OWNER_DATABASE_URL"))
        runtime_user = _required("RUNTIME_DB_USER")
        runtime_password = _required("RUNTIME_DB_PASSWORD")
        runtime_url = _sqlalchemy_url(
            owner.render_as_string(hide_password=False),
            username=runtime_user,
            password=runtime_password,
        )
    os.environ["DATABASE_URL"] = runtime_url.render_as_string(hide_password=False)
    # The long-running API, worker, scheduler and one-time admin command must
    # inherit only the restricted runtime connection, never the migration
    # owner's credentials or duplicate database URLs.
    for secret_name in ("OWNER_DATABASE_URL", "RUNTIME_DATABASE_URL", "RUNTIME_DB_PASSWORD"):
        os.environ.pop(secret_name, None)

def run_service(mode: str) -> None:
    use_runtime_database()
    if mode == "api":
        port = os.environ.get("PORT", "10000")
        command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port, "--proxy-headers"]
    elif mode == "worker":
        command = [sys.executable, "-m", "celery", "-A", "app.celery_app.celery_app", "worker", "--loglevel=INFO", "--concurrency=2"]
    elif mode == "scheduler":
        command = [sys.executable, "-m", "celery", "-A", "app.celery_app.celery_app", "beat", "--loglevel=INFO"]
    else:
        raise RuntimeError(f"Unsupported Render service mode: {mode}")
    os.execv(sys.executable, command)


def bootstrap_admin() -> int:
    use_runtime_database()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from .admin_bootstrap import BootstrapError, create_first_factory_admin

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = Session()
    try:
        print("FactoryLink first factory administrator setup")
        print("Run only once on an empty production database.\n")
        password = __import__("getpass").getpass("Set administrator password (14+ characters): ")
        confirmation = __import__("getpass").getpass("Confirm administrator password: ")
        if password != confirmation:
            print("Passwords do not match.", file=sys.stderr)
            return 2
        details = create_first_factory_admin(
            db,
            organization_name=input("Company name: ").strip(),
            organization_code=input("Company code: ").strip(),
            admin_name=input("Administrator full name: ").strip(),
            admin_email=input("Administrator email: ").strip(),
            password=password,
        )
        print(f"Created workspace {details['organization_code']} with administrator {details['admin_email']}.")
        return 0
    except BootstrapError as exc:
        db.rollback()
        print(f"Bootstrap refused: {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()
        engine.dispose()


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m app.render_deploy {prepare|api|worker|scheduler|bootstrap-admin}", file=sys.stderr)
        return 2
    command = sys.argv[1]
    if command == "prepare":
        prepare()
        return 0
    if command in {"api", "worker", "scheduler"}:
        run_service(command)
        return 0
    if command == "bootstrap-admin":
        return bootstrap_admin()
    print(f"Unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
