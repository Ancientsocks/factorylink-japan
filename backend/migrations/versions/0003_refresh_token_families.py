"""Track refresh token families and revoke descendants on replay.

Legacy refresh-token chains are grouped by walking replaced_by_id links from
roots. Independent legacy tokens are assigned distinct families.
"""
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_refresh_token_families"
down_revision = "0002_po_receipt_link"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_refresh_tokens_family_id"


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("refresh_tokens")}
    if "family_id" not in columns:
        op.add_column("refresh_tokens", sa.Column("family_id", sa.String(length=36), nullable=True))

    rows = bind.execute(sa.text("SELECT id, replaced_by_id FROM refresh_tokens ORDER BY id")).all()
    ids = {int(row.id) for row in rows}
    successor = {int(row.id): int(row.replaced_by_id) for row in rows if row.replaced_by_id is not None}
    referenced = set(successor.values())
    roots = sorted(ids - referenced)
    assigned = set()

    # Every chain starts at a token which has no predecessor. Bound traversal
    # with `assigned` so malformed legacy links cannot loop indefinitely.
    for root in roots:
        family = str(uuid4())
        current = root
        while current in ids and current not in assigned:
            assigned.add(current)
            bind.execute(
                sa.text("UPDATE refresh_tokens SET family_id = :family WHERE id = :id"),
                {"family": family, "id": current},
            )
            current = successor.get(current)
            if current is None:
                break

    # Any orphan or malformed cycle receives its own family, preserving safety.
    for token_id in sorted(ids - assigned):
        bind.execute(
            sa.text("UPDATE refresh_tokens SET family_id = :family WHERE id = :id"),
            {"family": str(uuid4()), "id": token_id},
        )

    inspector = inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("refresh_tokens")}
    if columns["family_id"].get("nullable", True):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("refresh_tokens", recreate="always") as batch:
                batch.alter_column("family_id", existing_type=sa.String(length=36), nullable=False)
        else:
            op.alter_column("refresh_tokens", "family_id", existing_type=sa.String(length=36), nullable=False)
    indexes = {index["name"] for index in inspect(bind).get_indexes("refresh_tokens")}
    if INDEX_NAME not in indexes:
        op.create_index(INDEX_NAME, "refresh_tokens", ["family_id"])


def downgrade():
    bind = op.get_bind()
    indexes = {index["name"] for index in inspect(bind).get_indexes("refresh_tokens")}
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name="refresh_tokens")
    columns = {column["name"] for column in inspect(bind).get_columns("refresh_tokens")}
    if "family_id" in columns:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("refresh_tokens", recreate="always") as batch:
                batch.drop_column("family_id")
        else:
            op.drop_column("refresh_tokens", "family_id")
