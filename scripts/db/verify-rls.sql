\set ON_ERROR_STOP on

-- Development/demo acceptance test. Requires SEED_DEMO_DATA=true and the
-- fictional SAKURA-JP, OSAKA-SUP and TOKYO-IND organisations.
-- Run as the migration owner/superuser; the script SET ROLEs to the runtime
-- login so FORCE ROW LEVEL SECURITY is exercised. All changes are rolled back.
BEGIN;
SELECT set_config('app.organization_provisioning', 'on', true);
SELECT id AS factory_org_id FROM organizations WHERE code = 'SAKURA-JP' \gset
SELECT id AS supplier_org_id FROM organizations WHERE code = 'OSAKA-SUP' \gset
SELECT id AS other_factory_org_id FROM organizations WHERE code = 'TOKYO-IND' \gset
SELECT set_config('app.organization_provisioning', '', true);

-- Seed one finished-product batch per factory so the new tenant policy is
-- tested against real rows. The enclosing transaction rolls these back.
SELECT set_config('app.current_organization_id', :'other_factory_org_id', true);
INSERT INTO production_orders
    (organization_id, order_number, product_name, quantity, completed_quantity, rejected_quantity,
     material_name, material_required, reserved_batch_ids, due_date, status, created_at, track_serials)
VALUES (:'other_factory_org_id', 'RLS-FP-OTHER-MO-0009', 'RLS Other Finished Part', 1, 0, 0,
        '', 0, '', NULL, 'COMPLETED', now(), true)
RETURNING id AS rls_other_order_id \gset
INSERT INTO finished_product_batches
    (organization_id, production_order_id, batch_number, product_name, quantity, source_lots_json, status, created_at)
VALUES (:'other_factory_org_id', :'rls_other_order_id', 'RLS-FP-OTHER-0009', 'RLS Other Finished Part', 1, '[]', 'AVAILABLE', now());

SELECT set_config('app.current_organization_id', :'factory_org_id', true);
INSERT INTO production_orders
    (organization_id, order_number, product_name, quantity, completed_quantity, rejected_quantity,
     material_name, material_required, reserved_batch_ids, due_date, status, created_at, track_serials)
VALUES (:'factory_org_id', 'RLS-FP-FACTORY-MO-0009', 'RLS Factory Finished Part', 1, 0, 0,
        '', 0, '', NULL, 'COMPLETED', now(), true)
RETURNING id AS rls_factory_order_id \gset
INSERT INTO finished_product_batches
    (organization_id, production_order_id, batch_number, product_name, quantity, source_lots_json, status, created_at)
VALUES (:'factory_org_id', :'rls_factory_order_id', 'RLS-FP-FACTORY-0009', 'RLS Factory Finished Part', 1, '[]', 'AVAILABLE', now());

-- Create a supplier relationship and PO that are not shared with OSAKA-SUP.
-- The owner runs this inside the rollback-only transaction with factory context.
SELECT set_config('app.current_organization_id', :'factory_org_id', true);
INSERT INTO suppliers (organization_id, supplier_organization_id, code, name, contact_name, email, phone, prefecture, status, created_at)
VALUES (:'factory_org_id', :'other_factory_org_id', 'RLS-UNLINKED-SUP', 'Unlinked Test Supplier', '', '', '', '', 'ACTIVE', now())
RETURNING id AS unlinked_supplier_id \gset
INSERT INTO purchase_orders (organization_id, supplier_id, po_number, item_name, quantity, received_quantity, unit, unit_price, due_date, status, supplier_note, created_at)
VALUES (:'factory_org_id', :'unlinked_supplier_id', 'RLS-UNLINKED-PO', 'Unshared Test Material', 1, 0, 'pcs', 1, NULL, 'SUBMITTED', '', now());

-- Simulate a malformed cross-factory foreign-key reference. The application
-- prevents this, but the supplier policy must reject it even if data is corrupt.
SELECT id AS linked_supplier_id FROM suppliers WHERE organization_id = :'factory_org_id' AND code = 'SUP-OSK-01' \gset
SELECT set_config('app.current_organization_id', :'other_factory_org_id', true);
SELECT set_config('factorylink.test_other_organization_id', :'other_factory_org_id', true);
INSERT INTO purchase_orders (organization_id, supplier_id, po_number, item_name, quantity, received_quantity, unit, unit_price, due_date, status, supplier_note, created_at)
VALUES (:'other_factory_org_id', :'linked_supplier_id', 'RLS-CROSS-ORG-PO', 'Cross Factory Test Material', 1, 0, 'pcs', 1, NULL, 'SUBMITTED', '', now());

