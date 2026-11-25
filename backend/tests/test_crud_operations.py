"""Edit and delete behaviour for organisation-owned records.

These tests cover the rules that make editing safe in production: only mutable
records can change, deletes never orphan stock, quality or maintenance history,
every change is audited, and roles cannot edit records outside their tenant.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app import main as main_module
from app.database import Base, get_db
from app.main import app
from app.security import hash_password

PASSWORD = "FactoryLink2026!"


@pytest.fixture()
def context(monkeypatch):
    monkeypatch.setattr(main_module.settings, "malware_scan_enabled", False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = Session()
    factory = models.Organization(name="Sakura Test", code="SAKURA-TEST", org_type="MANUFACTURER")
    other = models.Organization(name="Other Factory", code="OTHER-TEST", org_type="MANUFACTURER")
    supplier_org = models.Organization(name="Osaka Supplier", code="OSAKA-TEST", org_type="SUPPLIER")
    db.add_all([factory, other, supplier_org]); db.flush()
    db.add_all([
        models.User(organization_id=factory.id, email="admin@test.jp", full_name="Test Admin", password_hash=hash_password(PASSWORD), role="ORG_ADMIN"),
        models.User(organization_id=factory.id, email="production@test.jp", full_name="Prod Manager", password_hash=hash_password(PASSWORD), role="PRODUCTION_MANAGER"),
        models.User(organization_id=factory.id, email="warehouse@test.jp", full_name="Warehouse User", password_hash=hash_password(PASSWORD), role="WAREHOUSE_MANAGER"),
        models.User(organization_id=factory.id, email="maintenance@test.jp", full_name="Maint Manager", password_hash=hash_password(PASSWORD), role="MAINTENANCE_MANAGER"),
        models.User(organization_id=factory.id, email="quality@test.jp", full_name="Quality User", password_hash=hash_password(PASSWORD), role="QUALITY_INSPECTOR"),
        models.User(organization_id=factory.id, email="operator@test.jp", full_name="Operator", password_hash=hash_password(PASSWORD), role="OPERATOR"),
        models.User(organization_id=other.id, email="other@test.jp", full_name="Other Admin", password_hash=hash_password(PASSWORD), role="ORG_ADMIN"),
    ])
    supplier = models.Supplier(organization_id=factory.id, supplier_organization_id=supplier_org.id, code="SUP-1", name="Osaka Supplier", status="ACTIVE")
    db.add(supplier); db.flush()
    po = models.PurchaseOrder(organization_id=factory.id, supplier_id=supplier.id, po_number="PO-TEST-1", item_name="Steel", quantity=100, unit="kg", status="DRAFT")
    production = models.ProductionOrder(organization_id=factory.id, order_number="MO-TEST-1", product_name="Bracket", quantity=10, status="PLANNED")
    equipment = models.Equipment(organization_id=factory.id, code="EQ-1", name="Press", location="Line 1")
    other_equipment = models.Equipment(organization_id=other.id, code="EQ-1", name="Foreign press")
    template = models.QualityTemplate(organization_id=factory.id, code="TPL-1", name="Final check", process_type="FINAL", criteria_json="[]")
    db.add_all([po, production, equipment, other_equipment, template]); db.flush()
    db.add(models.MaintenanceTask(organization_id=factory.id, equipment_id=equipment.id, title="Quarterly service", status="SCHEDULED"))
    db.add(models.Attachment(organization_id=factory.id, purchase_order_id=po.id, supplier_id=supplier.id, uploaded_by=1, display_name="certificate.pdf", storage_name="a" * 32 + ".pdf", mime_type="application/pdf", size_bytes=1200))
    db.commit()
    ids = {"organization": factory.id, "other_organization": other.id, "supplier": supplier.id, "po": po.id,
           "production": production.id, "equipment": equipment.id, "other_equipment": other_equipment.id, "template": template.id}
    db.close()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield {"client": client, "Session": Session, "ids": ids}
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def auth(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_supplier_can_be_edited_and_deleted(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "admin@test.jp")
    response = client.patch(f"/api/v1/suppliers/{ids['supplier']}", headers=headers, json={"name": "Osaka Supplier KK", "contact_name": "Sato", "status": "INACTIVE"})
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Osaka Supplier KK"
    assert response.json()["status"] == "INACTIVE"
    # A purchase order still references the supplier, so deletion is refused
    # rather than silently orphaning procurement history.
    blocked = client.delete(f"/api/v1/suppliers/{ids['supplier']}", headers=headers)
    assert blocked.status_code == 409
    assert "purchase orders" in blocked.json()["detail"]
    with context["Session"]() as db:
        audit = db.scalars(select(models.AuditLog).where(models.AuditLog.entity_type == "Supplier")).all()
        assert any(item.action == "UPDATE" for item in audit)


def test_supplier_edit_rejects_duplicate_and_requires_permission(context):
    client, ids = context["client"], context["ids"]
    admin = auth(client, "admin@test.jp")
    warehouse = auth(client, "warehouse@test.jp")
    assert client.patch(f"/api/v1/suppliers/{ids['supplier']}", headers=warehouse, json={"name": "Nope"}).status_code == 403
    with context["Session"]() as db:
        db.add(models.Supplier(organization_id=ids["organization"], code="SUP-2", name="Second supplier")); db.commit()
    duplicate = client.patch(f"/api/v1/suppliers/{ids['supplier']}", headers=admin, json={"code": "SUP-2"})
    assert duplicate.status_code == 409


def test_purchase_order_edit_and_delete_rules(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "production@test.jp")
    edited = client.patch(f"/api/v1/purchase-orders/{ids['po']}", headers=headers, json={"item_name": "Stainless steel", "quantity": 80, "unit_price": 1200})
    assert edited.status_code == 200, edited.text
    assert edited.json()["item_name"] == "Stainless steel"
    assert edited.json()["quantity"] == 80
    # Shared documents block deletion until they are removed explicitly.
    with context["Session"]() as db:
        document_id = db.scalars(select(models.Attachment.id)).one()
    assert client.delete(f"/api/v1/purchase-orders/{ids['po']}", headers=headers).status_code == 409
    assert client.delete(f"/api/v1/documents/{document_id}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1/purchase-orders/{ids['po']}", headers=headers).status_code == 204
    assert client.get("/api/v1/purchase-orders", headers=headers).json() == []


def test_purchase_order_cannot_be_edited_after_dispatch(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "admin@test.jp")
    with context["Session"]() as db:
        db.get(models.PurchaseOrder, ids["po"]).status = "IN_TRANSIT"; db.commit()
    response = client.patch(f"/api/v1/purchase-orders/{ids['po']}", headers=headers, json={"item_name": "Changed"})
    assert response.status_code == 409
    assert client.delete(f"/api/v1/purchase-orders/{ids['po']}", headers=headers).status_code == 409


def test_production_order_edit_and_delete_rules(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "admin@test.jp")
    edited = client.patch(f"/api/v1/production/orders/{ids['production']}", headers=headers, json={"product_name": "Bracket v2", "quantity": 12, "due_date": "2026-12-01"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["product_name"] == "Bracket v2"
    assert edited.json()["due_date"] == "2026-12-01"
    assert client.delete(f"/api/v1/production/orders/{ids['production']}", headers=headers).status_code == 204


def test_production_order_cannot_be_edited_once_started(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "admin@test.jp")
    with context["Session"]() as db:
        order = db.get(models.ProductionOrder, ids["production"])
        order.status = "IN_PROGRESS"; order.completed_quantity = 2; db.commit()
    assert client.patch(f"/api/v1/production/orders/{ids['production']}", headers=headers, json={"quantity": 20}).status_code == 409
    assert client.delete(f"/api/v1/production/orders/{ids['production']}", headers=headers).status_code == 409


def test_equipment_edit_and_delete_guard(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "maintenance@test.jp")
    updated = client.patch(f"/api/v1/maintenance/equipment/{ids['equipment']}", headers=headers, json={"location": "Line 2", "next_maintenance": "2026-12-15"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["location"] == "Line 2"
    blocked = client.delete(f"/api/v1/maintenance/equipment/{ids['equipment']}", headers=headers)
    assert blocked.status_code == 409
    assert "maintenance history" in blocked.json()["detail"]


def test_equipment_edit_is_tenant_scoped(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "admin@test.jp")
    assert client.patch(f"/api/v1/maintenance/equipment/{ids['other_equipment']}", headers=headers, json={"location": "Hijacked"}).status_code == 404


def test_maintenance_task_edit_and_delete(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "maintenance@test.jp")
    with context["Session"]() as db:
        task_id = db.scalars(select(models.MaintenanceTask.id)).one()
    edited = client.patch(f"/api/v1/maintenance/tasks/{task_id}/details", headers=headers, json={"title": "Half-year service", "notes": "Check hydraulics"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Half-year service"
    assert client.delete(f"/api/v1/maintenance/tasks/{task_id}", headers=headers).status_code == 204
    with context["Session"]() as db:
        assert db.scalars(select(models.MaintenanceTask)).all() == []


def test_completed_maintenance_cannot_be_deleted(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "maintenance@test.jp")
    with context["Session"]() as db:
        task = db.scalars(select(models.MaintenanceTask)).one(); task.status = "COMPLETED"; db.commit(); task_id = task.id
    assert client.delete(f"/api/v1/maintenance/tasks/{task_id}", headers=headers).status_code == 409


def test_quality_template_edit_and_retire(context):
    client, ids = context["client"], context["ids"]
    headers = auth(client, "quality@test.jp")
    edited = client.patch(f"/api/v1/quality/templates/{ids['template']}", headers=headers, json={"name": "Final inspection", "criteria": [{"key": "surface", "label": "Surface", "kind": "PASS_FAIL"}]})
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Final inspection"
    assert edited.json()["criteria"][0]["key"] == "surface"
    assert client.delete(f"/api/v1/quality/templates/{ids['template']}", headers=headers).status_code == 204
    assert client.get("/api/v1/quality/templates", headers=headers).json() == []
    with context["Session"]() as db:
        assert db.get(models.QualityTemplate, ids["template"]).is_active is False


def test_user_role_update_and_deactivation(context):
    client, ids = context["client"], context["ids"]
    admin = auth(client, "admin@test.jp")
    with context["Session"]() as db:
        officer = db.scalars(select(models.User).where(models.User.email == "operator@test.jp")).one().id
    promoted = client.patch(f"/api/v1/users/{officer}", headers=admin, json={"role": "QUALITY_INSPECTOR", "full_name": "Operator One"})
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "QUALITY_INSPECTOR"
    assert client.delete(f"/api/v1/users/{officer}", headers=admin).status_code == 204
    # A deactivated account can no longer sign in and disappears from the list.
    assert client.post("/api/v1/auth/login", json={"email": "operator@test.jp", "password": PASSWORD}).status_code == 401
    emails = [row["email"] for row in client.get("/api/v1/users", headers=admin).json()]
    assert "operator@test.jp" not in emails


def test_user_cannot_change_own_role_or_deactivate_self(context):
    client, ids = context["client"], context["ids"]
    admin = auth(client, "admin@test.jp")
    me = client.get("/api/v1/auth/me", headers=admin).json()
    assert client.patch(f"/api/v1/users/{me['id']}", headers=admin, json={"role": "OPERATOR"}).status_code == 409
    assert client.delete(f"/api/v1/users/{me['id']}", headers=admin).status_code == 409


def test_invalid_role_for_organisation_is_rejected(context):
    client, ids = context["client"], context["ids"]
    admin = auth(client, "admin@test.jp")
    with context["Session"]() as db:
        warehouse = db.scalars(select(models.User).where(models.User.email == "warehouse@test.jp")).one().id
    assert client.patch(f"/api/v1/users/{warehouse}", headers=admin, json={"role": "SUPPLIER_USER"}).status_code == 422


def test_document_delete_removes_record_and_is_scoped(context):
    client, ids = context["client"], context["ids"]
    admin = auth(client, "admin@test.jp")
    other = auth(client, "other@test.jp")
    with context["Session"]() as db:
        document_id = db.scalars(select(models.Attachment.id)).one()
    assert client.delete(f"/api/v1/documents/{document_id}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/documents/{document_id}", headers=admin).status_code == 204
    assert client.get("/api/v1/documents", headers=admin).json() == []
