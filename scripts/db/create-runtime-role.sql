\set ON_ERROR_STOP on

-- Create or rotate the least-privilege application role. psql variables are
-- quoted as SQL literals; format(%I/%L) safely quotes identifiers/secrets.
SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT',
    :'runtime_db_user', :'runtime_db_password'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'runtime_db_user'
)
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT',
    :'runtime_db_user', :'runtime_db_password'
)
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'runtime_db_user')
\gexec
GRANT USAGE ON SCHEMA public TO :"runtime_db_user";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM :"runtime_db_user";
-- This bootstrap runs on every Compose start, including against an existing
-- database. Revoke broad table UPDATE/DELETE first. PostgreSQL also removes
-- column-level UPDATE grants when a table-level UPDATE grant is revoked, so
-- the reviewed workflow grants are explicitly reapplied below. Every GRANT is
-- conditional because the first bootstrap runs before Alembic creates tables.
REVOKE UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM :"runtime_db_user";
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO :"runtime_db_user";

SELECT format('GRANT UPDATE (language, password_hash, is_active) ON TABLE public.users TO %I', :'runtime_db_user')
WHERE to_regclass('public.users') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (revoked_at, replaced_by_id) ON TABLE public.refresh_tokens TO %I', :'runtime_db_user')
WHERE to_regclass('public.refresh_tokens') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (status, supplier_note) ON TABLE public.purchase_orders TO %I', :'runtime_db_user')
WHERE to_regclass('public.purchase_orders') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (received_quantity) ON TABLE public.purchase_orders TO %I', :'runtime_db_user')
WHERE EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'purchase_orders' AND column_name = 'received_quantity'
)
\gexec
SELECT format('GRANT UPDATE (quantity_on_hand, quantity_reserved, status) ON TABLE public.material_batches TO %I', :'runtime_db_user')
WHERE to_regclass('public.material_batches') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (status, reserved_batch_ids, completed_quantity, rejected_quantity) ON TABLE public.production_orders TO %I', :'runtime_db_user')
WHERE to_regclass('public.production_orders') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (status, total_downtime_minutes) ON TABLE public.equipment TO %I', :'runtime_db_user')
WHERE to_regclass('public.equipment') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (status, downtime_minutes, notes) ON TABLE public.maintenance_tasks TO %I', :'runtime_db_user')
WHERE to_regclass('public.maintenance_tasks') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (is_read) ON TABLE public.notifications TO %I', :'runtime_db_user')
WHERE to_regclass('public.notifications') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (used_at) ON TABLE public.auth_action_tokens TO %I', :'runtime_db_user')
WHERE to_regclass('public.auth_action_tokens') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (is_active) ON TABLE public.quality_templates TO %I', :'runtime_db_user')
WHERE to_regclass('public.quality_templates') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (status, containment_action, root_cause, corrective_action, preventive_action, verification, owner, due_date, updated_at, closed_at) ON TABLE public.corrective_actions TO %I', :'runtime_db_user')
WHERE to_regclass('public.corrective_actions') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (status, customer_name, shipment_reference, shipped_at) ON TABLE public.finished_product_serials TO %I', :'runtime_db_user')
WHERE to_regclass('public.finished_product_serials') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (status) ON TABLE public.finished_product_batches TO %I', :'runtime_db_user')
WHERE to_regclass('public.finished_product_batches') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (maintenance_type) ON TABLE public.maintenance_tasks TO %I', :'runtime_db_user')
WHERE EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'maintenance_tasks' AND column_name = 'maintenance_type'
)
\gexec
SELECT format('GRANT UPDATE (observed_quantity, ledger_quantity, variance, status, detected_by, detected_at, resolved_by, resolved_at, resolution_reason, resolution_reference, adjustment_movement_id) ON TABLE public.inventory_reconciliations TO %I', :'runtime_db_user')
WHERE to_regclass('public.inventory_reconciliations') IS NOT NULL
\gexec

-- Record edit/delete endpoints. Column grants keep ledger, audit and history
-- columns append-only while allowing the reviewed PATCH endpoints to save
-- changes and staff to remove records that have no history.
SELECT format('GRANT UPDATE (code, name, contact_name, email, phone, prefecture, status, supplier_organization_id) ON TABLE public.suppliers TO %I', :'runtime_db_user')
WHERE to_regclass('public.suppliers') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (supplier_id, po_number, item_name, quantity, unit, unit_price, due_date) ON TABLE public.purchase_orders TO %I', :'runtime_db_user')
WHERE to_regclass('public.purchase_orders') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (order_number, product_name, quantity, due_date, track_serials) ON TABLE public.production_orders TO %I', :'runtime_db_user')
WHERE to_regclass('public.production_orders') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (code, name, location, next_maintenance) ON TABLE public.equipment TO %I', :'runtime_db_user')
WHERE to_regclass('public.equipment') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (equipment_id, title, due_date) ON TABLE public.maintenance_tasks TO %I', :'runtime_db_user')
WHERE to_regclass('public.maintenance_tasks') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (name, process_type, criteria_json) ON TABLE public.quality_templates TO %I', :'runtime_db_user')
WHERE to_regclass('public.quality_templates') IS NOT NULL
\gexec
SELECT format('GRANT UPDATE (full_name, role) ON TABLE public.users TO %I', :'runtime_db_user')
WHERE to_regclass('public.users') IS NOT NULL
\gexec
SELECT format('GRANT DELETE ON TABLE public.%I TO %I', t.table_name, :'runtime_db_user')
FROM (VALUES ('suppliers'), ('purchase_orders'), ('production_orders'), ('equipment'), ('maintenance_tasks'), ('attachments')) AS t(table_name)
WHERE to_regclass('public.' || t.table_name) IS NOT NULL
\gexec

-- Alembic's version table is migration-owner metadata, not application data.
-- It does not exist during the first bootstrap, so revoke conditionally; this
-- also keeps an ordinary Compose restart from re-granting INSERT after 0004.
SELECT format('REVOKE INSERT, UPDATE, DELETE ON TABLE public.alembic_version FROM %I', :'runtime_db_user')
WHERE to_regclass('public.alembic_version') IS NOT NULL
\gexec
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"runtime_db_user";

SELECT format('REVOKE %I FROM %I', :'postgres_owner', :'runtime_db_user')
\gexec

-- Keep future tables read/insert-only too. Reviewed UPDATE columns for
-- existing tables are granted explicitly above and by the Alembic migrations.
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE UPDATE, DELETE ON TABLES FROM %I',
    :'postgres_owner', :'runtime_db_user'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT ON TABLES TO %I',
    :'postgres_owner', :'runtime_db_user'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I',
    :'postgres_owner', :'runtime_db_user'
)
\gexec
