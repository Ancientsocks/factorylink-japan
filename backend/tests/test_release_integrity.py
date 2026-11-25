import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_inventory_receipt_modal_declares_purchase_order_state():
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "const [purchaseOrders, setPurchaseOrders] = useState<Row[]>([]);" in source
    assert "setPurchaseOrders(rows.filter" in source
    assert "purchaseOrders.find((x) => String(x.id) === value)" in source


def test_frontend_static_api_paths_exist_in_fastapi_route_table():
    frontend = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    backend = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    fixed_paths = set(re.findall(r"['\"](/api/v1/[^'\"`$]+)['\"]", frontend))
    route_paths = set(re.findall(r'@app\.(?:get|post|patch|put|delete)\("(/api/v1/[^\"]+)"', backend))
    missing = sorted(path for path in fixed_paths if path not in route_paths)
    assert not missing, f"Frontend API paths are missing from FastAPI: {missing}"


def test_runtime_role_bootstrap_does_not_regrant_table_wide_writes():
    sql = (ROOT / "scripts/db/create-runtime-role.sql").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", sql).upper()
    assert 'REVOKE UPDATE, DELETE ON ALL TABLES IN SCHEMA PUBLIC FROM :' in normalized
    assert 'GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA PUBLIC TO :' in normalized
    assert 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA PUBLIC' not in normalized


def test_runtime_role_default_privileges_are_read_and_insert_only():
    sql = (ROOT / "scripts/db/create-runtime-role.sql").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", sql).upper()
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE" in normalized
    assert "GRANT SELECT, INSERT ON TABLES TO" in normalized
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO" not in normalized


def test_compose_migrations_use_owner_but_api_uses_runtime_role():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "service_completed_successfully" in compose
    assert "DATABASE_URL: postgresql+psycopg://${POSTGRES_USER" in compose
    assert "DATABASE_URL: postgresql+psycopg://${RUNTIME_DB_USER" in compose
    assert "backend:" in compose and "worker:" in compose and "scheduler:" in compose


def test_runtime_role_bootstrap_relocks_alembic_version_after_global_grant():
    sql = (ROOT / "scripts/db/create-runtime-role.sql").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", sql).upper()
    global_grant = normalized.index("GRANT SELECT, INSERT ON ALL TABLES")
    migration_revoke = normalized.index("REVOKE INSERT, UPDATE, DELETE ON TABLE PUBLIC.ALEMBIC_VERSION")
    assert migration_revoke > global_grant
    assert "TO_REGCLASS('PUBLIC.ALEMBIC_VERSION') IS NOT NULL" in normalized


def test_postgres_role_acceptance_script_asserts_privilege_boundary():
    sql = (ROOT / "scripts/db/verify-runtime-role.sql").read_text(encoding="utf-8").upper()
    for expected in (
        "ROLSUPER", "ROLCREATEDB", "ROLCREATEROLE", "ROLBYPASSRLS", "ROLINHERIT",
        "HAS_COLUMN_PRIVILEGE", "PUBLIC.PURCHASE_ORDERS", "PUBLIC.AUDIT_LOGS",
        "PUBLIC.ALEMBIC_VERSION", "RAISE EXCEPTION",
    ):
        assert expected in sql


