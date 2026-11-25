"""Link received material batches to purchase orders.

The initial migration in the first local release built tables from SQLAlchemy
metadata. This upgrade is conditional so it works both for an RC3 database
(which needs the new column) and a fresh database where the updated metadata
already created it during 0001.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_po_receipt_link"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "fk_material_batches_purchase_order_id_purchase_orders"
INDEX_NAME = "ix_material_batches_purchase_order_id"


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("material_batches")}
    if "purchase_order_id" not in columns:
        op.add_column(
            "material_batches",
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
        )
    inspector = inspect(bind)
    foreign_keys = {fk.get("name") for fk in inspector.get_foreign_keys("material_batches")}
    if CONSTRAINT_NAME not in foreign_keys:
        if bind.dialect.name == "sqlite":
            # SQLite cannot ALTER TABLE to add a FK; Alembic recreates the table safely.
            with op.batch_alter_table("material_batches", recreate="always") as batch_op:
                batch_op.create_foreign_key(
                    CONSTRAINT_NAME,
                    "purchase_orders",
                    ["purchase_order_id"],
                    ["id"],
                )
        else:
            op.create_foreign_key(
                CONSTRAINT_NAME,
                "material_batches",
                "purchase_orders",
                ["purchase_order_id"],
                ["id"],
            )
    indexes = {index["name"] for index in inspect(bind).get_indexes("material_batches")}
    if INDEX_NAME not in indexes:
        op.create_index(INDEX_NAME, "material_batches", ["purchase_order_id"])


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("material_batches")}
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name="material_batches")
    foreign_keys = {fk.get("name") for fk in inspect(bind).get_foreign_keys("material_batches")}
    columns = {column["name"] for column in inspect(bind).get_columns("material_batches")}
    if bind.dialect.name == "sqlite" and (CONSTRAINT_NAME in foreign_keys or "purchase_order_id" in columns):
        with op.batch_alter_table("material_batches", recreate="always") as batch_op:
            if CONSTRAINT_NAME in foreign_keys:
                batch_op.drop_constraint(CONSTRAINT_NAME, type_="foreignkey")
            if "purchase_order_id" in columns:
                batch_op.drop_column("purchase_order_id")
    else:
        if CONSTRAINT_NAME in foreign_keys:
            op.drop_constraint(CONSTRAINT_NAME, "material_batches", type_="foreignkey")
        if "purchase_order_id" in columns:
            op.drop_column("material_batches", "purchase_order_id")
