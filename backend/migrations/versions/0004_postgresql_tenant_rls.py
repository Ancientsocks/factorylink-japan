"""Add PostgreSQL row-level security to tenant-owned operational tables.

The API sets transaction-local app.current_organization_id from a signed access
JWT. Supplier users may read the supplier records and purchase orders that are
explicitly linked to their supplier organisation. They may update only linked
purchase-order rows (the application still restricts editable fields), upload
attachments against linked purchase orders, and receive notifications for a
linked relationship. SQLite keeps application-level scoping for local tests.
"""
import os

from alembic import op
import sqlalchemy as sa

revision = "0004_postgresql_tenant_rls"
down_revision = "0003_refresh_token_families"
branch_labels = None
depends_on = None

ORG = "NULLIF(current_setting('app.current_organization_id', true), '')::bigint"
TENANT_TABLES = (
    "material_batches",
    "inventory_movements",
    "production_orders",
    "quality_inspections",
    "equipment",
    "maintenance_tasks",
    "traceability_events",
    "audit_logs",
)
SPECIAL_POLICY_TABLES = {"suppliers", "purchase_orders", "notifications", "attachments"}
APPLICATION_TABLES = (
    "organizations", "users", "refresh_tokens", "suppliers", "purchase_orders",
    *TENANT_TABLES, "notifications", "attachments",
)
RUNTIME_UPDATE_COLUMNS = {
    "users": ("language",),
    "refresh_tokens": ("revoked_at", "replaced_by_id"),
    "purchase_orders": ("status", "supplier_note"),
    "material_batches": ("quantity_on_hand", "quantity_reserved", "status"),
    "production_orders": ("status", "reserved_batch_ids", "completed_quantity", "rejected_quantity"),
    "equipment": ("status", "total_downtime_minutes"),
    "maintenance_tasks": ("status", "downtime_minutes", "notes"),
    "notifications": ("is_read",),
}