def test_runtime_bootstrap_reapplies_all_reviewed_column_update_grants():
    sql = (ROOT / "scripts/db/create-runtime-role.sql").read_text(encoding="utf-8").upper()
    expected_grants = (
        "GRANT UPDATE (LANGUAGE, PASSWORD_HASH, IS_ACTIVE) ON TABLE PUBLIC.USERS",
        "GRANT UPDATE (REVOKED_AT, REPLACED_BY_ID) ON TABLE PUBLIC.REFRESH_TOKENS",
        "GRANT UPDATE (STATUS, SUPPLIER_NOTE) ON TABLE PUBLIC.PURCHASE_ORDERS",
        "GRANT UPDATE (QUANTITY_ON_HAND, QUANTITY_RESERVED, STATUS) ON TABLE PUBLIC.MATERIAL_BATCHES",
        "GRANT UPDATE (STATUS, RESERVED_BATCH_IDS, COMPLETED_QUANTITY, REJECTED_QUANTITY) ON TABLE PUBLIC.PRODUCTION_ORDERS",
        "GRANT UPDATE (STATUS, TOTAL_DOWNTIME_MINUTES) ON TABLE PUBLIC.EQUIPMENT",
        "GRANT UPDATE (STATUS, DOWNTIME_MINUTES, NOTES) ON TABLE PUBLIC.MAINTENANCE_TASKS",
        "GRANT UPDATE (IS_READ) ON TABLE PUBLIC.NOTIFICATIONS",
        "GRANT UPDATE (USED_AT) ON TABLE PUBLIC.AUTH_ACTION_TOKENS",
        "GRANT UPDATE (IS_ACTIVE) ON TABLE PUBLIC.QUALITY_TEMPLATES",
        "GRANT UPDATE (STATUS, CONTAINMENT_ACTION, ROOT_CAUSE, CORRECTIVE_ACTION, PREVENTIVE_ACTION, VERIFICATION, OWNER, DUE_DATE, UPDATED_AT, CLOSED_AT) ON TABLE PUBLIC.CORRECTIVE_ACTIONS",
        "GRANT UPDATE (STATUS, CUSTOMER_NAME, SHIPMENT_REFERENCE, SHIPPED_AT) ON TABLE PUBLIC.FINISHED_PRODUCT_SERIALS",
        "GRANT UPDATE (MAINTENANCE_TYPE) ON TABLE PUBLIC.MAINTENANCE_TASKS",
    )
    revoke_position = sql.index("REVOKE UPDATE, DELETE ON ALL TABLES")
    for grant in expected_grants:
        assert grant in sql
        assert sql.index(grant) > revoke_position


def test_browser_acceptance_suite_is_wired_into_ci_and_local_runner():
    e2e_tests = ROOT / "e2e/test_browser_journeys.py"
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    linux_runner = (ROOT / "scripts/e2e/run.sh").read_text(encoding="utf-8")
    windows_runner = (ROOT / "scripts/e2e/run.ps1").read_text(encoding="utf-8")
    source = e2e_tests.read_text(encoding="utf-8")
    journey_count = len(re.findall(r"^def test_", source, flags=re.MULTILINE))
    assert journey_count == 5
    assert "browser-e2e:" in workflow and "python -m pytest -q e2e" in workflow
    assert "backend/requirements.txt" in linux_runner and "e2e/requirements.txt" in linux_runner
    assert "backend/requirements.txt" in windows_runner and "e2e/requirements.txt" in windows_runner


def test_postgres_acceptance_runner_covers_rls_acl_api_celery_and_migrations():
    runner = (ROOT / "scripts/db/postgres-acceptance.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for expected in (
        "alembic upgrade head",
        "python -m app.seed",
        "verify-runtime-role.sql",
        "verify-rls.sql",
        "postgres-api-smoke.py",
        "celery-smoke.py",
        "redis-rate-limit-smoke.py",
        "migration-safety.py",
    ):
        assert expected in runner
    assert "PostgreSQL, API, Redis rate limiting, Celery and migration-safety acceptance completed successfully." in runner
    assert "postgresql-acceptance:" in workflow
    assert "image: postgres:17" in workflow
    assert "image: redis:7-alpine" in workflow
    assert "bash scripts/db/postgres-acceptance.sh" in workflow


def test_postgres_rls_acceptance_checks_no_context_and_unlinked_supplier_records():
    sql = (ROOT / "scripts/db/verify-rls.sql").read_text(encoding="utf-8").upper()
    assert "SET_CONFIG('APP.CURRENT_ORGANIZATION_ID', '', TRUE)" in sql
    assert "RLS-UNLINKED-PO" in sql
    assert "RLS-UNLINKED-SUP" in sql
    assert "RLS-CROSS-ORG-PO" in sql
    assert "TENANT-OWNED TABLES LACK FORCED RLS" in sql
    assert "RUNTIME TENANT CAN READ FOREIGN ORGANIZATION ROWS IN %" in sql
    assert "ACCOUNT-ACTION TOKEN RLS EXPOSED ANOTHER TENANT" in sql
    assert "RECEIVED_QUANTITY = RECEIVED_QUANTITY + 1" in sql
    assert "SUPPLIER TENANT CAN SEE A PURCHASE ORDER OR SUPPLIER" in sql
    assert "SUPPLIER TENANT CAN READ FACTORY INVENTORY BATCHES" in sql


