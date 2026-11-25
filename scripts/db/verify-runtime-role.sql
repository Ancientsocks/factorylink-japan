\set ON_ERROR_STOP on

-- Run as the database owner/superuser after Compose has completed migrations:
-- docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--   -v runtime_db_user="$RUNTIME_DB_USER" -f /dev/stdin < scripts/db/verify-runtime-role.sql
SELECT set_config('factorylink.runtime_role', :'runtime_db_user', false);

SELECT
    has_column_privilege(:'runtime_db_user', 'public.purchase_orders', 'status', 'UPDATE') AS can_update_po_status,
    has_column_privilege(:'runtime_db_user', 'public.purchase_orders', 'supplier_note', 'UPDATE') AS can_update_supplier_note,
    has_column_privilege(:'runtime_db_user', 'public.purchase_orders', 'received_quantity', 'UPDATE') AS can_update_received_quantity,
    has_column_privilege(:'runtime_db_user', 'public.purchase_orders', 'quantity', 'UPDATE') AS can_update_po_quantity,
    has_column_privilege(:'runtime_db_user', 'public.finished_product_serials', 'status', 'UPDATE') AS can_update_serial_status,
    has_column_privilege(:'runtime_db_user', 'public.finished_product_serials', 'shipment_reference', 'UPDATE') AS can_update_serial_shipment,
    has_table_privilege(:'runtime_db_user', 'public.finished_product_batches', 'SELECT') AS can_read_finished_product_batches,
    has_column_privilege(:'runtime_db_user', 'public.finished_product_batches', 'status', 'UPDATE') AS can_update_finished_product_batch_status,
    has_column_privilege(:'runtime_db_user', 'public.corrective_actions', 'status', 'UPDATE') AS can_update_capa_status,
    has_table_privilege(:'runtime_db_user', 'public.alembic_version', 'INSERT') AS can_write_alembic_version;

DO $$
DECLARE
    role_name text := current_setting('factorylink.runtime_role');
    role_row record;
BEGIN
    SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolinherit
      INTO role_row
      FROM pg_roles
     WHERE rolname = role_name;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Runtime role % does not exist', role_name;
    END IF;
    IF role_row.rolsuper OR role_row.rolcreatedb OR role_row.rolcreaterole OR role_row.rolbypassrls OR role_row.rolinherit THEN
        RAISE EXCEPTION 'Runtime role % has an unsafe role attribute', role_name;
    END IF;

    IF NOT has_table_privilege(role_name, 'public.purchase_orders', 'SELECT') THEN
        RAISE EXCEPTION 'Runtime role cannot read purchase orders';
    END IF;
    IF NOT has_column_privilege(role_name, 'public.purchase_orders', 'status', 'UPDATE')
       OR NOT has_column_privilege(role_name, 'public.purchase_orders', 'supplier_note', 'UPDATE')
       OR NOT has_column_privilege(role_name, 'public.purchase_orders', 'received_quantity', 'UPDATE') THEN
        RAISE EXCEPTION 'Runtime role is missing reviewed purchase-order workflow update privileges';
    END IF;
    IF NOT has_column_privilege(role_name, 'public.purchase_orders', 'quantity', 'UPDATE')
       OR NOT has_column_privilege(role_name, 'public.purchase_orders', 'po_number', 'UPDATE')
       OR NOT has_column_privilege(role_name, 'public.purchase_orders', 'due_date', 'UPDATE') THEN
        RAISE EXCEPTION 'Runtime role cannot save purchase-order edits';
    END IF;
    IF to_regclass('public.finished_product_serials') IS NOT NULL
       AND (NOT has_table_privilege(role_name, 'public.finished_product_serials', 'SELECT')
            OR NOT has_column_privilege(role_name, 'public.finished_product_serials', 'status', 'UPDATE')
            OR NOT has_column_privilege(role_name, 'public.finished_product_serials', 'shipment_reference', 'UPDATE')) THEN
        RAISE EXCEPTION 'Runtime role is missing finished-serial shipment privileges';
    END IF;
    IF to_regclass('public.finished_product_batches') IS NOT NULL
       AND (NOT has_table_privilege(role_name, 'public.finished_product_batches', 'SELECT')
            OR NOT has_table_privilege(role_name, 'public.finished_product_batches', 'INSERT')
            OR NOT has_column_privilege(role_name, 'public.finished_product_batches', 'status', 'UPDATE')) THEN
        RAISE EXCEPTION 'Runtime role is missing finished-product batch workflow privileges';
    END IF;
    IF to_regclass('public.corrective_actions') IS NOT NULL
       AND (NOT has_table_privilege(role_name, 'public.corrective_actions', 'SELECT')
            OR NOT has_column_privilege(role_name, 'public.corrective_actions', 'status', 'UPDATE')) THEN
        RAISE EXCEPTION 'Runtime role is missing CAPA workflow privileges';
    END IF;
    IF to_regclass('public.inventory_reconciliations') IS NOT NULL
       AND (NOT has_table_privilege(role_name, 'public.inventory_reconciliations', 'SELECT')
            OR NOT has_table_privilege(role_name, 'public.inventory_reconciliations', 'INSERT')
            OR NOT has_column_privilege(role_name, 'public.inventory_reconciliations', 'status', 'UPDATE')
            OR has_table_privilege(role_name, 'public.inventory_reconciliations', 'DELETE')) THEN
        RAISE EXCEPTION 'Runtime role has incorrect inventory-reconciliation privileges';
    END IF;
    -- Records staff may remove from the operations screens.
    IF NOT has_table_privilege(role_name, 'public.purchase_orders', 'DELETE')
       OR NOT has_table_privilege(role_name, 'public.suppliers', 'DELETE')
       OR NOT has_table_privilege(role_name, 'public.attachments', 'DELETE') THEN
        RAISE EXCEPTION 'Runtime role cannot delete editable records';
    END IF;
    -- Immutable history stays append-only: no updates and no deletes.
    IF has_table_privilege(role_name, 'public.audit_logs', 'UPDATE')
       OR has_table_privilege(role_name, 'public.audit_logs', 'DELETE')
       OR has_table_privilege(role_name, 'public.inventory_movements', 'UPDATE')
       OR has_table_privilege(role_name, 'public.inventory_movements', 'DELETE')
       OR has_table_privilege(role_name, 'public.traceability_events', 'DELETE')
       OR has_table_privilege(role_name, 'public.quality_inspections', 'DELETE') THEN
        RAISE EXCEPTION 'Runtime role has forbidden mutable-history or delete privileges';
    END IF;
    IF to_regclass('public.alembic_version') IS NOT NULL
       AND has_table_privilege(role_name, 'public.alembic_version', 'INSERT') THEN
        RAISE EXCEPTION 'Runtime role can write Alembic migration history';
    END IF;

    RAISE NOTICE 'FactoryLink runtime role % passed least-privilege checks', role_name;
END;
$$;