SELECT set_config('app.current_organization_id', :'factory_org_id', true);
SELECT id AS factory_admin_id FROM users WHERE email = 'admin@factorylink.jp' \gset
INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at, revoked_at, replaced_by_id, created_at)
VALUES (:'factory_admin_id', '00000000-0000-4000-8000-000000000010', repeat('b', 64), now() + interval '1 day', NULL, NULL, now());
INSERT INTO auth_action_tokens (organization_id, user_id, purpose, token_hash, expires_at, used_at, created_at)
VALUES (:'factory_org_id', :'factory_admin_id', 'PASSWORD_RESET', repeat('a', 64), now() + interval '1 day', NULL, now());

SELECT set_config('app.current_organization_id', :'other_factory_org_id', true);
SELECT id AS other_factory_admin_id FROM users WHERE email = 'admin@tokyo-industrial.jp' \gset
INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at, revoked_at, replaced_by_id, created_at)
VALUES (:'other_factory_admin_id', '00000000-0000-4000-8000-000000000011', repeat('c', 64), now() + interval '1 day', NULL, NULL, now());
INSERT INTO auth_action_tokens (organization_id, user_id, purpose, token_hash, expires_at, used_at, created_at)
VALUES (:'other_factory_org_id', :'other_factory_admin_id', 'PASSWORD_RESET', repeat('d', 64), now() + interval '1 day', NULL, now());

DO $$
DECLARE
    unprotected_tables text;
BEGIN
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO unprotected_tables
      FROM pg_class AS c
      JOIN pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r', 'p')
       AND EXISTS (
           SELECT 1 FROM pg_attribute AS a
            WHERE a.attrelid = c.oid
              AND a.attname = 'organization_id'
              AND a.attnum > 0
              AND NOT a.attisdropped
       )
       AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity);
    IF unprotected_tables IS NOT NULL THEN
        RAISE EXCEPTION 'Tenant-owned tables lack forced RLS: %', unprotected_tables;
    END IF;
    IF EXISTS (
        SELECT 1
          FROM pg_class AS c
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relname IN ('organizations', 'users', 'refresh_tokens', 'auth_action_tokens')
           AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
    ) THEN
        RAISE EXCEPTION 'An identity or authentication table lacks forced RLS';
    END IF;
END;
$$;

SET LOCAL ROLE :"runtime_db_user";
SELECT set_config('app.current_organization_id', '', true);
DO $$
BEGIN
    IF (SELECT count(*) FROM organizations) <> 0 THEN
        RAISE EXCEPTION 'Runtime role can read organizations without an authorized context';
    END IF;
    IF (SELECT count(*) FROM users) <> 0 THEN
        RAISE EXCEPTION 'Runtime role can read users without an authorized context';
    END IF;
    IF (SELECT count(*) FROM refresh_tokens) <> 0 THEN
        RAISE EXCEPTION 'Runtime role can read refresh tokens without an authorized context';
    END IF;
    IF (SELECT count(*) FROM auth_action_tokens) <> 0 THEN
        RAISE EXCEPTION 'Runtime role can read account-action tokens without an authorized context';
    END IF;
    IF (SELECT count(*) FROM material_batches) <> 0 THEN
        RAISE EXCEPTION 'Runtime role can read tenant inventory without a tenant context';
    END IF;
    IF (SELECT count(*) FROM finished_product_batches) <> 0 THEN
        RAISE EXCEPTION 'Runtime role can read finished-product batches without a tenant context';
    END IF;
END;
$$;

SELECT set_config('app.current_organization_id', :'factory_org_id', true);
SELECT set_config('app.auth_email', 'supplier@osaka-parts.jp', true);
DO $$
BEGIN
    IF (SELECT count(*) FROM users WHERE email = 'supplier@osaka-parts.jp') <> 1 THEN
        RAISE EXCEPTION 'Email-scoped login cannot find the requested account';
    END IF;
    IF (SELECT count(*) FROM users WHERE email = 'admin@tokyo-industrial.jp') <> 0 THEN
        RAISE EXCEPTION 'Email-scoped login exposed an unrelated account';
    END IF;
END;
$$;
SELECT set_config('app.auth_email', '', true);
DO $$
DECLARE
    table_name text;
    foreign_rows bigint;
    factory_id bigint := current_setting('app.current_organization_id')::bigint;
BEGIN
    FOR table_name IN
        SELECT DISTINCT c.table_name
          FROM information_schema.columns AS c
         WHERE c.table_schema = 'public'
           AND c.column_name = 'organization_id'
         ORDER BY c.table_name
    LOOP
        EXECUTE format(
            'SELECT count(*) FROM public.%I WHERE organization_id <> $1',
            table_name
        ) INTO foreign_rows USING factory_id;
        IF foreign_rows <> 0 THEN
            RAISE EXCEPTION 'Runtime tenant can read foreign organization rows in %', table_name;
        END IF;
    END LOOP;