def test_postgres_migration_safety_uses_only_disposable_namespaced_databases():
    source = (ROOT / "scripts/db/migration-safety.py").read_text(encoding="utf-8")
    assert 'DATABASE_PREFIX = "factorylink_migration_safety_"' in source
    assert '"CREATE DATABASE {}"' in source
    assert '"DROP DATABASE IF EXISTS {} WITH (FORCE)"' in source
    assert "0009_finished_product_quality" in source
    assert "0010_identity_rls" in source
    assert "0011_inventory_reconciliation" in source


def test_operational_acceptance_and_load_test_scripts_parse_and_are_bounded():
    scripts = (
        ROOT / "scripts/db/migration-safety.py",
        ROOT / "scripts/db/redis-rate-limit-smoke.py",
        ROOT / "scripts/db/postgres-api-smoke.py",
        ROOT / "scripts/load-test/manufacturing_transactions.py",
    )
    for path in scripts:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    load_test = scripts[-1].read_text(encoding="utf-8")
    assert "LOADTEST_MAX_OPERATIONS" in load_test
    assert "LOADTEST_REQUESTS_PER_MINUTE" in load_test
    assert "request_pacing_per_minute" in load_test
    assert "ThreadPoolExecutor(max_workers=users)" in load_test
    assert "/api/v1/production/orders" in load_test
    assert "inventory/receipts" in load_test
    assert "server_resource_usage" in load_test


def test_postgres_runtime_api_smoke_checks_supplier_boundary_and_post_commit_context():
    source = (ROOT / "scripts/db/postgres-api-smoke.py").read_text(encoding="utf-8")
    for expected in (
        "/api/v1/dashboard",
        "/api/v1/inventory/batches",
        "/api/v1/purchase-orders",
        "/api/v1/auth/refresh",
        "/api/v1/auth/language",
        "post-commit tenant context",
    ):
        assert expected in source


def test_supplier_visible_receipt_total_is_guarded_and_migrated():
    from pathlib import Path

    root = Path(__file__).parents[2]
    models = (root / "backend/app/models.py").read_text(encoding="utf-8")
    migration = (root / "backend/migrations/versions/0006_supplier_receipt_progress.py").read_text(encoding="utf-8")
    bootstrap = (root / "scripts/db/create-runtime-role.sql").read_text(encoding="utf-8")
    assert "received_quantity: Mapped[float]" in models
    assert 'server_default="0"' in models
    assert "ck_po_received_quantity_bounds" in models
    assert "UPDATE purchase_orders" in migration and "im.movement_type = 'RECEIPT'" in migration
    assert "factorylink_guard_po_received_quantity" in migration
    assert "ERRCODE = '42501'" in migration
    assert "information_schema.columns" in bootstrap and "GRANT UPDATE (received_quantity)" in bootstrap


def test_supplier_purchase_order_rls_correlates_supplier_to_order_owning_factory():
    from pathlib import Path

    root = Path(__file__).parents[2]
    rls_migration = (root / "backend/migrations/versions/0004_postgresql_tenant_rls.py").read_text(encoding="utf-8")
    receipt_migration = (root / "backend/migrations/versions/0006_supplier_receipt_progress.py").read_text(encoding="utf-8")
    assert "s.organization_id = purchase_orders.organization_id" in rls_migration
    assert "s.organization_id = purchase_orders.organization_id" in receipt_migration
    assert "purchase_orders_supplier_read" in receipt_migration
    assert "purchase_orders_supplier_update" in receipt_migration


def test_postgres_api_smoke_exercises_runtime_purchase_order_receipt_write():
    source = (ROOT / "scripts/db/postgres-api-smoke.py").read_text(encoding="utf-8")
    for expected in (
        '"/api/v1/suppliers"',
        '"/api/v1/purchase-orders"',
        '"/api/v1/inventory/receipts"',
        '"status": "IN_TRANSIT"',
        '"quantity": 2',
        '"remaining_quantity") == 3',
    ):
        assert expected in source


def test_postgres_rls_raw_sql_inserts_supply_non_server_defaulted_columns():
    source = (ROOT / "scripts/db/verify-rls.sql").read_text(encoding="utf-8")
    assert "received_quantity" in source
    assert "created_at" in source
    assert "received_at" in source
    assert "contact_name, email, phone, prefecture, status, created_at" in source


