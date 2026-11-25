"""Link quality inspections and genealogy to finished-product batches/serials."""
import os
import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0009_finished_product_quality"
down_revision = "0008_batch_manufacturer_rls"
branch_labels = None
depends_on = None


TENANT_TABLE = "finished_product_batches"


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if column.name not in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch:
                batch.add_column(column)
        else:
            op.add_column(table, column)


def _drop_column_if_present(table: str, column: str) -> None:
    if column in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
        else:
            op.drop_column(table, column)


def upgrade():
    bind = op.get_bind()
    from app.models import FinishedProductBatch

    FinishedProductBatch.__table__.create(bind=bind, checkfirst=True)
    _add_column_if_missing(
        "finished_product_batches",
        sa.Column("source_lots_json", sa.Text(), nullable=False, server_default="[]"),
    )
    _add_column_if_missing(
        "finished_product_serials",
        sa.Column("finished_product_batch_id", sa.Integer(), sa.ForeignKey("finished_product_batches.id"), nullable=True),
    )
    _add_column_if_missing(
        "quality_inspections",
        sa.Column("finished_product_batch_id", sa.Integer(), sa.ForeignKey("finished_product_batches.id"), nullable=True),
    )
    _add_column_if_missing(
        "quality_inspections",
        sa.Column("finished_product_serial_id", sa.Integer(), sa.ForeignKey("finished_product_serials.id"), nullable=True),
    )
    _add_column_if_missing(
        "corrective_actions",
        sa.Column("finished_product_batch_id", sa.Integer(), sa.ForeignKey("finished_product_batches.id"), nullable=True),
    )

    # FORCE RLS also applies to the migration owner, so backfill serialized
    # legacy output one tenant at a time instead of relying on owner bypass.
    organization_ids = (
        bind.execute(sa.text("SELECT id FROM organizations ORDER BY id")).scalars().all()
        if bind.dialect.name == "postgresql" else [None]
    )
    for organization_id in organization_ids:
        params = {}
        tenant_filter = ""
        if organization_id is not None:
            bind.execute(sa.text(
                "SELECT set_config('app.current_organization_id', :org_id, true)"
            ), {"org_id": str(int(organization_id))})
            tenant_filter = "AND s.organization_id = :organization_id"
            params["organization_id"] = organization_id
        bind.execute(sa.text(
            f"""INSERT INTO finished_product_batches
                    (organization_id, production_order_id, batch_number, product_name, quantity, source_lots_json, status, created_at)
                SELECT s.organization_id, s.production_order_id,
                       'FPB-' || p.order_number, MAX(s.product_name), COUNT(*), '[]',
                       CASE WHEN SUM(CASE WHEN s.status = 'QUARANTINED' THEN 1 ELSE 0 END) > 0
                            THEN 'HOLD' ELSE 'AVAILABLE' END,
                       MIN(s.created_at)
                FROM finished_product_serials AS s
                JOIN production_orders AS p ON p.id = s.production_order_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM finished_product_batches AS b
                    WHERE b.production_order_id = s.production_order_id
                ) {tenant_filter}
                GROUP BY s.organization_id, s.production_order_id, p.order_number"""
        ), params)
        serial_filter = "WHERE organization_id = :organization_id" if organization_id is not None else ""
        bind.execute(sa.text(
            f"""UPDATE finished_product_serials
                SET finished_product_batch_id = (
                    SELECT b.id FROM finished_product_batches AS b
                    WHERE b.production_order_id = finished_product_serials.production_order_id
                )
                WHERE finished_product_batch_id IS NULL {('AND organization_id = :organization_id' if organization_id is not None else '')}"""
        ), params)
        serial_rows = bind.execute(sa.text(
            f"""SELECT finished_product_batch_id, source_lots_json
                FROM finished_product_serials
                {serial_filter}
                {'AND' if serial_filter else 'WHERE'} finished_product_batch_id IS NOT NULL"""
        ), params).all()
        lots_by_batch: dict[int, set[str]] = {}
        for batch_id, lots_json in serial_rows:
            lots_by_batch.setdefault(batch_id, set()).update(json.loads(lots_json or "[]"))
        for batch_id, lots in lots_by_batch.items():
            bind.execute(sa.text(
                "UPDATE finished_product_batches SET source_lots_json = :source_lots WHERE id = :batch_id"
            ), {"source_lots": json.dumps(sorted(lots), ensure_ascii=False), "batch_id": batch_id})

    indexes = {
        (item["name"], item["column_names"][0])
        for table in ("finished_product_serials", "quality_inspections", "corrective_actions")
        for item in inspect(bind).get_indexes(table)
        if item.get("column_names")
    }
    for table, column, index_name in (
        ("finished_product_serials", "finished_product_batch_id", "ix_finished_product_serials_finished_product_batch_id"),
        ("quality_inspections", "finished_product_batch_id", "ix_quality_inspections_finished_product_batch_id"),
        ("quality_inspections", "finished_product_serial_id", "ix_quality_inspections_finished_product_serial_id"),
        ("corrective_actions", "finished_product_batch_id", "ix_corrective_actions_finished_product_batch_id"),
    ):
        if (index_name, column) not in indexes:
            op.create_index(index_name, table, [column])

    if bind.dialect.name == "postgresql":
        tenant_expr = "NULLIF(current_setting('app.current_organization_id', true), '')::bigint"
        op.execute(sa.text(
            f'ALTER TABLE "{TENANT_TABLE}" ENABLE ROW LEVEL SECURITY'
        ))
        op.execute(sa.text(f'ALTER TABLE "{TENANT_TABLE}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(
            f'CREATE POLICY "{TENANT_TABLE}_tenant_isolation" ON "{TENANT_TABLE}" '
            f'USING (organization_id = {tenant_expr}) WITH CHECK (organization_id = {tenant_expr})'
        ))
        runtime_role = os.getenv("RUNTIME_DB_USER", "factorylink_app")
        role_exists = bind.execute(
            sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role_name"),
            {"role_name": runtime_role},
        ).scalar()
        if role_exists:
            role = bind.dialect.identifier_preparer.quote(runtime_role)
            table = bind.dialect.identifier_preparer.quote(TENANT_TABLE)
            sequence = bind.dialect.identifier_preparer.quote("finished_product_batches_id_seq")
            op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE {table} TO {role}"))
            op.execute(sa.text(f"GRANT UPDATE (status) ON TABLE {table} TO {role}"))
            op.execute(sa.text(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {role}"))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(
            f'DROP POLICY IF EXISTS "{TENANT_TABLE}_tenant_isolation" ON "{TENANT_TABLE}"'
        ))
        op.execute(sa.text(f'ALTER TABLE "{TENANT_TABLE}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TENANT_TABLE}" DISABLE ROW LEVEL SECURITY'))

    for table, index_name in (
        ("corrective_actions", "ix_corrective_actions_finished_product_batch_id"),
        ("quality_inspections", "ix_quality_inspections_finished_product_serial_id"),
        ("quality_inspections", "ix_quality_inspections_finished_product_batch_id"),
        ("finished_product_serials", "ix_finished_product_serials_finished_product_batch_id"),
    ):
        if index_name in {item["name"] for item in inspect(bind).get_indexes(table)}:
            op.drop_index(index_name, table_name=table)
    _drop_column_if_present("corrective_actions", "finished_product_batch_id")
    _drop_column_if_present("quality_inspections", "finished_product_serial_id")
    _drop_column_if_present("quality_inspections", "finished_product_batch_id")
    _drop_column_if_present("finished_product_serials", "finished_product_batch_id")
    _drop_column_if_present("finished_product_batches", "source_lots_json")
    from app.models import FinishedProductBatch
    FinishedProductBatch.__table__.drop(bind=bind, checkfirst=True)