END;
$$;
SELECT set_config('app.auth_refresh_token_hash', repeat('b', 64), true);
SELECT set_config('app.auth_action_token_hash', repeat('a', 64), true);
DO $$
BEGIN
    IF (SELECT count(*) FROM refresh_tokens) <> 1 THEN
        RAISE EXCEPTION 'Refresh-token digest context did not resolve exactly one token';
    END IF;
    IF (SELECT count(*) FROM auth_action_tokens) <> 1 THEN
        RAISE EXCEPTION 'Action-token digest context did not resolve exactly one token';
    END IF;
END;
$$;
SELECT set_config('app.auth_user_id', :'factory_admin_id', true);
DO $$
BEGIN
    IF (SELECT count(*) FROM users WHERE id = current_setting('app.auth_user_id')::bigint) <> 1 THEN
        RAISE EXCEPTION 'Validated token user context cannot resolve its account';
    END IF;
END;
$$;
SELECT set_config('app.auth_refresh_token_hash', '', true);
SELECT set_config('app.auth_action_token_hash', '', true);
SELECT set_config('app.auth_user_id', '', true);

SELECT set_config('app.organization_provisioning', 'on', true);
DO $$
BEGIN
    IF (SELECT count(*) FROM organizations) < 3 THEN
        RAISE EXCEPTION 'Provisioning context cannot inspect existing organizations safely';
    END IF;
END;
$$;
SELECT set_config('app.organization_provisioning', '', true);

DO $$
DECLARE
    factory_id bigint := current_setting('app.current_organization_id')::bigint;
    other_factory_id bigint := current_setting('factorylink.test_other_organization_id')::bigint;
    visible_own_organizations integer;
    visible_other_organizations integer;
    visible_own_users integer;
    visible_other_users integer;
    visible_own_refresh_tokens integer;
    visible_other_refresh_tokens integer;
    visible_other_action_tokens integer;
    visible_own_batches integer;
    visible_other_batches integer;
    visible_own_finished_batch integer;
    visible_other_finished_batch integer;
BEGIN
    SELECT count(*) INTO visible_own_organizations FROM organizations WHERE id = factory_id;
    SELECT count(*) INTO visible_other_organizations FROM organizations WHERE id = other_factory_id;
    SELECT count(*) INTO visible_own_users FROM users WHERE organization_id = factory_id;
    SELECT count(*) INTO visible_other_users FROM users WHERE organization_id = other_factory_id;
    SELECT count(*) INTO visible_own_refresh_tokens FROM refresh_tokens
      WHERE user_id IN (SELECT id FROM users WHERE organization_id = factory_id);
    SELECT count(*) INTO visible_other_refresh_tokens FROM refresh_tokens
      WHERE user_id IN (SELECT id FROM users WHERE organization_id = other_factory_id);
    SELECT count(*) INTO visible_other_action_tokens FROM auth_action_tokens
      WHERE organization_id = other_factory_id;
    IF visible_own_organizations <> 1 OR visible_other_organizations <> 0 THEN
        RAISE EXCEPTION 'Organization RLS did not restrict the factory tenant';
    END IF;
    IF visible_own_users = 0 OR visible_other_users <> 0 THEN
        RAISE EXCEPTION 'User RLS did not restrict the factory tenant';
    END IF;
    IF visible_other_refresh_tokens <> 0 THEN
        RAISE EXCEPTION 'Refresh-token RLS exposed another tenant';
    END IF;
    IF visible_other_action_tokens <> 0 THEN
        RAISE EXCEPTION 'Account-action token RLS exposed another tenant';
    END IF;
    IF visible_own_refresh_tokens <> 1 THEN
        RAISE EXCEPTION 'Factory tenant cannot read its own refresh-token row';
    END IF;
    SELECT count(*) INTO visible_own_batches FROM material_batches WHERE organization_id = factory_id;
    SELECT count(*) INTO visible_other_batches FROM material_batches WHERE organization_id = other_factory_id;
    SELECT count(*) INTO visible_own_finished_batch FROM finished_product_batches
        WHERE batch_number = 'RLS-FP-FACTORY-0009';
    SELECT count(*) INTO visible_other_finished_batch FROM finished_product_batches
        WHERE batch_number = 'RLS-FP-OTHER-0009';
    IF visible_own_batches = 0 THEN
        RAISE EXCEPTION 'Factory tenant cannot read its own sample material batches';
    END IF;
    IF visible_other_batches <> 0 THEN
        RAISE EXCEPTION 'Factory tenant can read another factory tenant material batches';
    END IF;
    IF visible_own_finished_batch <> 1 THEN
        RAISE EXCEPTION 'Factory tenant cannot read its own finished-product batch';
    END IF;
    IF visible_other_finished_batch <> 0 THEN
        RAISE EXCEPTION 'Factory tenant can read another factory finished-product batch';
    END IF;
END;
$$;