def test_rc13_notification_bulk_read_and_unread_count_routes_are_scoped():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert '@app.get("/api/v1/notifications/unread-count")' in source
    assert '@app.patch("/api/v1/notifications/read-all")' in source
    assert "Notification.organization_id == user.organization_id" in source
    assert "setUnreadCount(0)" in frontend
    assert "markAllNotificationsRead" in frontend


def test_rc13_inventory_and_quality_report_routes_are_present_and_supplier_restricted():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    for dataset in ("inventory", "quality"):
        for extension in ("csv", "xlsx"):
            assert f'@app.get("/api/v1/reports/{dataset}.{extension}")' in source
    assert "_ensure_manufacturer_report(user)" in source
    assert "dataset: ReportDataset" in frontend
    assert "factorylink-${dataset}-report.${kind}" in frontend
    assert "stock value JPY" not in source.lower()  # workbook values are numeric, not formula strings


def test_rc14_healthcheck_uses_readiness_and_metrics_are_not_publicly_proxied():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "frontend/nginx/default.conf.template").read_text(encoding="utf-8")
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert "/health/ready" in compose
    assert '@app.get("/health/ready"' in main
    assert '@app.get("/health/live"' in main
    assert '@app.get("/metrics"' in main
    assert "location = /health/ready" in nginx
    assert "location = /health/live" in nginx
    assert "location = /metrics" not in nginx


def test_rc14_backup_restore_and_load_test_tooling_is_present_and_guarded():
    backup = (ROOT / "scripts/backup/backup.sh").read_text(encoding="utf-8")
    restore = (ROOT / "scripts/backup/restore.sh").read_text(encoding="utf-8")
    backup_ps = (ROOT / "scripts/backup/backup.ps1").read_text(encoding="utf-8")
    restore_ps = (ROOT / "scripts/backup/restore.ps1").read_text(encoding="utf-8")
    load = (ROOT / "scripts/load/k6-smoke.js").read_text(encoding="utf-8")
    assert "pg_dump --format=custom" in backup
    assert "uploads.tar.gz" in backup
    assert "sha256sum" in backup
    assert "--single-transaction" in restore
    assert "--clean --if-exists" in restore
    assert "Type RESTORE" in restore
    assert "pre-restore-uploads" in restore
    assert 'mv /app/data/uploads' not in restore
    assert "find /app/data/uploads -mindepth 1" in restore
    assert "pre-restore-database" in restore and "pre-restore-uploads" in restore
    assert "docker compose run --rm db-bootstrap" in restore
    assert "docker compose run --rm --no-deps -e SEED_DEMO_DATA=false migrate" in restore
    assert "docker compose up -d backend worker scheduler frontend" in restore
    assert "pg_dump --format=custom" in backup_ps
    assert "-ConfirmRestore" in restore_ps
    assert "ALLOW_EXTERNAL" in load and "localhost" in load
    assert "/api/v1/dashboard" in load


def test_rc14_request_logging_does_not_log_query_or_body_payloads():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    formatter = (ROOT / "backend/app/observability.py").read_text(encoding="utf-8")
    assert '"request_id"' in source
    assert '"duration_ms"' in source
    assert "request.url.query" not in source
    assert "request.body" not in source
    assert "class JsonLogFormatter" in formatter
    assert "factorylink_http_request_duration_seconds_sum" in formatter


def test_production_runtime_configuration_fails_closed_on_transport_and_cors():
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    for expected in (
        "JWT_ALGORITHM=HS256",
        "HTTPS-only CORS_ORIGINS",
        "sslmode=require",
        "SMTP_STARTTLS=true",
        "SMTP_USERNAME and SMTP_PASSWORD must either both be set or both be empty",
    ):
        assert expected in main


def test_rc15_nginx_csp_is_limited_to_spa_while_swagger_docs_remain_routable():
    nginx = (ROOT / "frontend/nginx/default.conf.template").read_text(encoding="utf-8")
    assert "location = /docs" in nginx
    assert "location / {" in nginx
    assert "Content-Security-Policy" in nginx
    assert "script-src 'self'" in nginx
    assert "object-src 'none'" in nginx
    assert "frame-ancestors 'none'" in nginx
    # Swagger UI includes its own inline initializer, so the strict SPA CSP
    # must not be inherited from server context by its exact /docs location.
    server_context = nginx.split("server {", 1)[1].split("location = /api/v1/auth/login", 1)[0]
    assert "Content-Security-Policy" not in server_context
    assert 'https "max-age=31536000"' in nginx


