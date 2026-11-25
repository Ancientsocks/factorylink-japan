"""Complete core quality, CAPA, serial genealogy and maintenance classification."""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0007_quality_capa_serial_traceability"
down_revision = "0006_supplier_receipt_progress"
branch_labels = None
depends_on = None

# Tenant-owned tables added after the original RLS migration.
TENANT_TABLES = ("quality_templates", "corrective_actions", "finished_product_serials")


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch:
                batch.add_column(column)
        else:
            op.add_column(table, column)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
    # Create parent/reference tables before adding the optional template FK.
    from app.models import QualityTemplate, CorrectiveAction, FinishedProductSerial
    QualityTemplate.__table__.create(bind=bind, checkfirst=True)
    _add_column_if_missing("production_orders", sa.Column("track_serials", sa.Boolean(), nullable=False, server_default=sa.true()))
    _add_column_if_missing("quality_inspections", sa.Column("template_id", sa.Integer(), sa.ForeignKey("quality_templates.id"), nullable=True))
    _add_column_if_missing("quality_inspections", sa.Column("criteria_results_json", sa.Text(), nullable=False, server_default="{}"))
    _add_column_if_missing("maintenance_tasks", sa.Column("maintenance_type", sa.String(length=24), nullable=False, server_default="PREVENTIVE"))
    CorrectiveAction.__table__.create(bind=bind, checkfirst=True)
    FinishedProductSerial.__table__.create(bind=bind, checkfirst=True)

    if bind.dialect.name == "postgresql":
        tenant_expr = "NULLIF(current_setting('app.current_organization_id', true), '')::bigint"
        for table in TENANT_TABLES:
            op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(
                f'CREATE POLICY "{table}_tenant_isolation" ON "{table}" '
                f'USING (organization_id = {tenant_expr}) WITH CHECK (organization_id = {tenant_expr})'
            ))
        runtime_role = os.getenv("RUNTIME_DB_USER", "factorylink_app")
        role_exists = bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"), {"role_name": runtime_role}).scalar()
        if role_exists:
            role = bind.dialect.identifier_preparer.quote(runtime_role)
            for table in ("quality_templates", "corrective_actions", "finished_product_serials"):
                quoted = bind.dialect.identifier_preparer.quote(table)
                op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE {quoted} TO {role}"))
            op.execute(sa.text(f"GRANT UPDATE (status, containment_action, root_cause, corrective_action, preventive_action, verification, owner, due_date, updated_at, closed_at) ON TABLE corrective_actions TO {role}"))
            op.execute(sa.text(f"GRANT UPDATE (status, customer_name, shipment_reference, shipped_at) ON TABLE finished_product_serials TO {role}"))
            op.execute(sa.text(f"GRANT UPDATE (is_active) ON TABLE quality_templates TO {role}"))
            op.execute(sa.text(f"GRANT UPDATE (maintenance_type) ON TABLE maintenance_tasks TO {role}"))
            for table in ("quality_templates", "corrective_actions", "finished_product_serials"):
                seq = bind.dialect.identifier_preparer.quote(f"{table}_id_seq")
                op.execute(sa.text(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO {role}"))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("finished_product_serials", "corrective_actions", "quality_templates"):
            op.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_isolation" ON "{table}"'))
            op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
    from app.models import FinishedProductSerial, CorrectiveAction, QualityTemplate
    FinishedProductSerial.__table__.drop(bind=bind, checkfirst=True)
    CorrectiveAction.__table__.drop(bind=bind, checkfirst=True)
    QualityTemplate.__table__.drop(bind=bind, checkfirst=True)
    for table, column in (("maintenance_tasks", "maintenance_type"), ("quality_inspections", "criteria_results_json"), ("quality_inspections", "template_id"), ("production_orders", "track_serials")):
        if column in {item["name"] for item in inspect(bind).get_columns(table)}:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table(table) as batch:
                    batch.drop_column(column)
            else:
                op.drop_column(table, column)
