from __future__ import annotations

from types import SimpleNamespace

from app.admin_bootstrap import _acquire_first_admin_lock


def test_postgres_first_admin_bootstrap_uses_transaction_advisory_lock():
    captured = []

    class FakeSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement, params):
            captured.append((str(statement), params))

    _acquire_first_admin_lock(FakeSession())

    assert len(captured) == 1
    sql, params = captured[0]
    assert "pg_advisory_xact_lock" in sql
    assert params == {"namespace": 7142026, "resource": 1}


def test_non_postgres_first_admin_bootstrap_skips_postgres_lock():
    class FakeSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        def execute(self, *_args, **_kwargs):
            raise AssertionError("SQLite must not execute PostgreSQL-only advisory SQL")

    _acquire_first_admin_lock(FakeSession())