def test_reproducible_acceptance_runner_reports_skipped_gates_instead_of_passing_them():
    runner = (ROOT / "scripts/acceptance/run.py").read_text(encoding="utf-8")
    for expected in (
        "Fresh Alembic migration",
        "Demo seed idempotency",
        "Live API factory/supplier smoke",
        "Vite production build",
        "Playwright browser journeys",
        "PostgreSQL/Redis/Celery acceptance",
        'record("Docker Compose configuration", "SKIP"',
        'record("Docker Compose isolated runtime", "SKIP"',
        "if args.strict and skipped",
    ):
        assert expected in runner


def test_reproducible_acceptance_runner_is_wired_into_ci_with_report_artifact():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "local-acceptance:" in workflow
    assert "python scripts/acceptance/run.py --skip-backend-tests" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "factorylink-local-acceptance" in workflow



def test_reproducible_acceptance_runner_redacts_demo_password_from_saved_logs():
    runner = (ROOT / "scripts/acceptance/run.py").read_text(encoding="utf-8")
    assert 'replace(DEMO_PASSWORD, "[redacted demo password]")' in runner


def test_live_acceptance_runner_exercises_supplier_to_quality_traceability_workflow():
    source = (ROOT / "scripts/acceptance/run.py").read_text(encoding="utf-8")
    for expected in (
        "PO-ACCEPTANCE-LIVE-001",
        '"status": "SUBMITTED"',
        '"status": "CONFIRMED"',
        '"status": "IN_TRANSIT"',
        '"purchase_order_id": po_id',
        '"status": "COMPLETED"',
        '"result": "FAIL"',
        "LOT-ACCEPTANCE-LIVE-001",
        '"PRODUCTION_RESERVED"',
        '"PRODUCTION_CONSUMED"',
        '"QUALITY_HOLD"',
    ):
        assert expected in source



def test_acceptance_runner_has_isolated_docker_compose_runtime_gate():
    runner = (ROOT / "scripts/acceptance/run.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for expected in (
        "--with-docker-runtime",
        '"up", "--build", "--detach"',
        'f"{base}/health/ready"',
        'f"{base}/api/v1/dashboard"',
        '"down", "--volumes", "--remove-orphans"',
        "unique",
    ):
        assert expected in runner
    assert "docker-compose-runtime:" in workflow
    assert "--with-docker-runtime" in workflow


def test_render_blueprint_uses_managed_runtime_credential_and_owner_secret():
    # The application services are staged for the second Blueprint sync.
    blueprint = (ROOT / "deploy/render-services.pending.yaml").read_text(encoding="utf-8")
    assert "name: factorylink-postgres" in blueprint
    assert "key: OWNER_DATABASE_URL\n        sync: false" in blueprint
    assert "key: RUNTIME_DATABASE_URL\n        fromDatabase:" in blueprint
    assert "key: RUNTIME_DB_PASSWORD" not in blueprint
    assert "python -m app.render_deploy prepare" in blueprint
    assert "python -m app.render_deploy bootstrap-admin" not in blueprint
    assert "key: BACKEND_HOST" in blueprint and "property: hostport" in blueprint


def test_render_deployment_helper_supports_precreated_managed_runtime_role():
    source = (ROOT / "backend/app/render_deploy.py").read_text(encoding="utf-8")
    assert "grant_existing_runtime_role" in source
    assert "RUNTIME_DATABASE_URL" in source
    assert "pg_auth_members" in source
    assert "does not CREATE/ALTER ROLE" in source
    assert "RUNTIME_DB_USER" in source  # role identity is propagated into Alembic RLS migrations


