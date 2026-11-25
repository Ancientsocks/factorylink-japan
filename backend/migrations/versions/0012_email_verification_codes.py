"""Add short-lived email verification codes for sign-up and password reset.

`0001_initial` creates the current model metadata, so a brand-new database can
already contain this table. Creation and indexing are guarded so fresh installs
and existing databases both migrate cleanly.
"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0012_email_verification_codes"
down_revision = "0011_inventory_reconciliation"
branch_labels = None
depends_on = None


def _index_names(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("email_verification_codes"):
        op.create_table(
            "email_verification_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("purpose", sa.String(length=24), nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("verification_token_hash", sa.String(length=64), nullable=True, unique=True),
            sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("purpose IN ('REGISTRATION', 'PASSWORD_RESET')", name="ck_email_verification_purpose"),
            sa.CheckConstraint("attempts >= 0", name="ck_email_verification_attempts"),
        )
    index_names = _index_names(sa.inspect(bind), "email_verification_codes")
    if "ix_email_verification_codes_email" not in index_names:
        op.create_index("ix_email_verification_codes_email", "email_verification_codes", ["email"])
    if "ix_email_verification_codes_verification_token_hash" not in index_names:
        op.create_index(
            "ix_email_verification_codes_verification_token_hash",
            "email_verification_codes",
            ["verification_token_hash"],
        )
    if bind.dialect.name == "postgresql":
        # Pre-authentication table: no tenant RLS policy, only runtime DML grants.
        runtime_role = os.getenv("RUNTIME_DB_USER", "factorylink_app")
        role_exists = bind.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
            {"role_name": runtime_role},
        ).scalar()
        if not role_exists:
            return
        role = bind.dialect.identifier_preparer.quote(runtime_role)
        table = bind.dialect.identifier_preparer.quote("email_verification_codes")
        sequence = bind.dialect.identifier_preparer.quote("email_verification_codes_id_seq")
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {role}"))
        op.execute(sa.text(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {role}"))


def downgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("email_verification_codes"):
        return
    index_names = _index_names(sa.inspect(bind), "email_verification_codes")
    if "ix_email_verification_codes_verification_token_hash" in index_names:
        op.drop_index("ix_email_verification_codes_verification_token_hash", table_name="email_verification_codes")
    if "ix_email_verification_codes_email" in index_names:
        op.drop_index("ix_email_verification_codes_email", table_name="email_verification_codes")
    op.drop_table("email_verification_codes")
