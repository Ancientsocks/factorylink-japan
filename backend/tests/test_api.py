import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db, set_tenant_context
from app import models
from app.main import app
from app import main as main_module
from app.security import hash_password

@pytest.fixture()
def context(monkeypatch):
    monkeypatch.setattr(main_module.settings, "malware_scan_enabled", False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    factory = models.Organization(name="Sakura Test", code="SAKURA-TEST", org_type="MANUFACTURER")
    supplier_org = models.Organization(name="Osaka Test Supplier", code="OSAKA-TEST", org_type="SUPPLIER")
    other_org = models.Organization(name="Other Test Factory", code="OTHER-TEST", org_type="MANUFACTURER")
    db.add_all([factory, supplier_org, other_org]); db.flush()
    admin = models.User(organization_id=factory.id, email="admin@test.jp", full_name="Test Admin", password_hash=hash_password("FactoryLink2026!"), role="ORG_ADMIN")
    warehouse = models.User(organization_id=factory.id, email="warehouse@test.jp", full_name="Warehouse User", password_hash=hash_password("FactoryLink2026!"), role="WAREHOUSE_MANAGER")
    quality = models.User(organization_id=factory.id, email="quality@test.jp", full_name="Quality User", password_hash=hash_password("FactoryLink2026!"), role="QUALITY_INSPECTOR")
    supplier_user = models.User(organization_id=supplier_org.id, email="supplier@test.jp", full_name="Supplier User", password_hash=hash_password("FactoryLink2026!"), role="SUPPLIER_USER")
    other_user = models.User(organization_id=other_org.id, email="other@test.jp", full_name="Other User", password_hash=hash_password("FactoryLink2026!"), role="ORG_ADMIN")
    db.add_all([admin, warehouse, quality, supplier_user, other_user]); db.flush()
    supplier = models.Supplier(organization_id=factory.id, supplier_organization_id=supplier_org.id, code="SUP-1", name="Osaka Supplier")
    db.add(supplier); db.flush()
    db.add(models.PurchaseOrder(organization_id=factory.id, supplier_id=supplier.id, po_number="PO-TEST-1", item_name="Steel", quantity=100, unit="kg", status="SUBMITTED"))
    db.add(models.MaterialBatch(organization_id=factory.id, material_name="Steel", lot_number="LOT-TEST-1", quantity_on_hand=5, unit="kg", status="AVAILABLE"))
    db.commit()
    db.close()
    def override_get_db():
        s = TestingSession()
        try: yield s
        finally: s.close()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield {"client": client, "Session": TestingSession}
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def token(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "FactoryLink2026!"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def register_verification_token(client, email):
    """Complete the email-code step required before creating a workspace."""
    requested = client.post("/api/v1/auth/email-verification/request", json={"email": email, "purpose": "REGISTRATION"})
    assert requested.status_code == 202, requested.text
    code = requested.json().get("development_code")
    assert code, requested.text
    verified = client.post("/api/v1/auth/email-verification/verify", json={"email": email, "purpose": "REGISTRATION", "code": code})
    assert verified.status_code == 200, verified.text
    return verified.json()["verification_token"]


def test_readiness_includes_scanner_when_enabled(monkeypatch):
    from app import main as app_main
    from sqlalchemy import create_engine
    import sys
    import types

    class FakeRedisClient:
        def ping(self):
            return True
        def close(self):
            return None

    fake_redis = types.ModuleType("redis")
    fake_redis.Redis = types.SimpleNamespace(from_url=lambda *args, **kwargs: FakeRedisClient())
    monkeypatch.setitem(sys.modules, "redis", fake_redis)
    monkeypatch.setattr(app_main, "get_engine", lambda: create_engine("sqlite://"))
    monkeypatch.setattr(app_main.settings, "malware_scan_enabled", True)
    monkeypatch.setattr(app_main, "ping_malware_scanner", lambda **kwargs: False)
    checks = app_main.check_readiness_dependencies()
    assert checks == {"database": "ok", "redis": "ok", "malware_scanner": "unavailable"}

    monkeypatch.setattr(app_main, "ping_malware_scanner", lambda **kwargs: True)
    checks = app_main.check_readiness_dependencies()
    assert checks["malware_scanner"] == "ok"


def test_readiness_marks_scanner_not_required_only_when_disabled(monkeypatch):
    from app import main as app_main
    monkeypatch.setattr(app_main.settings, "malware_scan_enabled", False)
    monkeypatch.setattr(app_main, "ping_malware_scanner", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not ping disabled scanner")))
    # Probe the scanner branch directly through a stubbed database and Redis.
    from sqlalchemy import create_engine
    import sys, types
    class FakeRedisClient:
        def ping(self): return True
        def close(self): return None
    fake_redis = types.ModuleType("redis")
    fake_redis.Redis = types.SimpleNamespace(from_url=lambda *args, **kwargs: FakeRedisClient())
    monkeypatch.setitem(sys.modules, "redis", fake_redis)
    monkeypatch.setattr(app_main, "get_engine", lambda: create_engine("sqlite://"))
    checks = app_main.check_readiness_dependencies()
    assert checks["malware_scanner"] == "not_required"


def test_health_and_login(context):
    client = context["client"]
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "FactoryLink API"
    access = token(client, "admin@test.jp")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 200
    assert response.json()["role"] == "ORG_ADMIN"


def test_production_api_documentation_is_disabled():
    assert main_module.documentation_urls("production") == (None, None, None)
    assert main_module.documentation_urls("development") == ("/docs", "/redoc", "/openapi.json")


def test_refresh_token_reuse_revokes_its_session_family(context):
    client = context["client"]
    response = client.post("/api/v1/auth/login", json={"email": "admin@test.jp", "password": "FactoryLink2026!"})
    old = response.json()["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert rotated.status_code == 200
    child = rotated.json()["refresh_token"]
    assert child != old

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert replay.status_code == 401
    assert "reuse" in replay.json()["detail"].lower()
    # Replay detection revokes the current descendant, not just the ancestor.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": child}).status_code == 401


def test_refresh_replay_does_not_revoke_other_login_sessions(context):
    client = context["client"]
    first = client.post("/api/v1/auth/login", json={"email": "admin@test.jp", "password": "FactoryLink2026!"}).json()
    second = client.post("/api/v1/auth/login", json={"email": "admin@test.jp", "password": "FactoryLink2026!"}).json()
    rotated_first = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated_first.status_code == 200

    # Reusing the first session's ancestor revokes only the first family.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rotated_first.json()["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 200


def test_tenant_isolation(context):
    client = context["client"]
    access = token(client, "other@test.jp")
    response = client.get("/api/v1/inventory/batches", headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 200
    assert response.json() == []


def test_inventory_reconciliation_detects_without_mutating_and_resolves_with_audit(context):
    client = context["client"]
    factory = context["Session"]
    with factory() as db:
        batch = db.scalar(select(models.MaterialBatch).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
        warehouse = db.scalar(select(models.User).where(models.User.email == "warehouse@test.jp"))
        db.add(models.InventoryMovement(
            organization_id=batch.organization_id, batch_id=batch.id,
            movement_type="RECEIPT", quantity=5, reference="RECON-BASE",
            note="Test opening ledger", created_by=warehouse.id,
        ))
        batch.quantity_on_hand = 7
        db.commit()
        batch_id = batch.id

    warehouse_token = token(client, "warehouse@test.jp")
    denied = client.post(
        "/api/v1/inventory/reconciliations",
        headers={"Authorization": f"Bearer {token(client, 'supplier@test.jp')}"},
    )
    assert denied.status_code == 403

    detected = client.post(
        "/api/v1/inventory/reconciliations",
        headers={"Authorization": f"Bearer {warehouse_token}"},
    )
    assert detected.status_code == 201
    row = next(item for item in detected.json()["discrepancies"] if item["batch_id"] == batch_id)
    assert row["observed_quantity"] == 7
    assert row["ledger_quantity"] == 5
    with factory() as db:
        batch = db.get(models.MaterialBatch, batch_id)
        total = db.scalar(select(func.sum(models.InventoryMovement.quantity)).where(
            models.InventoryMovement.batch_id == batch_id,
        ))
        assert batch.quantity_on_hand == 7
        assert total == 5

    rejected = client.post(
        f"/api/v1/inventory/reconciliations/{row['id']}/resolve",
        headers={"Authorization": f"Bearer {warehouse_token}"},
        json={"counted_quantity": 6, "reference": "COUNT-1", "reason": "   "},
    )
    assert rejected.status_code == 422

    resolved = client.post(
        f"/api/v1/inventory/reconciliations/{row['id']}/resolve",
        headers={"Authorization": f"Bearer {warehouse_token}"},
        json={"counted_quantity": 6, "reference": "COUNT-1", "reason": "Physical count verified"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["adjustment_quantity"] == 1
    with factory() as db:
        batch = db.get(models.MaterialBatch, batch_id)
        movements = db.scalars(select(models.InventoryMovement).where(
            models.InventoryMovement.batch_id == batch_id,
        ).order_by(models.InventoryMovement.id)).all()
        audit = db.scalar(select(models.AuditLog).where(
            models.AuditLog.action == "INVENTORY_RECONCILIATION_RESOLVED",
        ))
        assert batch.quantity_on_hand == 6
        assert sum(item.quantity for item in movements) == 6
        assert movements[-1].movement_type == "ADJUSTMENT_IN"
        assert audit is not None
        assert "Physical count verified" in audit.payload


def test_inventory_reconciliation_rejects_reserved_stock_and_cross_tenant_records(context):
    client = context["client"]
    factory = context["Session"]
    with factory() as db:
        batch = db.scalar(select(models.MaterialBatch).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
        warehouse = db.scalar(select(models.User).where(models.User.email == "warehouse@test.jp"))
        batch.quantity_on_hand = 8
        batch.quantity_reserved = 4
        db.add(models.InventoryMovement(
            organization_id=batch.organization_id, batch_id=batch.id,
            movement_type="RECEIPT", quantity=5, reference="RECON-BASE-2",
            note="Test opening ledger", created_by=warehouse.id,
        ))
        db.commit()
        batch_id = batch.id

    warehouse_token = token(client, "warehouse@test.jp")
    detected = client.post(
        "/api/v1/inventory/reconciliations",
        headers={"Authorization": f"Bearer {warehouse_token}"},
    )
    row = next(item for item in detected.json()["discrepancies"] if item["batch_id"] == batch_id)
    correction = client.post(
        f"/api/v1/inventory/reconciliations/{row['id']}/resolve",
        headers={"Authorization": f"Bearer {warehouse_token}"},
        json={"counted_quantity": 3, "reference": "COUNT-2", "reason": "Verified physical count"},
    )
    assert correction.status_code == 409
    foreign_token = token(client, "other@test.jp")
    foreign_read = client.get(
        "/api/v1/inventory/reconciliations",
        headers={"Authorization": f"Bearer {foreign_token}"},
    )
    assert foreign_read.status_code == 200
    assert foreign_read.json() == []
    foreign_resolve = client.post(
        f"/api/v1/inventory/reconciliations/{row['id']}/resolve",
        headers={"Authorization": f"Bearer {foreign_token}"},
        json={"counted_quantity": 8, "reference": "COUNT-3", "reason": "Unauthorized count"},
    )
    assert foreign_resolve.status_code == 404


def test_duplicate_lot_receipt_is_rejected(context):
    client = context["client"]
    access = token(client, "warehouse@test.jp")
    response = client.post("/api/v1/inventory/receipts", headers={"Authorization": f"Bearer {access}"}, json={
        "material_name": "Steel", "lot_number": "LOT-TEST-1", "quantity": 12, "unit": "kg", "unit_cost": 10, "reference": "GR-001"
    })
    assert response.status_code == 409


def test_reservation_blocks_insufficient_stock(context):
    client = context["client"]
    access = token(client, "admin@test.jp")
    create = client.post("/api/v1/production/orders", headers={"Authorization": f"Bearer {access}"}, json={
        "order_number": "MO-TEST-1", "product_name": "Bracket", "quantity": 20, "material_name": "Steel", "material_required": 50
    })
    assert create.status_code == 201
    transition = client.patch(f"/api/v1/production/orders/{create.json()['id']}/status", headers={"Authorization": f"Bearer {access}"}, json={"status": "READY"})
    assert transition.status_code == 409


def test_failed_inspection_requires_capa_and_holds_batch(context):
    client = context["client"]
    access = token(client, "quality@test.jp")
    headers = {"Authorization": f"Bearer {access}"}
    batch_id = context["Session"]().scalar(select(models.MaterialBatch.id).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
    invalid = client.post("/api/v1/quality/inspections", headers=headers, json={"inspection_number":"QI-TEST-1", "product_name":"Steel", "batch_id":batch_id, "result":"FAIL", "defect_count":2})
    assert invalid.status_code == 422
    created = client.post("/api/v1/quality/inspections", headers=headers, json={"inspection_number":"QI-TEST-2", "product_name":"Steel", "batch_id":batch_id, "result":"FAIL", "defect_count":2, "sample_size":10, "corrective_action":"Contain and investigate"})
    assert created.status_code == 201
    check = context["Session"]()
    batch = check.scalar(select(models.MaterialBatch).where(models.MaterialBatch.id == batch_id))
    assert batch.status == "HOLD"
    check.close()


def test_supplier_only_sees_their_purchase_orders(context):
    client = context["client"]
    access = token(client, "supplier@test.jp")
    response = client.get("/api/v1/purchase-orders", headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 200
    assert [x["po_number"] for x in response.json()] == ["PO-TEST-1"]
    assert client.get("/api/v1/inventory/batches", headers={"Authorization": f"Bearer {access}"}).status_code == 403


def test_maintenance_downtime_update_is_idempotent(context):
    client = context["client"]
    access = token(client, "admin@test.jp")
    headers = {"Authorization": f"Bearer {access}"}
    machine = client.post("/api/v1/maintenance/equipment", headers=headers, json={"code": "MC-TEST", "name": "Test CNC", "location": "Line 1"})
    assert machine.status_code == 201, machine.text
    task = client.post("/api/v1/maintenance/tasks", headers=headers, json={"equipment_id": machine.json()["id"], "title": "Spindle service"})
    assert task.status_code == 201, task.text
    url = f"/api/v1/maintenance/tasks/{task.json()['id']}"
    for _ in range(2):
        updated = client.patch(url, headers=headers, json={"status": "COMPLETED", "downtime_minutes": 45, "notes": "Completed service"})
        assert updated.status_code == 200, updated.text
    equipment = client.get("/api/v1/maintenance/equipment", headers=headers).json()
    row = next(x for x in equipment if x["code"] == "MC-TEST")
    assert row["total_downtime_minutes"] == 45


def test_reports_are_scoped_and_downloadable(context):
    client = context["client"]
    own = token(client, "admin@test.jp")
    other = token(client, "other@test.jp")
    own_report = client.get("/api/v1/reports/production.csv", headers={"Authorization": f"Bearer {own}"})
    other_report = client.get("/api/v1/reports/production.csv", headers={"Authorization": f"Bearer {other}"})
    assert own_report.status_code == 200
    assert "Order,Product" in own_report.text
    assert other_report.status_code == 200
    assert "PO-TEST" not in other_report.text
    workbook = client.get("/api/v1/reports/production.xlsx", headers={"Authorization": f"Bearer {own}"})
    assert workbook.status_code == 200
    assert "spreadsheetml" in workbook.headers["content-type"]


def test_dashboard_kpis_calculate_organization_totals(context):
    from datetime import date, timedelta

    client = context["client"]
    access = token(client, "admin@test.jp")
    db = context["Session"]()
    try:
        factory = db.scalar(select(models.Organization).where(models.Organization.code == "SAKURA-TEST"))
        admin = db.scalar(select(models.User).where(models.User.email == "admin@test.jp"))
        batch = db.scalar(select(models.MaterialBatch).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
        assert factory and admin and batch
        batch.unit_cost = 4
        db.add(models.MaterialBatch(
            organization_id=factory.id, material_name="Copper", lot_number="LOT-DASHBOARD-2",
            quantity_on_hand=2, unit="kg", unit_cost=3, status="AVAILABLE",
        ))
        db.add_all([
            models.ProductionOrder(
                organization_id=factory.id, order_number="MO-DASHBOARD-1", product_name="Part A",
                quantity=10, completed_quantity=2, status="IN_PROGRESS", due_date=date.today() - timedelta(days=1),
            ),
            models.ProductionOrder(
                organization_id=factory.id, order_number="MO-DASHBOARD-2", product_name="Part B",
                quantity=10, completed_quantity=10, status="COMPLETED",
            ),
            models.QualityInspection(
                organization_id=factory.id, created_by=admin.id, inspection_number="QI-DASHBOARD-1",
                product_name="Part A", result="FAIL", defect_count=2, sample_size=10,
            ),
        ])
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 200, response.text
    kpis = response.json()["kpis"]
    assert kpis == {
        "production_orders": 2,
        "completed_orders": 1,
        "delayed_orders": 1,
        "production_progress": 60.0,
        "defect_rate": 20.0,
        "inventory_value": 26.0,
        "low_stock_count": 0,
        "open_purchase_orders": 1,
        "equipment_count": 0,
        "equipment_due": 0,
    }


def test_spreadsheet_exports_escape_formula_like_user_text(context):
    from io import BytesIO
    from openpyxl import load_workbook

    client = context["client"]
    access = token(client, "admin@test.jp")
    headers = {"Authorization": f"Bearer {access}"}
    created = client.post("/api/v1/production/orders", headers=headers, json={
        "order_number": "MO-SAFE-EXPORT", "product_name": "=HYPERLINK(\"https://example.invalid\",\"click\")",
        "quantity": 1, "material_name": "Steel", "material_required": 0
    })
    assert created.status_code == 201, created.text

    csv_response = client.get("/api/v1/reports/production.csv", headers=headers)
    assert csv_response.status_code == 200
    assert "'=HYPERLINK" in csv_response.text

    xlsx_response = client.get("/api/v1/reports/production.xlsx", headers=headers)
    workbook = load_workbook(BytesIO(xlsx_response.content), data_only=False)
    matching = [row for row in workbook.active.iter_rows(min_row=2, values_only=False) if row[0].value == "MO-SAFE-EXPORT"]
    assert matching
    assert matching[0][1].data_type == "s"


def test_inspection_defects_cannot_exceed_sample_size(context):
    client = context["client"]
    access = token(client, "quality@test.jp")
    response = client.post("/api/v1/quality/inspections", headers={"Authorization": f"Bearer {access}"}, json={
        "inspection_number": "QI-SAMPLE-INVALID", "product_name": "Steel", "result": "PASS", "defect_count": 12, "sample_size": 10
    })
    assert response.status_code == 422


def test_new_supplier_tenant_can_be_linked_to_factory_supplier_record(context):
    client = context["client"]
    factory_token = token(client, "admin@test.jp")
    supplier_token = token(client, "supplier@test.jp")
    headers = {"Authorization": f"Bearer {factory_token}"}
    linked = client.post("/api/v1/suppliers", headers=headers, json={
        "code": "SUP-LINKED", "name": "Osaka Linked Supplier", "supplier_organization_code": "OSAKA-TEST"
    })
    assert linked.status_code == 201, linked.text
    po = client.post("/api/v1/purchase-orders", headers=headers, json={
        "supplier_id": linked.json()["id"], "po_number": "PO-LINKED-1", "item_name": "Precision steel", "quantity": 20, "unit": "kg"
    })
    assert po.status_code == 201, po.text
    supplier_orders = client.get("/api/v1/purchase-orders", headers={"Authorization": f"Bearer {supplier_token}"})
    assert supplier_orders.status_code == 200
    assert {row["po_number"] for row in supplier_orders.json()} == {"PO-TEST-1", "PO-LINKED-1"}


def test_organisation_registration_creates_first_admin(context):
    client = context["client"]
    verification = register_verification_token(client, "owner@kyoto.example")
    response = client.post("/api/v1/organizations/register", json={
        "organization_name": "Kyoto Precision Works", "organization_code": "kyoto-precision",
        "organization_type": "MANUFACTURER", "owner_name": "Yuki Tanaka",
        "email": "owner@kyoto.example", "password": "StrongLocalPass2026!", "language": "ja",
        "prefecture": "Kyoto", "postal_code": "600-8001", "email_verification_token": verification
    })
    assert response.status_code == 201, response.text
    assert response.json()["user"]["role"] == "ORG_ADMIN"
    token_value = response.json()["access_token"]
    profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_value}"})
    assert profile.status_code == 200
    assert profile.json()["organization_name"] == "Kyoto Precision Works"
    assert profile.json()["language"] == "ja"


def test_duplicate_organisation_code_is_rejected(context):
    client = context["client"]
    payload = {"organization_name": "New Factory", "organization_code": "SAKURA-TEST", "organization_type": "MANUFACTURER", "owner_name": "New Owner", "email": "newowner@example.jp", "password": "StrongLocalPass2026!", "language": "en", "email_verification_token": register_verification_token(client, "newowner@example.jp")}
    response = client.post("/api/v1/organizations/register", json=payload)
    assert response.status_code == 409


def test_supplier_to_receipt_production_quality_traceability_workflow(context):
    client = context["client"]
    supplier_access = token(client, "supplier@test.jp")
    admin_access = token(client, "admin@test.jp")
    warehouse_access = token(client, "warehouse@test.jp")
    quality_access = token(client, "quality@test.jp")
    supplier_headers = {"Authorization": f"Bearer {supplier_access}"}
    admin_headers = {"Authorization": f"Bearer {admin_access}"}
    warehouse_headers = {"Authorization": f"Bearer {warehouse_access}"}
    quality_headers = {"Authorization": f"Bearer {quality_access}"}

    # Supplier confirms the shared order.
    po = client.get("/api/v1/purchase-orders", headers=supplier_headers).json()[0]
    confirmed = client.patch(f"/api/v1/purchase-orders/{po['id']}/status", headers=supplier_headers,
                             json={"status": "CONFIRMED", "note": "Supplier confirmed the delivery window"})
    assert confirmed.status_code == 200, confirmed.text
    dispatched = client.patch(f"/api/v1/purchase-orders/{po['id']}/status", headers=supplier_headers,
                              json={"status": "IN_TRANSIT", "note": "Shipment dispatched"})
    assert dispatched.status_code == 200, dispatched.text

    # Factory receives against the exact PO, preserving supplier → PO → lot genealogy.
    receipt = client.post("/api/v1/inventory/receipts", headers=warehouse_headers, json={
        "material_name": "Steel", "lot_number": "LOT-FLOW-1", "quantity": 20,
        "unit": "kg", "unit_cost": 15, "purchase_order_id": po["id"], "reference": "GR-FLOW-1"
    })
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["purchase_order_id"] == po["id"]
    refreshed_po = client.get("/api/v1/purchase-orders", headers=admin_headers).json()[0]
    assert refreshed_po["status"] == "PARTIALLY_DELIVERED"
    assert refreshed_po["received_quantity"] == 20
    assert refreshed_po["remaining_quantity"] == 80

    # A production order reserves and then consumes stock through valid transitions.
    order = client.post("/api/v1/production/orders", headers=admin_headers, json={
        "order_number": "MO-FLOW-1", "product_name": "Precision frame", "quantity": 10,
        "material_name": "Steel", "material_required": 12
    })
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    ready = client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "READY"})
    assert ready.status_code == 200, ready.text
    assert ready.json()["reserved_batch_ids"]
    started = client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "IN_PROGRESS"})
    assert started.status_code == 200, started.text
    progress = client.patch(f"/api/v1/production/orders/{order_id}/progress", headers=admin_headers, json={
        "completed_quantity": 9, "rejected_quantity": 1
    })
    assert progress.status_code == 200, progress.text
    completed = client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "COMPLETED"})
    assert completed.status_code == 200, completed.text

    # Quality records a defect and places the source lot on hold.
    inspection = client.post("/api/v1/quality/inspections", headers=quality_headers, json={
        "inspection_number": "QI-FLOW-1", "product_name": "Precision frame", "batch_id": receipt.json()["id"],
        "result": "FAIL", "defect_count": 1, "sample_size": 10,
        "corrective_action": "Quarantine the lot and investigate the machining setup"
    })
    assert inspection.status_code == 201, inspection.text

    db = context["Session"]()
    batch = db.scalar(select(models.MaterialBatch).where(models.MaterialBatch.lot_number == "LOT-FLOW-1"))
    movements = db.scalars(select(models.InventoryMovement).where(models.InventoryMovement.batch_id == batch.id).order_by(models.InventoryMovement.created_at)).all()
    event_types = set(db.scalars(select(models.TraceabilityEvent.event_type).where(models.TraceabilityEvent.lot_number == "LOT-FLOW-1")).all())
    assert batch.status == "HOLD"
    # FIFO uses the older 5 kg test lot first, then 7 kg from this receipt.
    assert batch.quantity_on_hand == 13
    assert batch.quantity_reserved == 0
    assert [movement.movement_type for movement in movements] == ["RECEIPT", "CONSUMPTION"]
    assert movements[1].quantity == -7
    original_batch = db.scalar(select(models.MaterialBatch).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
    assert original_batch.quantity_on_hand == 0
    assert {"GOODS_RECEIVED", "PRODUCTION_RESERVED", "PRODUCTION_CONSUMED", "QUALITY_HOLD"}.issubset(event_types)
    db.close()

    trace = client.get("/api/v1/traceability/LOT-FLOW-1", headers=admin_headers)
    assert trace.status_code == 200, trace.text
    assert trace.json()["batch"]["status"] == "HOLD"


def test_inventory_adjustment_is_audited_and_cannot_overdraw_reserved_stock(context):
    client = context["client"]
    warehouse_access = token(client, "warehouse@test.jp")
    headers = {"Authorization": f"Bearer {warehouse_access}"}
    db = context["Session"]()
    batch_id = db.scalar(select(models.MaterialBatch.id).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
    db.close()

    # A quantity adjustment is recorded as a stock-ledger movement.
    adjusted = client.post("/api/v1/inventory/adjustments", headers=headers, json={
        "batch_id": batch_id, "quantity_delta": -2, "reference": "COUNT-001", "reason": "Cycle-count correction"
    })
    assert adjusted.status_code == 201, adjusted.text
    assert adjusted.json()["quantity_on_hand"] == 3

    # Reserve two units through the production workflow, then prevent an adjustment below reservations.
    admin_access = token(client, "admin@test.jp")
    order = client.post("/api/v1/production/orders", headers={"Authorization": f"Bearer {admin_access}"}, json={
        "order_number": "MO-ADJUST-1", "product_name": "Bracket", "quantity": 1,
        "material_name": "Steel", "material_required": 2
    })
    assert order.status_code == 201, order.text
    ready = client.patch(f"/api/v1/production/orders/{order.json()['id']}/status", headers={"Authorization": f"Bearer {admin_access}"}, json={"status": "READY"})
    assert ready.status_code == 200, ready.text

    blocked = client.post("/api/v1/inventory/adjustments", headers=headers, json={
        "batch_id": batch_id, "quantity_delta": -2, "reference": "COUNT-002", "reason": "Attempt below reserved stock"
    })
    assert blocked.status_code == 409

    db = context["Session"]()
    batch = db.get(models.MaterialBatch, batch_id)
    assert batch.quantity_on_hand == 3
    assert batch.quantity_reserved == 2
    movements = db.scalars(select(models.InventoryMovement).where(models.InventoryMovement.batch_id == batch_id)).all()
    assert any(m.movement_type == "ADJUSTMENT_OUT" and m.quantity == -2 for m in movements)
    db.close()


def test_quality_hold_after_reservation_blocks_production_consumption(context):
    client = context["client"]
    admin_access = token(client, "admin@test.jp")
    quality_access = token(client, "quality@test.jp")
    db = context["Session"]()
    batch_id = db.scalar(select(models.MaterialBatch.id).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
    db.close()

    order = client.post("/api/v1/production/orders", headers={"Authorization": f"Bearer {admin_access}"}, json={
        "order_number": "MO-HOLD-1", "product_name": "Bracket", "quantity": 2,
        "material_name": "Steel", "material_required": 2
    })
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    assert client.patch(f"/api/v1/production/orders/{order_id}/status", headers={"Authorization": f"Bearer {admin_access}"}, json={"status": "READY"}).status_code == 200
    assert client.patch(f"/api/v1/production/orders/{order_id}/status", headers={"Authorization": f"Bearer {admin_access}"}, json={"status": "IN_PROGRESS"}).status_code == 200

    held = client.post("/api/v1/quality/inspections", headers={"Authorization": f"Bearer {quality_access}"}, json={
        "inspection_number": "QI-HOLD-1", "product_name": "Steel", "batch_id": batch_id,
        "result": "FAIL", "defect_count": 1, "sample_size": 5, "corrective_action": "Quarantine the source lot"
    })
    assert held.status_code == 201, held.text

    completed = client.patch(f"/api/v1/production/orders/{order_id}/status", headers={"Authorization": f"Bearer {admin_access}"}, json={"status": "COMPLETED"})
    assert completed.status_code == 409
    db = context["Session"]()
    order_row = db.get(models.ProductionOrder, order_id)
    assert order_row.status == "IN_PROGRESS"
    assert order_row.reserved_batch_ids
    db.close()



def test_purchase_order_linked_partial_receipts_track_cumulative_delivery(context):
    client = context["client"]
    supplier_access = token(client, "supplier@test.jp")
    warehouse_access = token(client, "warehouse@test.jp")
    supplier_headers = {"Authorization": f"Bearer {supplier_access}"}
    warehouse_headers = {"Authorization": f"Bearer {warehouse_access}"}

    po = client.get("/api/v1/purchase-orders", headers=supplier_headers).json()[0]
    confirmed = client.patch(f"/api/v1/purchase-orders/{po['id']}/status", headers=supplier_headers,
                             json={"status": "CONFIRMED", "note": "Confirmed"})
    assert confirmed.status_code == 200, confirmed.text
    premature_receipt = client.post("/api/v1/inventory/receipts", headers=warehouse_headers, json={
        "material_name": "Steel", "lot_number": "LOT-PRE-DISPATCH", "quantity": 1,
        "unit": "kg", "unit_cost": 10, "purchase_order_id": po["id"], "reference": "GR-PRE-DISPATCH"
    })
    assert premature_receipt.status_code == 409
    dispatched = client.patch(f"/api/v1/purchase-orders/{po['id']}/status", headers=supplier_headers,
                              json={"status": "IN_TRANSIT", "note": "Dispatched"})
    assert dispatched.status_code == 200, dispatched.text

    first = client.post("/api/v1/inventory/receipts", headers=warehouse_headers, json={
        "material_name": "Steel", "lot_number": "LOT-PO-RECEIPT-1", "quantity": 60,
        "unit": "kg", "unit_cost": 10, "purchase_order_id": po["id"], "reference": "GR-PO-001"
    })
    assert first.status_code == 201, first.text
    assert first.json()["purchase_order_id"] == po["id"]
    factory_order = client.get("/api/v1/purchase-orders", headers={"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}).json()[0]
    assert factory_order["status"] == "PARTIALLY_DELIVERED"
    assert factory_order["received_quantity"] == 60
    assert factory_order["remaining_quantity"] == 40
    # Supplier tenant can read the PO receipt total without reading factory
    # material batches or the inventory movement ledger.
    supplier_order = client.get("/api/v1/purchase-orders", headers=supplier_headers).json()[0]
    assert supplier_order["received_quantity"] == 60
    assert supplier_order["remaining_quantity"] == 40
    assert client.get("/api/v1/inventory/batches", headers=supplier_headers).status_code == 403

    # The supplier can dispatch the outstanding quantity after a partial receipt.
    redispatched = client.patch(f"/api/v1/purchase-orders/{po['id']}/status", headers=supplier_headers,
                                json={"status": "IN_TRANSIT", "note": "Remaining quantity dispatched"})
    assert redispatched.status_code == 200, redispatched.text
    second = client.post("/api/v1/inventory/receipts", headers=warehouse_headers, json={
        "material_name": "Steel", "lot_number": "LOT-PO-RECEIPT-2", "quantity": 40,
        "unit": "kg", "unit_cost": 10, "purchase_order_id": po["id"], "reference": "GR-PO-002"
    })
    assert second.status_code == 201, second.text
    factory_order = client.get("/api/v1/purchase-orders", headers={"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}).json()[0]
    assert factory_order["status"] == "DELIVERED"
    supplier_order = client.get("/api/v1/purchase-orders", headers=supplier_headers).json()[0]
    assert supplier_order["received_quantity"] == 100
    assert supplier_order["remaining_quantity"] == 0

    over_receipt = client.post("/api/v1/inventory/receipts", headers=warehouse_headers, json={
        "material_name": "Steel", "lot_number": "LOT-PO-RECEIPT-3", "quantity": 1,
        "unit": "kg", "unit_cost": 10, "purchase_order_id": po["id"], "reference": "GR-PO-003"
    })
    assert over_receipt.status_code == 409

    # Supplier cannot self-certify delivery; only warehouse receipts close the order.
    supplier_attempt = client.patch(f"/api/v1/purchase-orders/{po['id']}/status", headers=supplier_headers,
                                    json={"status": "DELIVERED"})
    assert supplier_attempt.status_code == 403


def test_purchase_order_receipt_rejects_unit_mismatch(context):
    client = context["client"]
    access = token(client, "warehouse@test.jp")
    response = client.post("/api/v1/inventory/receipts", headers={"Authorization": f"Bearer {access}"}, json={
        "material_name": "Steel", "lot_number": "LOT-BAD-UNIT", "quantity": 5,
        "unit": "pcs", "reference": "GR-BAD-UNIT"
    })
    assert response.status_code == 409



def test_quality_hold_requires_latest_documented_pass_before_release(context):
    client = context["client"]
    admin_access = token(client, "admin@test.jp")
    quality_access = token(client, "quality@test.jp")
    warehouse_access = token(client, "warehouse@test.jp")
    quality_headers = {"Authorization": f"Bearer {quality_access}"}
    admin_headers = {"Authorization": f"Bearer {admin_access}"}
    warehouse_headers = {"Authorization": f"Bearer {warehouse_access}"}
    db = context["Session"]()
    batch = db.scalar(select(models.MaterialBatch).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
    batch_id = batch.id
    db.close()

    failed = client.post("/api/v1/quality/inspections", headers=quality_headers, json={
        "inspection_number": "QI-RELEASE-FAIL", "product_name": "Steel", "batch_id": batch_id,
        "result": "FAIL", "defect_count": 1, "sample_size": 5,
        "corrective_action": "Replace the worn tool and isolate affected pieces"
    })
    assert failed.status_code == 201, failed.text
    no_pass = client.post("/api/v1/quality/batches/{}/release".format(batch_id), headers=admin_headers,
                          json={"inspection_id": failed.json()["id"], "reason": "Attempt release without a passing reinspection"})
    assert no_pass.status_code == 409

    undocumented_pass = client.post("/api/v1/quality/inspections", headers=quality_headers, json={
        "inspection_number": "QI-RELEASE-UNDOCUMENTED", "product_name": "Steel", "batch_id": batch_id,
        "result": "PASS", "defect_count": 0, "sample_size": 10
    })
    assert undocumented_pass.status_code == 201, undocumented_pass.text
    undocumented_release = client.post(f"/api/v1/quality/batches/{batch_id}/release", headers=admin_headers,
        json={"inspection_id": undocumented_pass.json()["id"], "reason": "Attempt release without documented inspection notes"})
    assert undocumented_release.status_code == 409

    passing = client.post("/api/v1/quality/inspections", headers=quality_headers, json={
        "inspection_number": "QI-RELEASE-PASS", "product_name": "Steel", "batch_id": batch_id,
        "result": "PASS", "defect_count": 0, "sample_size": 10,
        "notes": "Re-inspection passed after tool replacement; all measured dimensions are within the approved range."
    })
    assert passing.status_code == 201, passing.text
    denied_warehouse = client.post(f"/api/v1/quality/batches/{batch_id}/release", headers=warehouse_headers,
        json={"inspection_id": passing.json()["id"], "reason": passing.json()["notes"]})
    assert denied_warehouse.status_code == 403

    released = client.post(f"/api/v1/quality/batches/{batch_id}/release", headers=admin_headers,
        json={"inspection_id": passing.json()["id"], "reason": "QA approved release after documented passing reinspection"})
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "AVAILABLE"
    trace = client.get("/api/v1/traceability/LOT-TEST-1", headers=admin_headers)
    assert "QUALITY_RELEASED" in {event["event_type"] for event in trace.json()["events"]}


def test_quality_hold_cannot_be_released_when_a_newer_failure_exists(context):
    client = context["client"]
    quality_headers = {"Authorization": f"Bearer {token(client, 'quality@test.jp')}"}
    admin_headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    db = context["Session"]()
    batch_id = db.scalar(select(models.MaterialBatch.id).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
    db.close()
    first_pass = client.post("/api/v1/quality/inspections", headers=quality_headers, json={
        "inspection_number": "QI-STALE-PASS", "product_name": "Steel", "batch_id": batch_id,
        "result": "PASS", "defect_count": 0, "sample_size": 5, "notes": "Initial pass record."
    })
    assert first_pass.status_code == 201, first_pass.text
    newer_fail = client.post("/api/v1/quality/inspections", headers=quality_headers, json={
        "inspection_number": "QI-NEWER-FAIL", "product_name": "Steel", "batch_id": batch_id,
        "result": "FAIL", "defect_count": 1, "sample_size": 5, "corrective_action": "Investigate newly detected defect"
    })
    assert newer_fail.status_code == 201, newer_fail.text
    rejected = client.post(f"/api/v1/quality/batches/{batch_id}/release", headers=admin_headers,
        json={"inspection_id": first_pass.json()["id"], "reason": "Attempt to release using a stale passing inspection"})
    assert rejected.status_code == 409


def test_passing_quality_inspection_cannot_record_nonzero_defects(context):
    client = context["client"]
    headers = {"Authorization": f"Bearer {token(client, 'quality@test.jp')}"}
    rejected = client.post("/api/v1/quality/inspections", headers=headers, json={
        "inspection_number": "QI-PASS-WITH-DEFECT", "product_name": "Steel",
        "result": "PASS", "defect_count": 1, "sample_size": 10, "notes": "Inconsistent pass result"
    })
    assert rejected.status_code == 422


def test_cancel_in_progress_order_releases_stock_reserved_on_quality_hold(context):
    client = context["client"]
    admin_access = token(client, "admin@test.jp")
    quality_access = token(client, "quality@test.jp")
    admin_headers = {"Authorization": f"Bearer {admin_access}"}
    quality_headers = {"Authorization": f"Bearer {quality_access}"}
    db = context["Session"]()
    batch_id = db.scalar(select(models.MaterialBatch.id).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
    db.close()

    created = client.post("/api/v1/production/orders", headers=admin_headers, json={
        "order_number": "MO-CANCEL-HELD", "product_name": "Test frame", "quantity": 2,
        "material_name": "Steel", "material_required": 2
    })
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    assert client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "READY"}).status_code == 200
    assert client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "IN_PROGRESS"}).status_code == 200

    failed = client.post("/api/v1/quality/inspections", headers=quality_headers, json={
        "inspection_number": "QI-CANCEL-HELD", "product_name": "Steel", "batch_id": batch_id,
        "result": "FAIL", "defect_count": 1, "sample_size": 5, "corrective_action": "Quarantine and investigate"
    })
    assert failed.status_code == 201, failed.text

    cancelled = client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "CANCELLED"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
    db = context["Session"]()
    batch = db.get(models.MaterialBatch, batch_id)
    order = db.get(models.ProductionOrder, order_id)
    assert batch.quantity_reserved == 0
    assert batch.quantity_on_hand == 5
    assert order.reserved_batch_ids == ""
    db.close()


def test_purchase_order_document_is_shared_only_with_linked_supplier(context, monkeypatch, tmp_path):
    from app import main as app_main
    monkeypatch.setattr(app_main.settings, "upload_dir", str(tmp_path))
    client = context["client"]
    admin_access = token(client, "admin@test.jp")
    supplier_access = token(client, "supplier@test.jp")
    other_access = token(client, "other@test.jp")
    db = context["Session"]()
    linked_po_id = db.scalar(select(models.PurchaseOrder.id).where(models.PurchaseOrder.po_number == "PO-TEST-1"))
    supplier_org = db.scalar(select(models.Organization).where(models.Organization.code == "OSAKA-TEST"))
    factory_id = db.scalar(select(models.Organization.id).where(models.Organization.code == "SAKURA-TEST"))
    other_supplier = models.Supplier(organization_id=factory_id, code="SUP-NOT-LINKED", name="Unlinked supplier")
    db.add(other_supplier); db.flush()
    unlinked_po = models.PurchaseOrder(organization_id=factory_id, supplier_id=other_supplier.id,
        po_number="PO-NOT-LINKED", item_name="Aluminium", quantity=5, unit="kg", status="SUBMITTED")
    db.add(unlinked_po); db.commit(); unlinked_po_id = unlinked_po.id
    db.close()

    uploaded = client.post("/api/v1/documents", headers={"Authorization": f"Bearer {admin_access}"},
        data={"purchase_order_id": str(linked_po_id)},
        files={"file": ("inspection.pdf", b"%PDF-1.7\nFactoryLink test document", "application/octet-stream")})
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]

    supplier_docs = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {supplier_access}"})
    assert supplier_docs.status_code == 200
    assert [row["id"] for row in supplier_docs.json()] == [document_id]
    downloaded = client.get(f"/api/v1/documents/{document_id}/download", headers={"Authorization": f"Bearer {supplier_access}"})
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"%PDF-")
    assert downloaded.headers["content-type"].startswith("application/pdf")

    denied = client.post("/api/v1/documents", headers={"Authorization": f"Bearer {supplier_access}"},
        data={"purchase_order_id": str(unlinked_po_id)},
        files={"file": ("other.pdf", b"%PDF-1.7\nprivate", "application/pdf")})
    assert denied.status_code == 403
    other_download = client.get(f"/api/v1/documents/{document_id}/download", headers={"Authorization": f"Bearer {other_access}"})
    assert other_download.status_code == 403
    assert len(list(tmp_path.iterdir())) == 1


def test_document_upload_rejects_fake_pdf_content(context, monkeypatch, tmp_path):
    from app import main as app_main
    monkeypatch.setattr(app_main.settings, "upload_dir", str(tmp_path))
    client = context["client"]
    access = token(client, "admin@test.jp")
    response = client.post("/api/v1/documents", headers={"Authorization": f"Bearer {access}"},
        files={"file": ("not-a-pdf.pdf", b"this is not a PDF", "application/pdf")})
    assert response.status_code == 415
    assert list(tmp_path.iterdir()) == []


def test_document_upload_rejects_malware_before_persistence(context, monkeypatch, tmp_path):
    from app import main as app_main
    from app.malware_scanner import MalwareDetected
    monkeypatch.setattr(app_main.settings, "malware_scan_enabled", True)
    monkeypatch.setattr(app_main.settings, "upload_dir", str(tmp_path))

    def infected(_content):
        raise MalwareDetected("test signature")

    monkeypatch.setattr(app_main, "scan_document_bytes", infected)
    client = context["client"]
    access = token(client, "admin@test.jp")
    response = client.post("/api/v1/documents", headers={"Authorization": f"Bearer {access}"},
        files={"file": ("inspection.pdf", b"%PDF-1.7\nEICAR test payload", "application/pdf")})
    assert response.status_code == 422
    assert "malware" in response.json()["detail"].lower()
    assert list(tmp_path.iterdir()) == []
    db = context["Session"]()
    assert db.scalars(select(models.Attachment)).all() == []
    db.close()


def test_document_upload_fails_closed_when_scanner_is_unavailable(context, monkeypatch, tmp_path):
    from app import main as app_main
    from app.malware_scanner import MalwareScannerUnavailable
    monkeypatch.setattr(app_main.settings, "malware_scan_enabled", True)
    monkeypatch.setattr(app_main.settings, "upload_dir", str(tmp_path))

    def unavailable(_content):
        raise MalwareScannerUnavailable("scanner down")

    monkeypatch.setattr(app_main, "scan_document_bytes", unavailable)
    client = context["client"]
    access = token(client, "admin@test.jp")
    response = client.post("/api/v1/documents", headers={"Authorization": f"Bearer {access}"},
        files={"file": ("inspection.pdf", b"%PDF-1.7\nFactoryLink document", "application/pdf")})
    assert response.status_code == 503
    assert "scanning" in response.json()["detail"].lower()
    assert list(tmp_path.iterdir()) == []
    db = context["Session"]()
    assert db.scalars(select(models.Attachment)).all() == []
    db.close()


def test_workspace_registration_can_be_disabled(context, monkeypatch):
    client = context["client"]
    verification = register_verification_token(client, "blocked@example.com")
    monkeypatch.setattr(main_module.settings, "allow_public_registration", False)
    response = client.post("/api/v1/organizations/register", json={
        "organization_name": "Blocked Registration Works", "organization_code": "BLOCKED-REG",
        "organization_type": "MANUFACTURER", "owner_name": "Test Owner",
        "email": "blocked@example.com", "password": "StrongLocalPass2026!", "language": "en",
        "email_verification_token": verification,
    })
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()
    check = context["Session"]()
    assert check.scalar(select(models.Organization).where(models.Organization.code == "BLOCKED-REG")) is None
    check.close()


def configure_valid_production_settings(monkeypatch):
    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "jwt_secret_key", "unique-production-secret-with-more-than-32-bytes")
    monkeypatch.setattr(main_module.settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(main_module.settings, "database_url", "postgresql+psycopg://factorylink_app:runtime-secret@db.example.jp:5432/factorylink?sslmode=verify-full")
    monkeypatch.setattr(main_module.settings, "cors_origins", "https://factory.example.jp")
    monkeypatch.setattr(main_module.settings, "allow_public_registration", False)
    monkeypatch.setattr(main_module.settings, "seed_demo_data", False)
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", False)
    monkeypatch.setattr(main_module.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(main_module.settings, "rate_limit_fail_closed", True)
    monkeypatch.setattr(main_module.settings, "smtp_host", "smtp.example.jp")
    monkeypatch.setattr(main_module.settings, "smtp_from", "FactoryLink <no-reply@example.jp>")
    monkeypatch.setattr(main_module.settings, "smtp_starttls", True)
    monkeypatch.setattr(main_module.settings, "smtp_username", "")
    monkeypatch.setattr(main_module.settings, "smtp_password", "")
    monkeypatch.setattr(main_module.settings, "frontend_base_url", "https://factory.example.jp")
    monkeypatch.setattr(main_module.settings, "storage_provider", "s3")
    monkeypatch.setattr(main_module.settings, "storage_s3_bucket", "factorylink-test-documents")
    monkeypatch.setattr(main_module.settings, "storage_s3_region", "ap-northeast-1")
    monkeypatch.setattr(main_module.settings, "storage_s3_endpoint_url", "")
    monkeypatch.setattr(main_module.settings, "storage_s3_access_key_id", "test-access-key")
    monkeypatch.setattr(main_module.settings, "storage_s3_secret_access_key", "test-secret-key")
    monkeypatch.setattr(main_module.settings, "malware_scan_enabled", True)
    monkeypatch.setattr(main_module.settings, "malware_scanner_host", "clamav.internal")
    monkeypatch.setattr(main_module.settings, "malware_scanner_port", 3310)
    monkeypatch.setattr(main_module.settings, "malware_scanner_timeout_seconds", 30.0)


def test_production_startup_rejects_public_registration_and_demo_seed(context, monkeypatch):
    from fastapi.testclient import TestClient

    configure_valid_production_settings(monkeypatch)
    monkeypatch.setattr(main_module.settings, "allow_public_registration", True)
    monkeypatch.setattr(main_module.settings, "seed_demo_data", False)
    with pytest.raises(RuntimeError, match="ALLOW_PUBLIC_REGISTRATION=false"):
        with TestClient(app):
            pass

    monkeypatch.setattr(main_module.settings, "allow_public_registration", False)
    monkeypatch.setattr(main_module.settings, "seed_demo_data", True)
    with pytest.raises(RuntimeError, match="SEED_DEMO_DATA=false"):
        with TestClient(app):
            pass


def test_production_startup_requires_antivirus_scanning(context, monkeypatch):
    from fastapi.testclient import TestClient
    configure_valid_production_settings(monkeypatch)
    monkeypatch.setattr(main_module.settings, "malware_scan_enabled", False)
    with pytest.raises(RuntimeError, match="MALWARE_SCAN_ENABLED=true"):
        with TestClient(app):
            pass


def test_production_startup_accepts_locked_down_configuration(context, monkeypatch):
    from fastapi.testclient import TestClient

    configure_valid_production_settings(monkeypatch)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_production_startup_rejects_development_action_links(context, monkeypatch):
    from fastapi.testclient import TestClient
    configure_valid_production_settings(monkeypatch)
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", True)
    with pytest.raises(RuntimeError, match="EXPOSE_AUTH_ACTION_LINKS=false"):
        with TestClient(app):
            pass


def test_production_startup_requires_smtp(context, monkeypatch):
    from fastapi.testclient import TestClient
    configure_valid_production_settings(monkeypatch)
    monkeypatch.setattr(main_module.settings, "smtp_host", "")
    monkeypatch.setattr(main_module.settings, "resend_api_key", "")
    with pytest.raises(RuntimeError, match="email delivery"):
        with TestClient(app):
            pass



@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("jwt_algorithm", "HS512", "JWT_ALGORITHM=HS256"),
        ("database_url", "postgresql+psycopg://app:secret@db:5432/factorylink", "sslmode=require"),
        ("database_url", "sqlite:///./factorylink.db", "postgresql[+]psycopg DATABASE_URL"),
        ("cors_origins", "http://factory.example.jp", "HTTPS-only CORS_ORIGINS"),
        ("cors_origins", "https://factory.example.jp/path", "HTTPS-only CORS_ORIGINS"),
        ("smtp_starttls", False, "SMTP_STARTTLS=true"),
        ("smtp_password", "orphan-password", "USERNAME and SMTP_PASSWORD"),
    ],
)
def test_production_startup_rejects_unsafe_transport_or_crypto_settings(context, monkeypatch, field, value, expected):
    from fastapi.testclient import TestClient
    configure_valid_production_settings(monkeypatch)
    monkeypatch.setattr(main_module.settings, field, value)
    with pytest.raises(RuntimeError, match=expected):
        with TestClient(app):
            pass


def test_nginx_emits_restrictive_browser_security_headers():
    from pathlib import Path
    nginx = (Path(__file__).resolve().parents[2] / "frontend/nginx/default.conf.template").read_text(encoding="utf-8")
    assert "default-src 'self'" in nginx
    assert "object-src 'none'" in nginx
    assert "frame-ancestors 'none'" in nginx
    assert "script-src 'self'" in nginx
    assert "Strict-Transport-Security $factorylink_hsts always" in nginx
    assert 'https "max-age=31536000"' in nginx


def test_tenant_context_is_retained_across_session_commits(context):
    db = context["Session"]()
    try:
        set_tenant_context(db, 456)
        assert db.info["tenant_org_id"] == 456
        db.execute(select(1))
        db.commit()
        # The PostgreSQL after_begin hook uses this retained value to reapply
        # SET LOCAL after a handler commits and then starts another transaction.
        db.execute(select(1))
        db.commit()
        assert db.info["tenant_org_id"] == 456
    finally:
        db.close()


def test_rls_migration_covers_every_operational_tenant_model():
    import importlib.util
    from pathlib import Path

    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "0004_postgresql_tenant_rls.py"
    spec = importlib.util.spec_from_file_location("factorylink_rls_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    special_policy_tables = {"suppliers", "purchase_orders", "notifications", "attachments"}
    protected = set(migration.TENANT_TABLES) | special_policy_tables
    # Core workflow tables introduced after RC6 receive their own additive RLS migration.
    latest_path = Path(__file__).parents[1] / "migrations" / "versions" / "0007_quality_capa_serial_traceability.py"
    latest_spec = importlib.util.spec_from_file_location("factorylink_latest_rls_migration", latest_path)
    latest_migration = importlib.util.module_from_spec(latest_spec)
    latest_spec.loader.exec_module(latest_migration)
    protected |= set(latest_migration.TENANT_TABLES)
    finished_quality_path = Path(__file__).parents[1] / "migrations" / "versions" / "0009_finished_product_quality.py"
    finished_quality_spec = importlib.util.spec_from_file_location("factorylink_finished_quality_migration", finished_quality_path)
    finished_quality_migration = importlib.util.module_from_spec(finished_quality_spec)
    finished_quality_spec.loader.exec_module(finished_quality_migration)
    protected.add(finished_quality_migration.TENANT_TABLE)
    protected.add("inventory_reconciliations")
    # `users` is deliberately excluded because login and refresh-token flows
    # need a narrowly controlled identity lookup before tenant context exists.
    expected = {
        table_name for table_name, table in Base.metadata.tables.items()
        if "organization_id" in table.c and table_name not in {"users", "auth_action_tokens"}
    }
    assert protected == expected
    assert migration.down_revision == "0003_refresh_token_families"


def test_runtime_role_bootstrap_is_non_owner_and_rls_restricted():
    from pathlib import Path

    sql = (Path(__file__).parents[2] / "scripts" / "db" / "create-runtime-role.sql").read_text(encoding="utf-8")
    normalized = " ".join(sql.upper().split())
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT" in normalized
    assert "GRANT USAGE ON SCHEMA PUBLIC" in normalized
    assert "REVOKE CREATE ON SCHEMA PUBLIC" in normalized
    assert "ALTER DEFAULT PRIVILEGES" in normalized
    assert "GRANT SELECT, INSERT ON TABLES" in normalized
    assert "GRANT USAGE, SELECT ON SEQUENCES" in normalized


def test_runtime_update_grants_are_column_limited_and_ledgers_append_only():
    import importlib.util
    from pathlib import Path

    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "0004_postgresql_tenant_rls.py"
    spec = importlib.util.spec_from_file_location("factorylink_rls_grants", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.RUNTIME_UPDATE_COLUMNS["purchase_orders"] == ("status", "supplier_note")
    assert migration.RUNTIME_UPDATE_COLUMNS["notifications"] == ("is_read",)
    assert "inventory_movements" not in migration.RUNTIME_UPDATE_COLUMNS
    assert "audit_logs" not in migration.RUNTIME_UPDATE_COLUMNS
    assert "traceability_events" not in migration.RUNTIME_UPDATE_COLUMNS
    assert set(migration.APPLICATION_TABLES) == {
        "organizations", "users", "refresh_tokens", "suppliers", "purchase_orders",
        "material_batches", "inventory_movements", "production_orders", "quality_inspections",
        "equipment", "maintenance_tasks", "traceability_events", "audit_logs", "notifications", "attachments",
    }


def test_postgres_acceptance_scripts_are_explicit_and_rollback_demo_changes():
    from pathlib import Path

    root = Path(__file__).parents[2]
    rls = (root / "scripts" / "db" / "verify-rls.sql").read_text(encoding="utf-8").upper()
    role = (root / "scripts" / "db" / "verify-runtime-role.sql").read_text(encoding="utf-8").upper()
    assert "SET LOCAL ROLE" in rls
    assert "ROLLBACK;" in rls
    assert "TOKYO-IND" in rls and "SAKURA-JP" in rls and "OSAKA-SUP" in rls
    assert "UPDATE PURCHASE_ORDERS SET QUANTITY" in rls
    assert "DELETE FROM PURCHASE_ORDERS" in rls
    assert "ROLBYPASSRLS" in role
    assert "CAN_UPDATE_PO_QUANTITY" in role
    assert "CAN_WRITE_ALEMBIC_VERSION" in role


def _extract_action_token(action_link: str) -> str:
    from urllib.parse import urlparse, parse_qs
    values = parse_qs(urlparse(action_link).query).get("token", [])
    assert len(values) == 1 and values[0]
    return values[0]


def test_password_reset_is_generic_one_time_and_revokes_refresh_sessions(context, monkeypatch):
    client = context["client"]
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", True)
    monkeypatch.setattr(main_module, "queue_action_email", lambda *args, **kwargs: False)

    original_session = client.post("/api/v1/auth/login", json={"email": "admin@test.jp", "password": "FactoryLink2026!"}).json()
    requested = client.post("/api/v1/auth/password-reset/request", json={"email": "admin@test.jp"})
    assert requested.status_code == 202
    assert "development_action_link" in requested.json()
    token_value = _extract_action_token(requested.json()["development_action_link"])

    unknown = client.post("/api/v1/auth/password-reset/request", json={"email": "not-registered@test.jp"})
    assert unknown.status_code == 202
    assert unknown.json()["message"] == requested.json()["message"]
    assert "development_action_link" not in unknown.json()

    changed = client.post("/api/v1/auth/password-reset/confirm", json={
        "token": token_value, "password": "NewStrongPass2026!"
    })
    assert changed.status_code == 200, changed.text
    assert client.post("/api/v1/auth/password-reset/confirm", json={
        "token": token_value, "password": "AnotherStrongPass2026!"
    }).status_code == 400
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": original_session["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "admin@test.jp", "password": "NewStrongPass2026!"}).status_code == 200


def test_user_invitation_creates_inactive_account_then_accepts_once(context, monkeypatch):
    client = context["client"]
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", True)
    monkeypatch.setattr(main_module, "queue_action_email", lambda *args, **kwargs: False)
    headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    invitation = client.post("/api/v1/users/invitations", headers=headers, json={
        "email": "new.operator@test.jp", "full_name": "New Operator", "role": "OPERATOR", "language": "en"
    })
    assert invitation.status_code == 202, invitation.text
    assert invitation.json()["status"] == "INVITED"
    assert "development_action_link" in invitation.json()
    assert client.post("/api/v1/auth/login", json={"email": "new.operator@test.jp", "password": "FactoryLink2026!"}).status_code == 401

    action_token = _extract_action_token(invitation.json()["development_action_link"])
    accepted = client.post("/api/v1/users/invitations/accept", json={
        "token": action_token, "password": "InvitedOperator2026!"
    })
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["user"]["role"] == "OPERATOR"
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {accepted.json()['access_token']}"}).status_code == 200
    assert client.post("/api/v1/users/invitations/accept", json={
        "token": action_token, "password": "ReplayPassword2026!"
    }).status_code == 400


def test_only_organisation_admin_can_invite_users(context):
    client = context["client"]
    headers = {"Authorization": f"Bearer {token(client, 'warehouse@test.jp')}"}
    response = client.post("/api/v1/users/invitations", headers=headers, json={
        "email": "blocked.operator@test.jp", "full_name": "Blocked Operator", "role": "OPERATOR", "language": "en"
    })
    assert response.status_code == 403


def test_invitation_role_must_match_organisation_type(context, monkeypatch):
    client = context["client"]
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", True)
    monkeypatch.setattr(main_module, "queue_action_email", lambda *args, **kwargs: False)
    headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    response = client.post("/api/v1/users/invitations", headers=headers, json={
        "email": "bad.role@test.jp", "full_name": "Wrong Role", "role": "SUPPLIER_USER", "language": "en"
    })
    assert response.status_code == 422


def test_direct_password_assignment_endpoint_is_disabled(context):
    client = context["client"]
    headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    response = client.post("/api/v1/users", headers=headers, json={
        "email": "direct@test.jp", "full_name": "Direct User", "password": "PasswordForDirectUser2026!", "role": "OPERATOR"
    })
    assert response.status_code == 410


def test_expired_invitation_token_cannot_activate_account(context, monkeypatch):
    from datetime import datetime, timedelta, timezone
    client = context["client"]
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", True)
    monkeypatch.setattr(main_module, "queue_action_email", lambda *args, **kwargs: False)
    headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    created = client.post("/api/v1/users/invitations", headers=headers, json={
        "email": "expired.invite@test.jp", "full_name": "Expired Invite", "role": "OPERATOR", "language": "en"
    })
    assert created.status_code == 202
    token_value = _extract_action_token(created.json()["development_action_link"])
    check = context["Session"]()
    digest = __import__("hashlib").sha256(token_value.encode()).hexdigest()
    action = check.scalar(select(models.AuthActionToken).where(models.AuthActionToken.token_hash == digest))
    action.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    check.commit(); check.close()
    failed = client.post("/api/v1/users/invitations/accept", json={"token": token_value, "password": "NewInvitePassword2026!"})
    assert failed.status_code == 400
    check = context["Session"]()
    invited = check.scalar(select(models.User).where(models.User.email == "expired.invite@test.jp"))
    assert invited is not None and invited.is_active is False
    check.close()


def test_action_token_cannot_be_redeemed_for_another_purpose(context, monkeypatch):
    client = context["client"]
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", True)
    monkeypatch.setattr(main_module, "queue_action_email", lambda *args, **kwargs: False)
    headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    invitation = client.post("/api/v1/users/invitations", headers=headers, json={
        "email": "purpose.check@test.jp", "full_name": "Purpose Check", "role": "OPERATOR", "language": "en"
    })
    action_token = _extract_action_token(invitation.json()["development_action_link"])
    response = client.post("/api/v1/auth/password-reset/confirm", json={
        "token": action_token, "password": "UnrelatedPurpose2026!"
    })
    assert response.status_code == 400


def test_development_action_links_are_never_exposed_outside_development(context, monkeypatch):
    client = context["client"]
    monkeypatch.setattr(main_module.settings, "environment", "staging")
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", True)
    monkeypatch.setattr(main_module, "queue_action_email", lambda *args, **kwargs: False)
    response = client.post("/api/v1/auth/password-reset/request", json={"email": "admin@test.jp"})
    assert response.status_code == 202
    assert "development_action_link" not in response.json()


def test_supplier_workspace_owner_is_supplier_admin_and_can_invite_members(context, monkeypatch):
    client = context["client"]
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(main_module.settings, "expose_auth_action_links", True)
    monkeypatch.setattr(main_module, "queue_action_email", lambda *args, **kwargs: False)
    registered = client.post("/api/v1/organizations/register", json={
        "organization_name": "Kobe Fasteners", "organization_code": "KOBE-FASTENERS",
        "organization_type": "SUPPLIER", "owner_name": "Kobe Owner",
        "email": "owner@kobe-fasteners.jp", "password": "SupplierOwner2026!", "language": "ja",
        "email_verification_token": register_verification_token(client, "owner@kobe-fasteners.jp"),
    })
    assert registered.status_code == 201, registered.text
    assert registered.json()["user"]["role"] == "SUPPLIER_ADMIN"
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    assert client.get("/api/v1/users", headers=headers).status_code == 200
    invite = client.post("/api/v1/users/invitations", headers=headers, json={
        "email": "operator@kobe-fasteners.jp", "full_name": "Kobe Operator", "role": "SUPPLIER_USER", "language": "ja"
    })
    assert invite.status_code == 202, invite.text
    invitation_token = _extract_action_token(invite.json()["development_action_link"])
    accepted = client.post("/api/v1/users/invitations/accept", json={
        "token": invitation_token, "password": "KobeOperator2026!"
    })
    assert accepted.status_code == 200
    assert accepted.json()["user"]["role"] == "SUPPLIER_USER"
    assert client.get("/api/v1/inventory/batches", headers={"Authorization": f"Bearer {registered.json()['access_token']}"}).status_code == 403


def test_supplier_admin_access_is_supplier_scoped(context):
    db = context["Session"]()
    supplier_org = db.scalar(select(models.Organization).where(models.Organization.code == "OSAKA-TEST"))
    admin = models.User(
        organization_id=supplier_org.id, email="supplier-admin@test.jp", full_name="Supplier Admin",
        password_hash=hash_password("FactoryLink2026!"), role="SUPPLIER_ADMIN", language="en",
    )
    db.add(admin); db.commit(); db.close()
    client = context["client"]
    access = token(client, "supplier-admin@test.jp")
    headers = {"Authorization": f"Bearer {access}"}
    purchase_orders = client.get("/api/v1/purchase-orders", headers=headers)
    assert purchase_orders.status_code == 200
    assert [row["po_number"] for row in purchase_orders.json()] == ["PO-TEST-1"]
    assert client.get("/api/v1/inventory/batches", headers=headers).status_code == 403
    assert client.get("/api/v1/users", headers=headers).status_code == 200


def test_notification_unread_count_and_mark_all_are_tenant_scoped(context):
    from app.models import Notification, Organization

    client = context["client"]
    session = context["Session"]()
    factory = session.scalar(select(Organization).where(Organization.code == "SAKURA-TEST"))
    other = session.scalar(select(Organization).where(Organization.code == "OTHER-TEST"))
    session.add_all([
        Notification(organization_id=factory.id, title="PO update", body="A supplier confirmed an order", level="INFO"),
        Notification(organization_id=factory.id, title="Quality hold", body="A batch is on hold", level="CRITICAL"),
        Notification(organization_id=other.id, title="Other tenant", body="Private notice", level="WARNING"),
    ])
    session.commit()
    session.close()

    factory_headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    other_headers = {"Authorization": f"Bearer {token(client, 'other@test.jp')}"}
    lookup = context["Session"]()
    foreign_notification_id = lookup.scalar(select(Notification.id).where(Notification.organization_id == other.id))
    lookup.close()
    assert client.patch(f"/api/v1/notifications/{foreign_notification_id}/read", headers=factory_headers).status_code == 404
    assert client.get("/api/v1/notifications/unread-count", headers=factory_headers).json() == {"unread_count": 2}
    assert client.get("/api/v1/notifications/unread-count", headers=other_headers).json() == {"unread_count": 1}

    marked = client.patch("/api/v1/notifications/read-all", headers=factory_headers)
    assert marked.status_code == 200
    assert marked.json() == {"updated": 2}
    repeated = client.patch("/api/v1/notifications/read-all", headers=factory_headers)
    assert repeated.status_code == 200 and repeated.json() == {"updated": 0}
    assert client.get("/api/v1/notifications/unread-count", headers=factory_headers).json() == {"unread_count": 0}
    assert client.get("/api/v1/notifications/unread-count", headers=other_headers).json() == {"unread_count": 1}


def test_inventory_and_quality_reports_are_downloadable_and_tenant_scoped(context):
    import csv
    from io import BytesIO, StringIO
    from openpyxl import load_workbook

    client = context["client"]
    admin_headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    other_headers = {"Authorization": f"Bearer {token(client, 'other@test.jp')}"}
    supplier_headers = {"Authorization": f"Bearer {token(client, 'supplier@test.jp')}"}

    receipt = client.post("/api/v1/inventory/receipts", headers={"Authorization": f"Bearer {token(client, 'warehouse@test.jp')}"}, json={
        "material_name": "=HYPERLINK(\"https://example.invalid\",\"open\")",
        "lot_number": "LOT-EXPORT-SAFE", "quantity": 3, "unit": "kg", "unit_cost": 25, "reference": "GR-EXPORT-SAFE"
    })
    assert receipt.status_code == 201, receipt.text

    quality = client.post("/api/v1/quality/inspections", headers={"Authorization": f"Bearer {token(client, 'quality@test.jp')}"}, json={
        "inspection_number": "QI-EXPORT-1", "product_name": "Bracket", "batch_id": receipt.json()["id"],
        "result": "FAIL", "defect_count": 1, "sample_size": 20, "corrective_action": "Contain affected lot and investigate"
    })
    assert quality.status_code == 201, quality.text

    inventory_csv = client.get("/api/v1/reports/inventory.csv", headers=admin_headers)
    assert inventory_csv.status_code == 200
    assert "LOT-EXPORT-SAFE" in inventory_csv.text
    assert "'=HYPERLINK" in inventory_csv.text
    assert "LOT-TEST-1" not in client.get("/api/v1/reports/inventory.csv", headers=other_headers).text

    inventory_xlsx = client.get("/api/v1/reports/inventory.xlsx", headers=admin_headers)
    workbook = load_workbook(BytesIO(inventory_xlsx.content), data_only=False)
    export_row = next(row for row in workbook.active.iter_rows(min_row=2) if row[1].value == "LOT-EXPORT-SAFE")
    assert export_row[0].data_type == "s"
    assert export_row[0].value.startswith("'=")

    quality_csv = client.get("/api/v1/reports/quality.csv", headers=admin_headers)
    assert quality_csv.status_code == 200
    assert "QI-EXPORT-1" in quality_csv.text
    quality_rows = list(csv.DictReader(StringIO(quality_csv.text.lstrip("\ufeff"))))
    export_quality_row = next(row for row in quality_rows if row["Inspection"] == "QI-EXPORT-1")
    assert float(export_quality_row["Defect rate %"]) == 5.0
    other_quality_csv = client.get("/api/v1/reports/quality.csv", headers=other_headers)
    assert "QI-EXPORT-1" not in other_quality_csv.text
    quality_xlsx = client.get("/api/v1/reports/quality.xlsx", headers=admin_headers)
    quality_workbook = load_workbook(BytesIO(quality_xlsx.content), data_only=False)
    quality_row = next(row for row in quality_workbook.active.iter_rows(min_row=2) if row[0].value == "QI-EXPORT-1")
    assert quality_row[6].value == 5

    for path in ("inventory.csv", "inventory.xlsx", "quality.csv", "quality.xlsx"):
        assert client.get(f"/api/v1/reports/{path}", headers=supplier_headers).status_code == 403


def test_observability_headers_metrics_and_health_probes(context, monkeypatch):
    client = context["client"]
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.headers.get("x-request-id")
    assert len(live.headers["x-request-id"]) == 32
    assert live.headers.get("x-content-type-options") == "nosniff"

    monkeypatch.setattr(main_module, "check_readiness_dependencies", lambda: {"database": "ok", "redis": "ok"})
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"database": "ok", "redis": "ok"}

    monkeypatch.setattr(main_module, "check_readiness_dependencies", lambda: {"database": "ok", "redis": "unavailable"})
    not_ready = client.get("/health/ready")
    assert not_ready.status_code == 503
    assert not_ready.json()["status"] == "not_ready"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "factorylink_http_requests_total" in metrics.text
    assert 'route="/health/live"' in metrics.text
    assert 'route="/health/ready"' in metrics.text


def test_observability_metrics_use_route_templates_not_identifier_values(context):
    client = context["client"]
    access = token(client, "admin@test.jp")
    headers = {"Authorization": f"Bearer {access}"}
    for identifier in (101, 202, 303):
        response = client.get(f"/api/v1/maintenance/tasks/{identifier}", headers=headers)
        # The endpoint is not a GET route; each request is expected to be a
        # stable 405/404, but the metric label must never contain the id.
        assert response.status_code in (404, 405)
    metrics = client.get("/metrics").text
    assert "/api/v1/maintenance/tasks/{task_id}" in metrics or 'route="unmatched"' in metrics
    assert "/api/v1/maintenance/tasks/101" not in metrics


def test_operator_bootstrap_creates_first_japanese_factory_admin_once():
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.admin_bootstrap import BootstrapError, create_first_factory_admin

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = Session()
    try:
        created = create_first_factory_admin(
            db,
            organization_name="Kobe Precision Works",
            organization_code="KOBE-PRECISION",
            admin_email="first.admin@example.jp",
            admin_name="Factory Owner",
            password="A-Unique-Production-Password-2026!",
        )
        assert created["organization_code"] == "KOBE-PRECISION"
        user = db.scalar(select(models.User).where(models.User.id == created["admin_user_id"]))
        organization = db.scalar(select(models.Organization).where(models.Organization.id == created["organization_id"]))
        audit = db.scalar(select(models.AuditLog).where(models.AuditLog.action == "FIRST_ADMIN_BOOTSTRAP"))
        assert user.role == "ORG_ADMIN" and user.language == "ja"
        assert organization.timezone == "Asia/Tokyo" and organization.currency == "JPY"
        assert audit is not None
        with pytest.raises(BootstrapError, match="only on an empty database"):
            create_first_factory_admin(
                db,
                organization_name="Second Factory",
                organization_code="SECOND-FACTORY",
                admin_email="second@example.jp",
                admin_name="Second Owner",
                password="Another-Unique-Production-Password-2026!",
            )
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_operator_bootstrap_rejects_short_or_demo_passwords():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.admin_bootstrap import BootstrapError, create_first_factory_admin

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        with pytest.raises(BootstrapError, match="14–128 characters"):
            create_first_factory_admin(
                db, organization_name="Factory", organization_code="FACTORY-1",
                admin_email="owner@example.jp", admin_name="Owner", password="short",
            )
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_s3_document_upload_and_download_use_private_object_storage(context, monkeypatch):
    from io import BytesIO
    from app import object_storage

    monkeypatch.setattr(main_module.settings, "storage_provider", "s3")
    monkeypatch.setattr(main_module.settings, "storage_s3_bucket", "factorylink-private-test")
    objects = {}

    class FakeBody:
        def __init__(self, content):
            self.stream = BytesIO(content)

        def read(self):
            return self.stream.read()

        def close(self):
            self.stream.close()

    class FakeS3:
        def put_object(self, **kwargs):
            objects[(kwargs["Bucket"], kwargs["Key"])] = {
                "content": kwargs["Body"],
                "content_type": kwargs["ContentType"],
                "metadata": kwargs.get("Metadata", {}),
            }

        def get_object(self, **kwargs):
            item = objects[(kwargs["Bucket"], kwargs["Key"])]
            return {"Body": FakeBody(item["content"])}

        def delete_object(self, **kwargs):
            objects.pop((kwargs["Bucket"], kwargs["Key"]), None)

    monkeypatch.setattr(object_storage, "_get_s3_client", lambda: FakeS3())
    client = context["client"]
    access = token(client, "admin@test.jp")
    content = b"%PDF-1.7\nPrivate S3 document"
    uploaded = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {access}"},
        files={"file": ("s3-inspection.pdf", content, "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    stored = next(iter(objects.values()))
    assert stored["content"] == content
    assert stored["metadata"]["sha256"]

    downloaded = client.get(
        f"/api/v1/documents/{document_id}/download",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert downloaded.headers["x-content-type-options"] == "nosniff"


def test_local_document_download_is_non_cacheable(context, monkeypatch, tmp_path):
    from app import object_storage

    monkeypatch.setattr(main_module.settings, "storage_provider", "local")
    monkeypatch.setattr(main_module.settings, "upload_dir", str(tmp_path / "private-uploads"))
    client = context["client"]
    access = token(client, "admin@test.jp")
    content = b"%PDF-1.7\nLocal private attachment"
    uploaded = client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {access}"},
        files={"file": ("local-inspection.pdf", content, "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    downloaded = client.get(
        f"/api/v1/documents/{uploaded.json()['id']}/download",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert downloaded.headers["x-content-type-options"] == "nosniff"


def test_production_startup_rejects_local_document_storage(context, monkeypatch):
    from fastapi.testclient import TestClient

    configure_valid_production_settings(monkeypatch)
    monkeypatch.setattr(main_module.settings, "storage_provider", "local")
    with pytest.raises(RuntimeError, match="STORAGE_PROVIDER=s3"):
        with TestClient(app):
            pass


def test_quality_template_derives_failure_and_completes_capa_lifecycle(context):
    client = context["client"]
    quality_access = token(client, "quality@test.jp")
    headers = {"Authorization": f"Bearer {quality_access}"}
    db = context["Session"]()
    batch_id = db.scalar(select(models.MaterialBatch.id).where(models.MaterialBatch.lot_number == "LOT-TEST-1"))
    db.close()

    template = client.post("/api/v1/quality/templates", headers=headers, json={
        "code": "FINAL-DIM",
        "name": "Final dimensional inspection",
        "process_type": "FINAL",
        "criteria": [
            {"key": "diameter", "label": "Diameter (mm)", "kind": "NUMERIC", "minimum": 9.95, "maximum": 10.05, "required": True},
            {"key": "surface", "label": "Surface finish", "kind": "PASS_FAIL", "required": True},
        ],
    })
    assert template.status_code == 201, template.text
    assert len(client.get("/api/v1/quality/templates", headers=headers).json()) == 1

    # The submitted overall PASS must be overridden when a measured criterion fails.
    inspection = client.post("/api/v1/quality/inspections", headers=headers, json={
        "inspection_number": "QI-TEMPLATE-FAIL", "product_name": "Precision Shaft",
        "batch_id": batch_id, "template_id": template.json()["id"], "result": "PASS",
        "defect_count": 0, "sample_size": 5,
        "corrective_action": "Segregate the lot and stop release pending investigation",
        "criteria_results": {"diameter": 10.2, "surface": "PASS"},
    })
    assert inspection.status_code == 201, inspection.text
    assert inspection.json()["result"] == "FAIL"
    assert inspection.json()["criteria_results"]["diameter"] == 10.2
    assert inspection.json()["capa"]["status"] == "OPEN"
    capa_id = inspection.json()["capa"]["id"]

    invalid_advance = client.patch(f"/api/v1/quality/capa/{capa_id}", headers=headers, json={"status": "INVESTIGATING"})
    assert invalid_advance.status_code == 409

    steps = [
        ({"status": "CONTAINED"}, "CONTAINED"),
        ({"status": "INVESTIGATING", "root_cause": "Tool offset drifted after the changeover"}, "INVESTIGATING"),
        ({"status": "IMPLEMENTED", "corrective_action": "Recalibrate and lock the tool offset", "preventive_action": "Add first-piece verification after each changeover"}, "IMPLEMENTED"),
        ({"status": "VERIFIED", "verification": "Thirty consecutive parts passed the approved gauge check"}, "VERIFIED"),
        ({"status": "CLOSED"}, "CLOSED"),
    ]
    for payload, expected in steps:
        response = client.patch(f"/api/v1/quality/capa/{capa_id}", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected

    db = context["Session"]()
    batch = db.get(models.MaterialBatch, batch_id)
    assert batch.status == "HOLD"
    db.close()

    other_headers = {"Authorization": f"Bearer {token(client, 'other@test.jp')}"}
    assert client.get("/api/v1/quality/capa", headers=other_headers).json() == []
    assert client.patch(f"/api/v1/quality/capa/{capa_id}", headers=other_headers, json={"status": "CLOSED"}).status_code == 404


def test_production_completion_creates_traceable_serials_qr_and_shipment(context):
    client = context["client"]
    admin_headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    warehouse_headers = {"Authorization": f"Bearer {token(client, 'warehouse@test.jp')}"}

    created = client.post("/api/v1/production/orders", headers=admin_headers, json={
        "order_number": "MO-SERIAL-1", "product_name": "Precision Bracket", "quantity": 2,
        "material_name": "Steel", "material_required": 2, "track_serials": True,
    })
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    # Production orders are created in PLANNED state.
    assert created.json()["status"] == "PLANNED"
    assert client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "READY"}).status_code == 200
    assert client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "IN_PROGRESS"}).status_code == 200
    progress = client.patch(f"/api/v1/production/orders/{order_id}/progress", headers=admin_headers, json={"completed_quantity": 2, "rejected_quantity": 0})
    assert progress.status_code == 200, progress.text
    completed = client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "COMPLETED"})
    assert completed.status_code == 200, completed.text

    serials = client.get("/api/v1/traceability/serials", headers=admin_headers)
    assert serials.status_code == 200, serials.text
    generated = [row for row in serials.json() if row["production_order_id"] == order_id]
    assert len(generated) == 2
    serial_number = generated[0]["serial_number"]

    serial_trace = client.get(f"/api/v1/traceability/serials/{serial_number}", headers=admin_headers)
    assert serial_trace.status_code == 200, serial_trace.text
    assert serial_trace.json()["serial"]["serial_number"] == serial_number
    assert serial_trace.json()["production_order"]["order_number"] == "MO-SERIAL-1"
    assert serial_trace.json()["sources"]

    qr = client.get(f"/api/v1/traceability/qr/serial/{serial_number}.svg", headers=admin_headers)
    assert qr.status_code == 200
    assert "image/svg+xml" in qr.headers["content-type"]
    assert b"<svg" in qr.content[:500]

    shipped = client.patch(f"/api/v1/traceability/serials/{serial_number}/shipment", headers=warehouse_headers, json={
        "customer_name": "Tokyo Industrial Customer", "shipment_reference": "SHIP-2026-001",
    })
    assert shipped.status_code == 200, shipped.text
    assert shipped.json()["status"] == "SHIPPED"
    assert shipped.json()["shipment_reference"] == "SHIP-2026-001"

    lot_trace = client.get("/api/v1/traceability/LOT-TEST-1", headers=admin_headers)
    assert lot_trace.status_code == 200, lot_trace.text
    assert any(row["serial_number"] == serial_number for row in lot_trace.json()["finished_serials"])

    other_headers = {"Authorization": f"Bearer {token(client, 'other@test.jp')}"}
    assert client.get(f"/api/v1/traceability/serials/{serial_number}", headers=other_headers).status_code == 404


def test_maintenance_downtime_classification_and_analytics(context):
    client = context["client"]
    maintenance_headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    equipment = client.post("/api/v1/maintenance/equipment", headers=maintenance_headers, json={
        "code": "MC-CAPA-1", "name": "CNC Test Machine", "location": "Line A",
    })
    assert equipment.status_code == 201, equipment.text
    task = client.post("/api/v1/maintenance/tasks", headers=maintenance_headers, json={
        "equipment_id": equipment.json()["id"], "title": "Unexpected spindle failure", "maintenance_type": "UNPLANNED",
    })
    assert task.status_code == 201, task.text
    updated = client.patch(f"/api/v1/maintenance/tasks/{task.json()['id']}", headers=maintenance_headers, json={
        "status": "COMPLETED", "downtime_minutes": 90, "maintenance_type": "UNPLANNED", "notes": "Bearing replaced",
    })
    assert updated.status_code == 200, updated.text
    analytics = client.get("/api/v1/maintenance/analytics?planned_operating_minutes=600", headers=maintenance_headers)
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["unplanned_downtime_minutes"] == 90
    assert analytics.json()["availability_percent"] == 85.0


def test_finished_product_inspection_quarantine_capa_release_and_genealogy(context):
    client = context["client"]
    admin_headers = {"Authorization": f"Bearer {token(client, 'admin@test.jp')}"}
    quality_headers = {"Authorization": f"Bearer {token(client, 'quality@test.jp')}"}
    other_headers = {"Authorization": f"Bearer {token(client, 'other@test.jp')}"}

    created = client.post("/api/v1/production/orders", headers=admin_headers, json={
        "order_number": "MO-FP-QUALITY-1", "product_name": "Finished Precision Part",
        "quantity": 2, "material_name": "Steel", "material_required": 2,
    })
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    assert client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "READY"}).status_code == 200
    assert client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "IN_PROGRESS"}).status_code == 200
    assert client.patch(f"/api/v1/production/orders/{order_id}/progress", headers=admin_headers, json={
        "completed_quantity": 2, "rejected_quantity": 0,
    }).status_code == 200
    completed = client.patch(f"/api/v1/production/orders/{order_id}/status", headers=admin_headers, json={"status": "COMPLETED"})
    assert completed.status_code == 200, completed.text

    finished_batches = client.get("/api/v1/quality/finished-batches", headers=admin_headers)
    assert finished_batches.status_code == 200, finished_batches.text
    finished_batch = next(row for row in finished_batches.json() if row["production_order_id"] == order_id)
    serials = client.get("/api/v1/traceability/serials", headers=admin_headers).json()
    generated = [row for row in serials if row["production_order_id"] == order_id]
    assert len(generated) == 2
    assert all(row["finished_product_batch_id"] == finished_batch["id"] for row in generated)

    failed = client.post("/api/v1/quality/inspections", headers=quality_headers, json={
        "inspection_number": "QI-FP-FAIL-1", "product_name": "Finished Precision Part",
        "finished_product_serial_id": generated[0]["id"], "result": "FAIL",
        "defect_count": 1, "sample_size": 1,
        "corrective_action": "Quarantine output and investigate the final assembly issue",
    })
    assert failed.status_code == 201, failed.text
    failed_row = failed.json()
    assert failed_row["finished_product_batch_id"] == finished_batch["id"]
    assert failed_row["finished_product_serial_id"] == generated[0]["id"]
    assert failed_row["capa"]["finished_product_batch_id"] == finished_batch["id"]

    held_batches = client.get("/api/v1/quality/finished-batches", headers=admin_headers).json()
    assert next(row for row in held_batches if row["id"] == finished_batch["id"])["status"] == "HOLD"
    quarantined = client.get("/api/v1/traceability/serials", headers=admin_headers).json()
    assert {row["status"] for row in quarantined if row["production_order_id"] == order_id} == {"QUARANTINED"}
    denied_release = client.post(f"/api/v1/quality/finished-batches/{finished_batch['id']}/release",
        headers=quality_headers, json={"inspection_id": failed_row["id"], "reason": "Attempt to release failed output"})
    assert denied_release.status_code == 409

    passing = client.post("/api/v1/quality/inspections", headers=quality_headers, json={
        "inspection_number": "QI-FP-PASS-1", "product_name": "Finished Precision Part",
        "finished_product_batch_id": finished_batch["id"], "finished_product_serial_id": generated[0]["id"],
        "result": "PASS", "defect_count": 0, "sample_size": 1,
        "notes": "Corrective work verified; the reinspection meets all approved release criteria",
    })
    assert passing.status_code == 201, passing.text

    db = context["Session"]()
    finished_batch_row = db.get(models.FinishedProductBatch, finished_batch["id"])
    assert finished_batch_row
    material_batch = db.scalar(select(models.MaterialBatch).where(
        models.MaterialBatch.organization_id == finished_batch_row.organization_id,
        models.MaterialBatch.lot_number == "LOT-TEST-1",
    ))
    assert material_batch
    material_batch.status = "HOLD"
    finished_batch_row.source_lots_json = '["LOT-TEST-1"]'
    db.commit()
    db.close()
    source_hold_release = client.post(f"/api/v1/quality/finished-batches/{finished_batch['id']}/release",
        headers=quality_headers, json={"inspection_id": passing.json()["id"], "reason": "Source hold must remain effective"})
    assert source_hold_release.status_code == 409
    assert {row["status"] for row in client.get("/api/v1/traceability/serials", headers=admin_headers).json()
            if row["production_order_id"] == order_id} == {"QUARANTINED"}

    db = context["Session"]()
    material_batch = db.scalar(select(models.MaterialBatch).where(
        models.MaterialBatch.organization_id == finished_batch_row.organization_id,
        models.MaterialBatch.lot_number == "LOT-TEST-1",
    ))
    assert material_batch
    material_batch.status = "AVAILABLE"
    db.commit()
    db.close()
    released = client.post(f"/api/v1/quality/finished-batches/{finished_batch['id']}/release",
        headers=quality_headers, json={"inspection_id": passing.json()["id"], "reason": "Verified reinspection and CAPA containment"})
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "AVAILABLE"
    released_serials = client.get("/api/v1/traceability/serials", headers=admin_headers).json()
    assert {row["status"] for row in released_serials if row["production_order_id"] == order_id} == {"AVAILABLE"}

    serial_trace = client.get(f"/api/v1/traceability/serials/{generated[0]['serial_number']}", headers=admin_headers)
    assert serial_trace.status_code == 200, serial_trace.text
    trace_body = serial_trace.json()
    assert trace_body["finished_product_batch"]["batch_number"] == finished_batch["batch_number"]
    assert [row["inspection_number"] for row in trace_body["finished_product_inspections"]] == [
        "QI-FP-FAIL-1", "QI-FP-PASS-1",
    ]
    assert trace_body["finished_product_corrective_actions"][0]["case_number"] == "CAPA-QI-FP-FAIL-1"

    lot_trace = client.get("/api/v1/traceability/LOT-TEST-1", headers=admin_headers)
    assert lot_trace.status_code == 200, lot_trace.text
    traced_batch = next(row for row in lot_trace.json()["finished_product_batches"] if row["id"] == finished_batch["id"])
    assert {row["inspection_number"] for row in traced_batch["inspections"]} == {"QI-FP-FAIL-1", "QI-FP-PASS-1"}
    assert any(event["event_type"] == "FINISHED_QUALITY_RELEASED" for event in lot_trace.json()["events"])

    cross_org = client.post("/api/v1/quality/inspections", headers=other_headers, json={
        "inspection_number": "QI-FP-CROSS-1", "product_name": "Finished Precision Part",
        "finished_product_batch_id": finished_batch["id"], "result": "PASS",
        "defect_count": 0, "sample_size": 1, "notes": "Cross-organisation inspection",
    })
    assert cross_org.status_code == 404
    assert client.get("/api/v1/quality/finished-batches", headers=other_headers).json() == []
    assert client.get(f"/api/v1/traceability/serials/{generated[0]['serial_number']}", headers=other_headers).status_code == 404