def test_rc20_upload_scanning_is_fail_closed_and_scans_before_storage():
    scanner = (ROOT / "backend/app/malware_scanner.py").read_text(encoding="utf-8")
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    config = (ROOT / "backend/app/config.py").read_text(encoding="utf-8")
    assert "zINSTREAM\\0" in scanner
    assert "MalwareDetected" in scanner and "MalwareScannerUnavailable" in scanner
    assert "MALWARE_SCAN_ENABLED=true" in scanner
    upload = main[main.index('async def upload_document'):main.index('@app.get("/api/v1/documents/{document_id}/download")')]
    assert upload.index("scan_document_bytes") < upload.index("save_document")
    assert "Uploaded document failed malware scanning" in upload
    assert "Document malware scanning is temporarily unavailable" in upload
    assert "malware_scanner_timeout_seconds" in config


def test_rc20_compose_runs_private_clamav_and_backend_waits_for_health():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "image: clamav/clamav:1.5" in compose
    assert "clamav_database:/var/lib/clamav" in compose
    assert "MALWARE_SCAN_ENABLED: ${MALWARE_SCAN_ENABLED:-true}" in compose
    assert "MALWARE_SCANNER_HOST: ${MALWARE_SCANNER_HOST:-clamav}" in compose
    backend = compose[compose.index("  backend:"):compose.index("  worker:")]
    assert "clamav: { condition: service_healthy }" in backend
    assert "clamav_database:" in compose
    assert "3310:" not in compose  # clamd must not be published on the host


def test_rc20_render_requires_private_clamav_endpoint_and_production_scanning():
    render = (ROOT / "deploy/render-services.pending.yaml").read_text(encoding="utf-8")
    assert 'key: MALWARE_SCAN_ENABLED\n        value: "true"' in render
    assert "key: MALWARE_SCANNER_HOST" in render
    assert "key: MALWARE_SCANNER_TIMEOUT_SECONDS" in render
    scanner_dockerfile = (ROOT / "scanner/Dockerfile").read_text(encoding="utf-8")
    assert "FROM clamav/clamav:1.5" in scanner_dockerfile


def test_rc20_readiness_includes_enabled_malware_scanner():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    scanner = (ROOT / "backend/app/malware_scanner.py").read_text(encoding="utf-8")
    assert 'result["malware_scanner"]' in source
    assert "ping_malware_scanner(config=settings)" in source
    assert '"not_required"' in source
    assert 'ready = all(value in {"ok", "not_required"}' in source
    assert 'connection.sendall(b"zPING\\0")' in scanner


def test_backend_docker_package_index_is_build_only_and_binary_wheels_are_required():
    dockerfile = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    assert "ARG PIP_INDEX_URL=https://pypi.org/simple" in dockerfile
    assert '--index-url "${PIP_INDEX_URL}"' in dockerfile
    assert "--only-binary=:all:" in dockerfile
    assert "ENV PIP_INDEX_URL" not in dockerfile


