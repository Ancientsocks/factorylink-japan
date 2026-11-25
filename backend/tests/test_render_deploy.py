from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.engine import make_url

from app import render_deploy


def test_render_managed_runtime_identity_rejects_privileged_roles():
    safe_row = (False, False, False, False, 0)
    render_deploy._validate_runtime_identity(safe_row, "factorylink_app")

    unsafe_cases = [
        ((True, False, False, False, 0), "SUPERUSER"),
        ((False, True, False, False, 0), "CREATEDB"),
        ((False, False, True, False, 0), "CREATEROLE"),
        ((False, False, False, True, 0), "BYPASSRLS"),
        ((False, False, False, False, 1), "role membership"),
    ]
    for row, message in unsafe_cases:
        with pytest.raises(RuntimeError, match=message):
            render_deploy._validate_runtime_identity(row, "factorylink_app")


def test_render_runtime_and_owner_urls_must_be_distinct_credentials_same_database():
    owner = make_url("postgresql://factorylink_owner:secret@db.internal:5432/factorylink")
    runtime = make_url("postgresql://factorylink_app:runtime@db.internal:5432/factorylink")
    render_deploy._validate_database_pair(owner, runtime)

    with pytest.raises(RuntimeError, match="must be different"):
        render_deploy._validate_database_pair(
            owner,
            make_url("postgresql://factorylink_owner:other@db.internal:5432/factorylink"),
        )
    with pytest.raises(RuntimeError, match="same database host and name"):
        render_deploy._validate_database_pair(
            owner,
            make_url("postgresql://factorylink_app:runtime@other.internal:5432/factorylink"),
        )


def test_render_grant_path_never_creates_or_alters_managed_runtime_role(monkeypatch):
    commands: list[str] = []

    class Result:
        def __init__(self, rows=None, one=None):
            self._rows = rows or []
            self._one = one

        def all(self):
            return self._rows

        def one_or_none(self):
            return self._one

    class Connection:
        dialect = SimpleNamespace(
            identifier_preparer=SimpleNamespace(quote=lambda value: f'"{value}"')
        )

        def execute(self, statement, params=None):
            statement_text = str(statement)
            if "FROM pg_roles" in statement_text:
                return Result(one=(False, False, False, False, 0))
            if "information_schema.columns" in statement_text:
                return Result(rows=[
                    ("purchase_orders", "status"),
                    ("purchase_orders", "supplier_note"),
                    ("purchase_orders", "received_quantity"),
                    ("alembic_version", "version_num"),
                ])
            raise AssertionError(f"Unexpected SQL query: {statement_text}")

        def exec_driver_sql(self, statement):
            commands.append(statement)

    class Engine:
        def begin(self):
            class Context:
                def __enter__(self_inner):
                    return Connection()

                def __exit__(self_inner, exc_type, exc, tb):
                    return False
            return Context()

        def dispose(self):
            pass

    monkeypatch.setattr(render_deploy, "create_engine", lambda *args, **kwargs: Engine())
    owner = make_url("postgresql+psycopg://factorylink_owner:owner@db.internal:5432/factorylink")
    runtime = make_url("postgresql+psycopg://factorylink_app:runtime@db.internal:5432/factorylink")
    render_deploy.grant_existing_runtime_role(owner, runtime)

    normalized = "\n".join(commands).upper()
    assert "GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA PUBLIC" in normalized
    assert "REVOKE UPDATE, DELETE ON ALL TABLES IN SCHEMA PUBLIC" in normalized
    assert "GRANT UPDATE (\"STATUS\", \"SUPPLIER_NOTE\", \"RECEIVED_QUANTITY\")" in normalized
    assert "REVOKE INSERT, UPDATE, DELETE ON TABLE PUBLIC.ALEMBIC_VERSION" in normalized
    assert "CREATE ROLE" not in normalized
    assert "ALTER ROLE" not in normalized


def test_render_grants_preserve_all_reviewed_maintenance_task_columns():
    assert render_deploy.RUNTIME_UPDATE_COLUMNS["maintenance_tasks"] == (
        "status", "downtime_minutes", "notes", "maintenance_type", "equipment_id", "title", "due_date",
    )
    assert render_deploy.RUNTIME_UPDATE_COLUMNS["finished_product_batches"] == ("status",)


def test_render_grants_allow_record_edits_and_deletes_only_where_reviewed():
    assert render_deploy.RUNTIME_DELETE_TABLES == (
        "suppliers", "purchase_orders", "production_orders", "equipment", "maintenance_tasks", "attachments",
    )
    # Ledger, audit and inspection history must never be deletable through the API role.
    for table in ("audit_logs", "inventory_movements", "traceability_events", "quality_inspections"):
        assert table not in render_deploy.RUNTIME_DELETE_TABLES
        assert table not in render_deploy.RUNTIME_UPDATE_COLUMNS
    assert render_deploy.RUNTIME_UPDATE_COLUMNS["suppliers"][:3] == ("code", "name", "contact_name")


def test_render_use_runtime_database_prefers_managed_runtime_url(monkeypatch):
    import os

    monkeypatch.setenv(
        "RUNTIME_DATABASE_URL",
        "postgresql://factorylink_app:p%40ss@db.internal:5432/factorylink",
    )
    monkeypatch.setenv("OWNER_DATABASE_URL", "postgresql://factorylink_owner:owner-secret@db.internal:5432/factorylink")
    monkeypatch.setenv("RUNTIME_DB_PASSWORD", "unused-fallback-secret")
    render_deploy.use_runtime_database()
    runtime = make_url(os.environ["DATABASE_URL"])
    assert runtime.username == "factorylink_app"
    assert runtime.password == "p@ss"
    assert runtime.drivername == "postgresql+psycopg"
    assert runtime.query["sslmode"] == "require"
    assert "OWNER_DATABASE_URL" not in os.environ
    assert "RUNTIME_DATABASE_URL" not in os.environ
    assert "RUNTIME_DB_PASSWORD" not in os.environ
