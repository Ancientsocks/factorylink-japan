"""Add Google sign-in support (optional password, Google subject, hand-off codes).

`0001_initial` creates the current model metadata, so a brand-new database can
already contain these objects. Every step is guarded so both fresh installs and
existing databases migrate cleanly.
"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0013_google_signin"
down_revision = "0012_email_verification_codes"
branch_labels = None
depends_on = None


def _index_names(inspector, table: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}

    with op.batch_alter_table("users") as batch:
        password_hash = next(
            column for column in inspector.get_columns("users") if column["name"] == "password_hash"
        )
        if not password_hash["nullable"]:
            batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=True)
        if "google_sub" not in user_columns:
            batch.add_column(sa.Column("google_sub", sa.String(length=64), nullable=True))
    if "ix_users_google_sub" not in _index_names(sa.inspect(bind), "users"):
        op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)

    if not sa.inspect(bind).has_table("oauth_login_codes"):
        op.create_table(
            "oauth_login_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("purpose", sa.String(length=16), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=140), nullable=False, server_default=""),
            sa.Column("google_sub", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("purpose IN ('SIGNIN', 'SIGNUP')", name="ck_oauth_login_purpose"),
        )
    if "ix_oauth_login_codes_code_hash" not in _index_names(sa.inspect(bind), "oauth_login_codes"):
        op.create_index("ix_oauth_login_codes_code_hash", "oauth_login_codes", ["code_hash"], unique=True)
    if bind.dialect.name == "postgresql":
        runtime_role = os.getenv("RUNTIME_DB_USER", "factorylink_app")
        role_exists = bind.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
            {"role_name": runtime_role},
        ).scalar()
        if not role_exists:
            return
        role = bind.dialect.identifier_preparer.quote(runtime_role)
        table = bind.dialect.identifier_preparer.quote("oauth_login_codes")
        sequence = bind.dialect.identifier_preparer.quote("oauth_login_codes_id_seq")
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO {role}"))
        op.execute(sa.text(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {role}"))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("oauth_login_codes"):
        if "ix_oauth_login_codes_code_hash" in _index_names(inspector, "oauth_login_codes"):
            op.drop_index("ix_oauth_login_codes_code_hash", table_name="oauth_login_codes")
        op.drop_table("oauth_login_codes")
    if "ix_users_google_sub" in _index_names(sa.inspect(bind), "users"):
        op.drop_index("ix_users_google_sub", table_name="users")
    if "google_sub" in {column["name"] for column in sa.inspect(bind).get_columns("users")}:
        with op.batch_alter_table("users") as batch:
            batch.drop_column("google_sub")
