"""Restrict material-batch rows to manufacturer organisations."""
from alembic import op

revision = "0008_batch_manufacturer_rls"
down_revision = "0007_quality_capa_serial_traceability"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """CREATE POLICY material_batches_manufacturer_only
               ON material_batches AS RESTRICTIVE FOR ALL
               USING (
                   EXISTS (
                       SELECT 1 FROM organizations
                       WHERE organizations.id = material_batches.organization_id
                         AND organizations.org_type = 'MANUFACTURER'
                   )
               )
               WITH CHECK (
                   EXISTS (
                       SELECT 1 FROM organizations
                       WHERE organizations.id = material_batches.organization_id
                         AND organizations.org_type = 'MANUFACTURER'
                   )
               )"""
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS material_batches_manufacturer_only ON material_batches"
        )
