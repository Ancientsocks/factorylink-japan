"""Add immutable-snapshot inventory reconciliation records."""
import os

import sqlalchemy as sa
from alembic import op

revision = "0011_inventory_reconciliation"
down_revision = "0010_identity_rls"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    from app.models import InventoryReconciliation

    InventoryReconciliation.__table__.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE inventory_reconciliations ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE inventory_reconciliations FORCE ROW LEVEL SECURITY')
        op.execute(sa.text(
            """CREATE POLICY inventory_reconciliations_tenant_isolation
               ON inventory_reconciliations
               USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::bigint)
               WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::bigint)"""
        ))
        runtime_role = os.getenv("RUNTIME_DB_USER", "factorylink_app")
        # The runtime role is created by the bootstrap step (Compose) or by the
        # deploy tooling (managed PostgreSQL). Granting to a missing role aborts
        # the whole upgrade, so skip the grants when it does not exist yet.
        role_exists = bind.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
            {"role_name": runtime_role},
        ).scalar()
        if not role_exists:
            return
        role = bind.dialect.identifier_preparer.quote(runtime_role)
        table = bind.dialect.identifier_preparer.quote("inventory_reconciliations")
        sequence = bind.dialect.identifier_preparer.quote("inventory_reconciliations_id_seq")
        op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE {table} TO {role}"))
        op.execute(sa.text(
            f"GRANT UPDATE (observed_quantity, ledger_quantity, variance, status, detected_by, detected_at, resolved_by, resolved_at, resolution_reason, resolution_reference, adjustment_movement_id) ON TABLE {table} TO {role}"
        ))
        op.execute(sa.text(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {role}"))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('DROP POLICY IF EXISTS inventory_reconciliations_tenant_isolation ON inventory_reconciliations')
        op.execute('ALTER TABLE inventory_reconciliations NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE inventory_reconciliations DISABLE ROW LEVEL SECURITY')
    from app.models import InventoryReconciliation

    InventoryReconciliation.__table__.drop(bind=bind, checkfirst=True)
