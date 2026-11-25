"""Add one-time invitation and password-reset tokens.

The table is intentionally not protected by tenant RLS because the two public
redemption endpoints locate records by a high-entropy token digest before an
interactive user session exists. Queries are always scoped to purpose and the
unique digest; raw tokens are never stored.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import os

revision = "0005_account_lifecycle"
down_revision = "0004_postgresql_tenant_rls"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    # The legacy 0001 migration builds tables from live Base.metadata rather
    # than a frozen historical schema. On a fresh install it may already have
    # created this newer model; on an RC7 upgrade it will be absent.
    if "auth_action_tokens" not in inspector.get_table_names():
        op.create_table(
            "auth_action_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("purpose", sa.String(length=24), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("purpose IN ('PASSWORD_RESET', 'INVITATION')", name="ck_auth_action_token_purpose"),
        )

    indexes = {index["name"] for index in inspect(bind).get_indexes("auth_action_tokens")}
    if "ix_auth_action_tokens_organization_id" not in indexes:
        op.create_index("ix_auth_action_tokens_organization_id", "auth_action_tokens", ["organization_id"])
    if "ix_auth_action_tokens_user_id" not in indexes:
        op.create_index("ix_auth_action_tokens_user_id", "auth_action_tokens", ["user_id"])

    if bind.dialect.name == "postgresql":
        role_name = os.getenv("RUNTIME_DB_USER", "factorylink_app")
        role = bind.dialect.identifier_preparer.quote(role_name)
        role_exists = bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"), {"role_name": role_name}).scalar()
        if role_exists:
            op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE auth_action_tokens TO {role}"))
            op.execute(sa.text(f"GRANT UPDATE (used_at) ON TABLE auth_action_tokens TO {role}"))
            # Password reset and invitation acceptance must update only these two fields.
            op.execute(sa.text(f"GRANT UPDATE (password_hash, is_active) ON TABLE users TO {role}"))
            op.execute(sa.text(f"REVOKE DELETE ON TABLE auth_action_tokens FROM {role}"))


def downgrade():
    bind = op.get_bind()
    if "auth_action_tokens" not in inspect(bind).get_table_names():
        return
    indexes = {index["name"] for index in inspect(bind).get_indexes("auth_action_tokens")}
    for name in ("ix_auth_action_tokens_user_id", "ix_auth_action_tokens_organization_id"):
        if name in indexes:
            op.drop_index(name, table_name="auth_action_tokens")
    op.drop_table("auth_action_tokens")
