"""Grant runtime privileges for the record edit and delete endpoints.

The restricted runtime role was deliberately read/insert-only while records were
immutable. The operations screens now allow editing master data and deleting
records that have no history, so the same reviewed matrix is extended here:
column-level UPDATE for the fields the PATCH endpoints write, and DELETE on the
tables whose records may be removed. Ledger and history tables stay append-only
and the runtime role still cannot drop tables, change the schema or edit audit
history.
"""
import os

from alembic import op
import sqlalchemy as sa

revision = "0014_runtime_edit_delete_grants"
down_revision = "0013_google_signin"
branch_labels = None
depends_on = None

RUNTIME_EDIT_COLUMNS = {
    "suppliers": (
        "code", "name", "contact_name", "email", "phone", "prefecture", "status",
        "supplier_organization_id",
    ),
    "purchase_orders": (
        "supplier_id", "po_number", "item_name", "quantity", "unit", "unit_price", "due_date",
    ),
    "production_orders": ("order_number", "product_name", "quantity", "due_date", "track_serials"),
    "equipment": ("code", "name", "location", "next_maintenance"),
    "maintenance_tasks": ("equipment_id", "title", "due_date"),
    "quality_templates": ("name", "process_type", "criteria_json"),
    "users": ("full_name", "role"),
}

RUNTIME_DELETE_TABLES = (
    "suppliers",
    "purchase_orders",
    "production_orders",
    "equipment",
    "maintenance_tasks",
    "attachments",
)


def _runtime_role(bind) -> str | None:
    role_name = os.getenv("RUNTIME_DB_USER", "factorylink_app")
    exists = bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
        {"role_name": role_name},
    ).scalar()
    return bind.dialect.identifier_preparer.quote(role_name) if exists else None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    role = _runtime_role(bind)
    if not role:
        # The bootstrap step creates the role before the API starts; skip the
        # grants instead of aborting the upgrade when it does not exist yet.
        return
    quote = bind.dialect.identifier_preparer.quote
    inspector = sa.inspect(bind)
    for table, columns in RUNTIME_EDIT_COLUMNS.items():
        if not inspector.has_table(table):
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        granted = [quote(column) for column in columns if column in existing]
        if not granted:
            continue
        op.execute(sa.text(
            f"GRANT UPDATE ({', '.join(granted)}) ON TABLE {quote(table)} TO {role}"
        ))
    for table in RUNTIME_DELETE_TABLES:
        if inspector.has_table(table):
            op.execute(sa.text(f"GRANT DELETE ON TABLE {quote(table)} TO {role}"))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    role = _runtime_role(bind)
    if not role:
        return
    quote = bind.dialect.identifier_preparer.quote
    inspector = sa.inspect(bind)
    for table, columns in RUNTIME_EDIT_COLUMNS.items():
        if not inspector.has_table(table):
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        revoked = [quote(column) for column in columns if column in existing]
        if not revoked:
            continue
        op.execute(sa.text(
            f"REVOKE UPDATE ({', '.join(revoked)}) ON TABLE {quote(table)} FROM {role}"
        ))
    for table in RUNTIME_DELETE_TABLES:
        if inspector.has_table(table):
            op.execute(sa.text(f"REVOKE DELETE ON TABLE {quote(table)} FROM {role}"))