def _execute(sql: str) -> None:
    op.execute(sa.text(sql))


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite is supported for fast unit tests and local lightweight checks.
        # Production Compose uses PostgreSQL and executes the policies below.
        return

    # Tables whose only data owner is their organisation.
    for table in TENANT_TABLES:
        _execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        _execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        _execute(
            f'''CREATE POLICY "{table}_tenant_isolation" ON "{table}"
                USING (organization_id = {ORG})
                WITH CHECK (organization_id = {ORG})'''
        )

    # Manufacturers own supplier directory records. A linked supplier account
    # can read only the particular supplier records addressed to its tenant.
    _execute('ALTER TABLE "suppliers" ENABLE ROW LEVEL SECURITY')
    _execute('ALTER TABLE "suppliers" FORCE ROW LEVEL SECURITY')
    _execute(
        f'''CREATE POLICY suppliers_owner_all ON suppliers FOR ALL
            USING (organization_id = {ORG})
            WITH CHECK (organization_id = {ORG})'''
    )
    _execute(
        f'''CREATE POLICY suppliers_linked_supplier_read ON suppliers FOR SELECT
            USING (supplier_organization_id = {ORG})'''
    )

    # A supplier may see its explicitly shared purchase orders and update the
    # supplier workflow state. API code limits those updates to status/note.
    _execute('ALTER TABLE "purchase_orders" ENABLE ROW LEVEL SECURITY')
    _execute('ALTER TABLE "purchase_orders" FORCE ROW LEVEL SECURITY')
    _execute(
        f'''CREATE POLICY purchase_orders_factory_all ON purchase_orders FOR ALL
            USING (organization_id = {ORG})
            WITH CHECK (organization_id = {ORG})'''
    )
    supplier_link = (
        "supplier_id IN (SELECT s.id FROM suppliers AS s "
        f"WHERE s.supplier_organization_id = {ORG} "
        "AND s.organization_id = purchase_orders.organization_id)"
    )
    _execute(
        f'''CREATE POLICY purchase_orders_supplier_read ON purchase_orders FOR SELECT
            USING ({supplier_link})'''
    )
    _execute(
        f'''CREATE POLICY purchase_orders_supplier_update ON purchase_orders FOR UPDATE
            USING ({supplier_link})
            WITH CHECK ({supplier_link})'''
    )

    # Notifications normally belong to their tenant. A linked supplier and a
    # manufacturer may enqueue a notification for the other party only through
    # an existing supplier relationship. Reading remains own-tenant only.
    _execute('ALTER TABLE "notifications" ENABLE ROW LEVEL SECURITY')
    _execute('ALTER TABLE "notifications" FORCE ROW LEVEL SECURITY')
    _execute(
        f'''CREATE POLICY notifications_tenant_select ON notifications
            FOR SELECT USING (organization_id = {ORG})'''
    )
    _execute(
        f'''CREATE POLICY notifications_tenant_update ON notifications FOR UPDATE
            USING (organization_id = {ORG})
            WITH CHECK (organization_id = {ORG})'''
    )
    _execute(
        f'''CREATE POLICY notifications_related_insert ON notifications FOR INSERT
            WITH CHECK (
                organization_id = {ORG}
                OR organization_id IN (
                    SELECT s.supplier_organization_id FROM suppliers AS s
                    WHERE s.organization_id = {ORG} AND s.supplier_organization_id IS NOT NULL
                )
                OR organization_id IN (
                    SELECT s.organization_id FROM suppliers AS s
                    WHERE s.supplier_organization_id = {ORG}
                )
            )'''
    )

    # Factory users own attachments for their organisation. Supplier users can
    # see and upload only files attached to a purchase order shared with them.
    _execute('ALTER TABLE "attachments" ENABLE ROW LEVEL SECURITY')
    _execute('ALTER TABLE "attachments" FORCE ROW LEVEL SECURITY')
    _execute(
        f'''CREATE POLICY attachments_factory_all ON attachments FOR ALL
            USING (organization_id = {ORG})
            WITH CHECK (organization_id = {ORG})'''
    )
    _execute(
        f'''CREATE POLICY attachments_supplier_read ON attachments FOR SELECT
            USING (
                supplier_id IN (
                    SELECT s.id FROM suppliers AS s
                    WHERE s.supplier_organization_id = {ORG}
                )
            )'''
    )
    _execute(
        f'''CREATE POLICY attachments_supplier_insert ON attachments FOR INSERT
            WITH CHECK (
                purchase_order_id IS NOT NULL
                AND supplier_id IN (
                    SELECT s.id FROM suppliers AS s
                    WHERE s.supplier_organization_id = {ORG}
                )
                AND purchase_order_id IN (
                    SELECT p.id FROM purchase_orders AS p
                    WHERE p.supplier_id = attachments.supplier_id
                      AND p.organization_id = attachments.organization_id
                )
            )'''
    )

    # Runtime API credentials are not schema owners. Keep them read-only on
    # Alembic's bookkeeping table even though future-table DML is granted by
    # default privileges for ordinary application tables.
    runtime_role = os.getenv("RUNTIME_DB_USER", "factorylink_app")
    role_exists = bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
        {"role_name": runtime_role},
    ).scalar()
    if role_exists:
        quoted_role = bind.dialect.identifier_preparer.quote(runtime_role)
        # Start from the broad bootstrap DML grant, then reduce writes to the
        # operations the API actually performs. Event/ledger tables stay append
        # only, and no application table can be deleted through the runtime role.
        for table in APPLICATION_TABLES:
            quoted_table = bind.dialect.identifier_preparer.quote(table)
            _execute(f"REVOKE UPDATE, DELETE ON TABLE {quoted_table} FROM {quoted_role}")

        for table, columns in RUNTIME_UPDATE_COLUMNS.items():
            quoted_table = bind.dialect.identifier_preparer.quote(table)
            quoted_columns = ", ".join(bind.dialect.identifier_preparer.quote(column) for column in columns)
            _execute(f"GRANT UPDATE ({quoted_columns}) ON TABLE {quoted_table} TO {quoted_role}")

        _execute(f"REVOKE INSERT, UPDATE, DELETE ON TABLE alembic_version FROM {quoted_role}")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    policy_tables = {
        "attachments": ["attachments_factory_all", "attachments_supplier_read", "attachments_supplier_insert"],
        "notifications": ["notifications_tenant_select", "notifications_tenant_update", "notifications_related_insert"],
        "purchase_orders": ["purchase_orders_factory_all", "purchase_orders_supplier_read", "purchase_orders_supplier_update"],
        "suppliers": ["suppliers_owner_all", "suppliers_linked_supplier_read"],
    }
    for table in TENANT_TABLES:
        policy_tables[table] = [f"{table}_tenant_isolation"]

    for table, policies in policy_tables.items():
        for policy in policies:
            _execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
        _execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        _execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    runtime_role = os.getenv("RUNTIME_DB_USER", "factorylink_app")
    role_exists = bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
        {"role_name": runtime_role},
    ).scalar()
    if role_exists:
        quoted_role = bind.dialect.identifier_preparer.quote(runtime_role)
        for table in APPLICATION_TABLES:
            quoted_table = bind.dialect.identifier_preparer.quote(table)
            _execute(f"GRANT UPDATE, DELETE ON TABLE {quoted_table} TO {quoted_role}")
        _execute(f"GRANT INSERT, UPDATE, DELETE ON TABLE alembic_version TO {quoted_role}")