def test_local_start_scripts_check_engine_and_show_plain_build_output():
    powershell = (ROOT / "scripts/start.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "scripts/start.sh").read_text(encoding="utf-8")
    assert "docker info" in powershell and "--progress plain" in powershell
    assert "docker info" in shell and "--progress plain" in shell


def test_frontend_build_skips_audit_network_calls_and_release_docs_exist():
    frontend_dockerfile = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert "npm ci --no-audit --no-fund" in frontend_dockerfile
    assert (ROOT / "frontend/package-lock.json").is_file()
    for path in (
        "WINDOWS_SETUP.md", "USER_GUIDE.md", "RELEASE_NOTES.md",
        "docs/releases/RC24_BUILD_REPORT.md", "docs/releases/RC24_ACCEPTANCE_RESULTS.json",
    ):
        assert (ROOT / path).is_file(), f"Missing release documentation: {path}"


def test_identity_rls_migration_scopes_public_auth_and_provisioning_paths():
    migration = (ROOT / "backend/migrations/versions/0010_identity_rls.py").read_text(encoding="utf-8")
    main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    database = (ROOT / "backend/app/database.py").read_text(encoding="utf-8")
    for table in ("organizations", "users", "refresh_tokens", "auth_action_tokens"):
        assert f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY' in migration
        assert f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY' in migration
    for context in (
        "app.current_organization_id", "app.organization_provisioning",
        "app.auth_email", "app.auth_user_id", "app.auth_refresh_token_hash",
        "app.auth_action_token_hash", "app.supplier_organization_code",
        "app.system_job",
    ):
        assert context in migration or context in database
    assert 'set_request_context(db, "app.auth_email", payload.email.lower())' in main
    assert 'set_request_context(db, "app.auth_refresh_token_hash", digest)' in main
    assert 'set_request_context(db, "app.auth_action_token_hash", digest)' in main
    assert 'set_request_context(db, "app.supplier_organization_code", partner_code)' in main


def test_current_release_version_is_consistent_across_metadata():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    report = (ROOT / "docs/releases/RC24_BUILD_REPORT.md").read_text(encoding="utf-8")
    results = (ROOT / "docs/releases/RC24_ACCEPTANCE_RESULTS.json").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert version == "1.0.0-rc.24"
    assert version in report and version in results and version in readme


def test_postgresql_material_batches_restrictive_policy_excludes_supplier_orgs():
    migration = (ROOT / "backend/migrations/versions/0008_batch_manufacturer_rls.py").read_text(encoding="utf-8")
    assert 'CREATE POLICY material_batches_manufacturer_only' in migration
    assert 'ON material_batches AS RESTRICTIVE FOR ALL' in migration
    assert "organizations.org_type = 'MANUFACTURER'" in migration
    assert "DROP POLICY IF EXISTS material_batches_manufacturer_only" in migration


def test_finished_product_quality_migration_preserves_existing_rows_and_adds_tenant_rls():
    migration = (ROOT / "backend/migrations/versions/0009_finished_product_quality.py").read_text(encoding="utf-8")
    models = (ROOT / "backend/app/models.py").read_text(encoding="utf-8")
    runtime_sql = (ROOT / "scripts/db/create-runtime-role.sql").read_text(encoding="utf-8")
    verify_sql = (ROOT / "scripts/db/verify-runtime-role.sql").read_text(encoding="utf-8")
    assert 'down_revision = "0008_batch_manufacturer_rls"' in migration
    assert "finished_product_batches" in models and "source_lots_json" in models
    assert "finished_product_batch_id" in migration and "finished_product_serial_id" in migration
    assert "set_config('app.current_organization_id'" in migration
    assert 'CREATE POLICY "{TENANT_TABLE}_tenant_isolation"' in migration
    assert "GRANT UPDATE (status) ON TABLE public.finished_product_batches" in runtime_sql
    assert "can_update_finished_product_batch_status" in verify_sql


def test_render_blueprint_enables_fail_closed_rate_limits_and_private_scanner():
    render = (ROOT / "deploy/render-services.pending.yaml").read_text(encoding="utf-8")
    assert "key: RATE_LIMIT_ENABLED\n        value: \"true\"" in render
    assert "key: RATE_LIMIT_FAIL_CLOSED\n        value: \"true\"" in render
    assert "name: factorylink-clamav" in render
    assert "dockerfilePath: scanner/Dockerfile" in render
    assert "property: host" in render
    assert "key: MALWARE_SCANNER_HOST\n        fromService:" in render


def test_render_blueprint_is_staged_database_first_then_application_services():
    database_stage = (ROOT / "render.yaml").read_text(encoding="utf-8")
    application_stage = (ROOT / "deploy/render-services.pending.yaml").read_text(encoding="utf-8")
    deployment = (ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")
    # Stage 1 provisions only the managed database, before the restricted
    # runtime credential exists. It must not create application services yet.
    assert "name: factorylink-postgres" in database_stage
    assert "user: factorylink_owner" in database_stage
    assert "diskSizeGB: 15" in database_stage
    assert "\nservices:" not in database_stage
    # Stage 2 is the reviewed full configuration copied into the same root file.
    assert "\nservices:" in application_stage
    assert "fromDatabase:" in application_stage
    assert "name: factorylink-api" in application_stage
    # The staged file must never be selected as the Blueprint path.
    assert "render-services.pending.yaml" in deployment
    assert "Keep the Blueprint path as `render.yaml`" in deployment


def test_production_frontend_does_not_ship_fixed_demo_password_or_default_user():
    frontend = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "FactoryLink2026!" not in frontend
    assert "useState('admin@factorylink.jp')" not in frontend
    assert "useState('')" in frontend
    assert "import.meta.env.DEV" in frontend
    assert "VITE_FACTORYLINK_PUBLIC_REGISTRATION" in frontend