SELECT set_config('app.current_organization_id', :'other_factory_org_id', true);
DO $$
DECLARE
    visible_own_finished_batch integer;
    visible_foreign_finished_batch integer;
BEGIN
    SELECT count(*) INTO visible_own_finished_batch FROM finished_product_batches
        WHERE batch_number = 'RLS-FP-OTHER-0009';
    SELECT count(*) INTO visible_foreign_finished_batch FROM finished_product_batches
        WHERE batch_number = 'RLS-FP-FACTORY-0009';
    IF visible_own_finished_batch <> 1 THEN
        RAISE EXCEPTION 'Other factory tenant cannot read its own finished-product batch';
    END IF;
    IF visible_foreign_finished_batch <> 0 THEN
        RAISE EXCEPTION 'Other factory tenant can read the first factory finished-product batch';
    END IF;
END;
$$;

SELECT set_config('app.current_organization_id', :'supplier_org_id', true);
DO $$
DECLARE
    supplier_org_id bigint := current_setting('app.current_organization_id')::bigint;
    visible_orders integer;
    visible_suppliers integer;
    visible_batches integer;
    visible_finished_batches integer;
    unlinked_orders integer;
    unlinked_suppliers integer;
    cross_factory_orders integer;
    first_po_id integer;
BEGIN
    SELECT count(*) INTO visible_orders FROM purchase_orders;
    SELECT count(*) INTO visible_suppliers FROM suppliers;
    SELECT count(*) INTO visible_batches FROM material_batches;
    SELECT count(*) INTO visible_finished_batches FROM finished_product_batches;
    SELECT count(*) INTO unlinked_orders FROM purchase_orders WHERE po_number = 'RLS-UNLINKED-PO';
    SELECT count(*) INTO unlinked_suppliers FROM suppliers WHERE code = 'RLS-UNLINKED-SUP';
    SELECT count(*) INTO cross_factory_orders FROM purchase_orders WHERE po_number = 'RLS-CROSS-ORG-PO';
    IF visible_orders = 0 OR visible_suppliers = 0 THEN
        RAISE EXCEPTION 'Supplier tenant cannot read its linked supplier record/purchase orders';
    END IF;
    IF unlinked_orders <> 0 OR unlinked_suppliers <> 0 THEN
        RAISE EXCEPTION 'Supplier tenant can see a purchase order or supplier that is not linked to its workspace';
    END IF;
    IF cross_factory_orders <> 0 THEN
        RAISE EXCEPTION 'Supplier tenant can see a purchase order that references another factory supplier record';
    END IF;
    IF visible_batches <> 0 THEN
        RAISE EXCEPTION 'Supplier tenant can read factory inventory batches';
    END IF;
    IF visible_finished_batches <> 0 THEN
        RAISE EXCEPTION 'Supplier tenant can read factory finished-product batches';
    END IF;

    SELECT min(id) INTO first_po_id FROM purchase_orders;
    UPDATE purchase_orders SET supplier_note = supplier_note WHERE id = first_po_id;

    BEGIN
        UPDATE purchase_orders SET quantity = quantity WHERE id = first_po_id;
        RAISE EXCEPTION 'Runtime role unexpectedly updated purchase-order quantity';
    EXCEPTION WHEN insufficient_privilege THEN
        NULL;
    END;

    BEGIN
        UPDATE purchase_orders SET received_quantity = received_quantity + 1 WHERE id = first_po_id;
        RAISE EXCEPTION 'Supplier tenant unexpectedly changed factory-confirmed receipt totals';
    EXCEPTION WHEN insufficient_privilege THEN
        NULL;
    END;

    BEGIN
        DELETE FROM purchase_orders WHERE id = first_po_id;
        RAISE EXCEPTION 'Runtime role unexpectedly deleted a purchase order';
    EXCEPTION WHEN insufficient_privilege THEN
        NULL;
    END;

    BEGIN
        UPDATE audit_logs SET action = action WHERE false;
        RAISE EXCEPTION 'Runtime role unexpectedly updated immutable audit history';
    EXCEPTION WHEN insufficient_privilege THEN
        NULL;
    END;

    BEGIN
        INSERT INTO material_batches (organization_id, material_name, lot_number, quantity_on_hand, quantity_reserved, unit, unit_cost, status, received_at)
        VALUES (supplier_org_id, 'Forbidden Supplier Stock', 'RLS-FORBIDDEN-LOT', 1, 0, 'pcs', 1, 'AVAILABLE', now());
        RAISE EXCEPTION 'Supplier runtime role unexpectedly inserted factory inventory';
    EXCEPTION WHEN insufficient_privilege OR check_violation OR foreign_key_violation THEN
        NULL;
    END;
END;
$$;

ROLLBACK;
\echo 'FactoryLink RLS and runtime column-grant checks passed (all changes rolled back).'
