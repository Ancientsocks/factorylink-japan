"""Expose factory-confirmed PO receipt totals to linked suppliers safely.

Supplier accounts are intentionally denied access to factory-owned material
batches and movement ledgers. Persist the cumulative receipt total on the PO,
backfill it from the append-only receipt ledger, and guard changes so only a
request whose tenant context is the PO-owning factory can update the counter.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import os

revision = "0006_supplier_receipt_progress"
down_revision = "0005_account_lifecycle"
branch_labels = None
depends_on = None

CONSTRAINT = "ck_po_received_quantity_bounds"


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    column_info = {column["name"]: column for column in inspector.get_columns("purchase_orders")}
    checks = {item.get("name") for item in inspector.get_check_constraints("purchase_orders")}
    needs_column = "received_quantity" not in column_info
    needs_check = CONSTRAINT not in checks
    # The original initial migration creates tables from live SQLAlchemy
    # metadata. Make sure both old upgrades and fresh installs have a genuine
    # database-side default: raw SQL maintenance/acceptance inserts do not
    # receive Python-side SQLAlchemy defaults.
    needs_default = not needs_column and column_info["received_quantity"].get("default") is None

    if bind.dialect.name == "sqlite":
        if needs_column or needs_check or needs_default:
            with op.batch_alter_table("purchase_orders", recreate="always") as batch:
                if needs_column:
                    batch.add_column(sa.Column("received_quantity", sa.Float(), nullable=False, server_default="0"))
                elif needs_default:
                    batch.alter_column("received_quantity", existing_type=sa.Float(), existing_nullable=False, server_default="0")
                if needs_check:
                    batch.create_check_constraint(CONSTRAINT, "received_quantity >= 0 AND received_quantity <= quantity + 0.000000001")
    else:
        if needs_column:
            op.add_column("purchase_orders", sa.Column("received_quantity", sa.Float(), nullable=False, server_default="0"))
        elif needs_default:
            op.alter_column("purchase_orders", "received_quantity", existing_type=sa.Float(), existing_nullable=False, server_default="0")
        if needs_check:
            op.create_check_constraint(CONSTRAINT, "purchase_orders", "received_quantity >= 0 AND received_quantity <= quantity + 0.000000001")

    # Backfill existing installations using the authoritative immutable receipt
    # movement ledger. Adjustment and production-consumption movements do not
    # count as supplier deliveries. PostgreSQL RLS is FORCE-enabled, so migrate
    # one owning organisation at a time rather than assuming the schema owner
    # bypasses row policies. SQLite has no RLS and can update in one statement.
    backfill_template = """
        UPDATE purchase_orders
           SET received_quantity = COALESCE((
               SELECT SUM(im.quantity)
                 FROM material_batches AS mb
                 JOIN inventory_movements AS im ON im.batch_id = mb.id
                WHERE mb.purchase_order_id = purchase_orders.id
                  AND im.movement_type = 'RECEIPT'
           ), 0)
        {where_clause}
    """
    if bind.dialect.name == "postgresql":
        organization_ids = bind.execute(sa.text("SELECT id FROM organizations ORDER BY id")).scalars().all()
        for organization_id in organization_ids:
            bind.execute(
                sa.text("SELECT set_config('app.current_organization_id', :org_id, true)"),
                {"org_id": str(int(organization_id))},
            )
            bind.execute(
                sa.text(backfill_template.format(where_clause="WHERE organization_id = :org_id")),
                {"org_id": organization_id},
            )
    else:
        bind.execute(sa.text(backfill_template.format(where_clause="")))

    if bind.dialect.name == "postgresql":
        runtime_role = os.getenv("RUNTIME_DB_USER", "factorylink_app")
        role_exists = bind.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
            {"role_name": runtime_role},
        ).scalar()
        if role_exists:
            role = bind.dialect.identifier_preparer.quote(runtime_role)
            op.execute(sa.text(f"GRANT UPDATE (received_quantity) ON TABLE purchase_orders TO {role}"))

        # The runtime role can update this column for warehouse receipt
        # workflows, but linked suppliers share the same DB role. A trigger
        # enforces that the transaction-local tenant is the owning factory.
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION factorylink_guard_po_received_quantity()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE tenant_id bigint;
            BEGIN
                IF NEW.received_quantity IS DISTINCT FROM OLD.received_quantity THEN
                    tenant_id := NULLIF(current_setting('app.current_organization_id', true), '')::bigint;
                    IF tenant_id IS DISTINCT FROM OLD.organization_id THEN
                        RAISE EXCEPTION 'Only the purchase-order owning factory can update received_quantity'
                            USING ERRCODE = '42501';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$
        """))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_factorylink_guard_po_received_quantity ON purchase_orders"))
        op.execute(sa.text("""
            CREATE TRIGGER trg_factorylink_guard_po_received_quantity
            BEFORE UPDATE OF received_quantity ON purchase_orders
            FOR EACH ROW EXECUTE FUNCTION factorylink_guard_po_received_quantity()
        """))

        # A supplier record must belong to the same manufacturer as the PO.
        # This prevents a malformed cross-organisation foreign-key reference
        # from exposing another factory's order to an otherwise linked supplier.
        op.execute(sa.text("DROP POLICY IF EXISTS purchase_orders_supplier_read ON purchase_orders"))
        op.execute(sa.text("DROP POLICY IF EXISTS purchase_orders_supplier_update ON purchase_orders"))
        supplier_link = (
            "supplier_id IN (SELECT s.id FROM suppliers AS s "
            "WHERE s.supplier_organization_id = "
            "NULLIF(current_setting('app.current_organization_id', true), '')::bigint "
            "AND s.organization_id = purchase_orders.organization_id)"
        )
        op.execute(sa.text(f"""
            CREATE POLICY purchase_orders_supplier_read ON purchase_orders FOR SELECT
            USING ({supplier_link})
        """))
        op.execute(sa.text(f"""
            CREATE POLICY purchase_orders_supplier_update ON purchase_orders FOR UPDATE
            USING ({supplier_link}) WITH CHECK ({supplier_link})
        """))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        runtime_role = os.getenv("RUNTIME_DB_USER", "factorylink_app")
        role_exists = bind.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
            {"role_name": runtime_role},
        ).scalar()
        if role_exists:
            role = bind.dialect.identifier_preparer.quote(runtime_role)
            op.execute(sa.text(f"REVOKE UPDATE (received_quantity) ON TABLE purchase_orders FROM {role}"))
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_factorylink_guard_po_received_quantity ON purchase_orders"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS factorylink_guard_po_received_quantity()"))
        op.execute(sa.text("DROP POLICY IF EXISTS purchase_orders_supplier_read ON purchase_orders"))
        op.execute(sa.text("DROP POLICY IF EXISTS purchase_orders_supplier_update ON purchase_orders"))
        supplier_link = (
            "supplier_id IN (SELECT s.id FROM suppliers AS s "
            "WHERE s.supplier_organization_id = "
            "NULLIF(current_setting('app.current_organization_id', true), '')::bigint)"
        )
        op.execute(sa.text(f"CREATE POLICY purchase_orders_supplier_read ON purchase_orders FOR SELECT USING ({supplier_link})"))
        op.execute(sa.text(f"CREATE POLICY purchase_orders_supplier_update ON purchase_orders FOR UPDATE USING ({supplier_link}) WITH CHECK ({supplier_link})"))
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("purchase_orders")}
    checks = {item.get("name") for item in inspector.get_check_constraints("purchase_orders")}
    if bind.dialect.name == "sqlite":
        if "received_quantity" in columns or CONSTRAINT in checks:
            with op.batch_alter_table("purchase_orders", recreate="always") as batch:
                if CONSTRAINT in checks:
                    batch.drop_constraint(CONSTRAINT, type_="check")
                if "received_quantity" in columns:
                    batch.drop_column("received_quantity")
    else:
        if CONSTRAINT in checks:
            op.drop_constraint(CONSTRAINT, "purchase_orders", type_="check")
        if "received_quantity" in columns:
            op.drop_column("purchase_orders", "received_quantity")
