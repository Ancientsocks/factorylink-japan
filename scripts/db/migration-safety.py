#!/usr/bin/env python3
"""Exercise clean, predecessor, and failed/retried PostgreSQL migrations."""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PREDECESSOR = "0009_finished_product_quality"
EXPECTED_HEAD = "0011_inventory_reconciliation"
DATABASE_PREFIX = "factorylink_migration_safety_"


def _psycopg_url(url: str, database: str | None = None) -> str:
    parsed = make_url(url).set(drivername="postgresql")
    if database is not None:
        parsed = parsed.set(database=database)
    return parsed.render_as_string(hide_password=False)


def _alembic(database_url: str, revision: str, runtime_role: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment["RUNTIME_DB_USER"] = runtime_role
    environment["PYTHONPATH"] = str(BACKEND)
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _expect_migration(database_url: str, revision: str, runtime_role: str) -> None:
    result = _alembic(database_url, revision, runtime_role)
    if result.returncode:
        raise RuntimeError(
            f"Alembic upgrade to {revision} failed:\n{result.stdout}\n{result.stderr}"
        )


def _current_revision(database_url: str) -> str:
    with psycopg.connect(_psycopg_url(database_url)) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    if row is None:
        raise RuntimeError("The scratch database has no Alembic revision.")
    return row[0]


def _create_database(admin_url: str, name: str) -> None:
    with psycopg.connect(_psycopg_url(admin_url), autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def _drop_database(admin_url: str, name: str) -> None:
    if not name.startswith(DATABASE_PREFIX):
        raise RuntimeError("Refusing to drop a database outside the migration-test namespace.")
    with psycopg.connect(_psycopg_url(admin_url), autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )


def _assert_data_and_integrity(database_url: str, marker: str) -> None:
    with psycopg.connect(_psycopg_url(database_url)) as connection:
        connection.execute("SELECT set_config('app.organization_provisioning', 'on', true)")
        row = connection.execute(
            "SELECT name FROM organizations WHERE code = %s",
            (marker,),
        ).fetchone()
        if row != ("Migration Safety Fixture",):
            raise RuntimeError("The predecessor organization record did not survive migration.")
        reconciliation_policy = connection.execute(
            """
            SELECT c.relrowsecurity AND c.relforcerowsecurity
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'inventory_reconciliations'
            """
        ).fetchone()
        if reconciliation_policy != (True,):
            raise RuntimeError("Inventory reconciliation RLS is not enabled and forced.")
        index_exists = connection.execute(
            "SELECT to_regclass('public.uq_inventory_reconciliation_open_batch') IS NOT NULL"
        ).fetchone()
        if index_exists != (True,):
            raise RuntimeError("The open-reconciliation uniqueness index is missing.")
        constraint_exists = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'public.inventory_reconciliations'::regclass
                  AND conname = 'ck_inventory_reconciliation_status'
            )
            """
        ).fetchone()
        if constraint_exists != (True,):
            raise RuntimeError("The reconciliation status constraint is missing.")


def main() -> None:
    admin_url = os.environ.get("DATABASE_URL", "")
    runtime_role = os.environ.get("RUNTIME_DB_USER", "factorylink_app")
    if not admin_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise SystemExit("Set DATABASE_URL to a PostgreSQL migration-owner URL.")
    if not runtime_role or len(runtime_role) > 63:
        raise SystemExit("Set RUNTIME_DB_USER to the configured PostgreSQL runtime role.")

    suffix = secrets.token_hex(6)
    clean_name = f"{DATABASE_PREFIX}{suffix}_clean"
    recovery_name = f"{DATABASE_PREFIX}{suffix}_recovery"
    created: list[str] = []
    try:
        for name in (clean_name, recovery_name):
            _create_database(admin_url, name)
            created.append(name)

        clean_url = make_url(admin_url).set(database=clean_name).render_as_string(hide_password=False)
        _expect_migration(clean_url, "head", runtime_role)
        if _current_revision(clean_url) != EXPECTED_HEAD:
            raise RuntimeError("The empty-database migration did not reach the expected head.")

        recovery_url = make_url(admin_url).set(database=recovery_name).render_as_string(hide_password=False)
        _expect_migration(recovery_url, PREDECESSOR, runtime_role)
        marker = f"MIGRATION-{suffix.upper()}"
        with psycopg.connect(_psycopg_url(recovery_url)) as connection:
            connection.execute(
                """
                INSERT INTO organizations
                    (name, code, org_type, postal_code, prefecture, address, timezone, currency, created_at)
                VALUES
                    ('Migration Safety Fixture', %s, 'MANUFACTURER', '', '', '', 'Asia/Tokyo', 'JPY', now())
                """,
                (marker,),
            )

        _expect_migration(recovery_url, "0010_identity_rls", runtime_role)
        missing_role = f"factorylink_no_such_role_{suffix}"
        failed = _alembic(recovery_url, "head", missing_role)
        if failed.returncode == 0:
            raise RuntimeError("The intentional migration privilege failure unexpectedly succeeded.")
        if missing_role not in failed.stdout + failed.stderr:
            raise RuntimeError("The migration failed for a reason other than the controlled missing-role check.")
        if _current_revision(recovery_url) != "0010_identity_rls":
            raise RuntimeError("Failed migration did not preserve the previous Alembic revision.")

        with psycopg.connect(_psycopg_url(recovery_url)) as connection:
            enabled = connection.execute(
                """
                SELECT relrowsecurity
                FROM pg_class
                WHERE oid = 'public.inventory_reconciliations'::regclass
                """
            ).fetchone()
        if enabled != (False,):
            raise RuntimeError("Failed migration left partial reconciliation RLS changes behind.")

        _expect_migration(recovery_url, "head", runtime_role)
        if _current_revision(recovery_url) != EXPECTED_HEAD:
            raise RuntimeError("Migration retry did not recover to the expected head.")
        _assert_data_and_integrity(recovery_url, marker)
        print(
            "PostgreSQL migration safety passed: empty upgrade, populated 0009 upgrade, "
            "failed 0011 rollback, successful retry, data preservation, RLS, index and constraint."
        )
    finally:
        for name in reversed(created):
            _drop_database(admin_url, name)


if __name__ == "__main__":
    main()
