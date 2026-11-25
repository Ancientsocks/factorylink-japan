from datetime import date, timedelta
from sqlalchemy import select
from .database import Base, get_engine, SessionLocal, set_request_context, set_tenant_context
from .models import Organization, User, Supplier, PurchaseOrder, MaterialBatch, InventoryMovement, ProductionOrder, QualityInspection, Equipment, MaintenanceTask, TraceabilityEvent, Notification, QualityTemplate, CorrectiveAction
from .security import hash_password

DEMO_PASSWORD = "FactoryLink2026!"

def seed():
    Base.metadata.create_all(bind=get_engine())
    db = SessionLocal()
    try:
        set_request_context(db, "app.organization_provisioning", "on")
        factory = db.scalar(select(Organization).where(Organization.code == "SAKURA-JP"))
        if not factory:
            factory = Organization(name="Sakura Precision Manufacturing", code="SAKURA-JP", org_type="MANUFACTURER", postal_code="460-0008", prefecture="Aichi", address="Naka-ku, Nagoya, Aichi (fictional demo address)", timezone="Asia/Tokyo", currency="JPY")
            db.add(factory)
        supplier_org = db.scalar(select(Organization).where(Organization.code == "OSAKA-SUP"))
        if not supplier_org:
            supplier_org = Organization(name="Osaka Parts Supply", code="OSAKA-SUP", org_type="SUPPLIER", postal_code="550-0001", prefecture="Osaka", address="Nishi-ku, Osaka (fictional demo address)", timezone="Asia/Tokyo", currency="JPY")
            db.add(supplier_org)
        other_factory = db.scalar(select(Organization).where(Organization.code == "TOKYO-IND"))
        if not other_factory:
            other_factory = Organization(name="Tokyo Industrial Components", code="TOKYO-IND", org_type="MANUFACTURER", postal_code="144-0001", prefecture="Tokyo", address="Ota-ku, Tokyo (fictional demo address)", timezone="Asia/Tokyo", currency="JPY")
            db.add(other_factory)
        db.flush()
        # Demo business data is deliberately scoped to the fictional factory.
        # User and organisation bootstrap records are not RLS-protected.
        demo_users = [
            ("admin@factorylink.jp", "Tanaka Hiroshi", "ORG_ADMIN", factory.id),
            ("production@factorylink.jp", "Sato Kenji", "PRODUCTION_MANAGER", factory.id),
            ("warehouse@factorylink.jp", "Yamada Aiko", "WAREHOUSE_MANAGER", factory.id),
            ("quality@factorylink.jp", "Suzuki Mei", "QUALITY_INSPECTOR", factory.id),
            ("maintenance@factorylink.jp", "Ito Ren", "MAINTENANCE_MANAGER", factory.id),
            ("operator@factorylink.jp", "Kobayashi Daichi", "OPERATOR", factory.id),
            ("supplier@osaka-parts.jp", "Nakamura Yuki", "SUPPLIER_USER", supplier_org.id),
            ("admin@tokyo-industrial.jp", "Kato Emi", "ORG_ADMIN", other_factory.id),
        ]
        for email, name, role, org_id in demo_users:
            set_tenant_context(db, org_id)
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(organization_id=org_id, email=email, full_name=name, password_hash=hash_password(DEMO_PASSWORD), role=role, language="ja"))
        db.flush()
        set_tenant_context(db, factory.id)
        supplier = db.scalar(select(Supplier).where(Supplier.organization_id == factory.id, Supplier.code == "SUP-OSK-01"))
        if not supplier:
            supplier = Supplier(organization_id=factory.id, supplier_organization_id=supplier_org.id, code="SUP-OSK-01", name="Osaka Parts Supply", contact_name="Nakamura Yuki", email="contact@osaka-parts.jp", phone="06-5555-0101", prefecture="Osaka", status="ACTIVE")
            db.add(supplier)
        db.flush()
        steel_po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.organization_id == factory.id, PurchaseOrder.po_number == "PO-2026-001"))
        if not steel_po:
            steel_po = PurchaseOrder(organization_id=factory.id, supplier_id=supplier.id, po_number="PO-2026-001", item_name="Steel (S45C)", quantity=4000, received_quantity=3200, unit="kg", unit_price=480, due_date=date.today()+timedelta(days=7), status="PARTIALLY_DELIVERED")
            db.add(steel_po)
        resin_po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.organization_id == factory.id, PurchaseOrder.po_number == "PO-2026-002"))
        if not resin_po:
            resin_po = PurchaseOrder(organization_id=factory.id, supplier_id=supplier.id, po_number="PO-2026-002", item_name="Resin (ABS)", quantity=2000, received_quantity=1500, unit="kg", unit_price=620, due_date=date.today()+timedelta(days=12), status="PARTIALLY_DELIVERED")
            db.add(resin_po)
        db.flush()
        if not db.scalar(select(MaterialBatch).where(MaterialBatch.organization_id == factory.id)):
            batches = [
                MaterialBatch(organization_id=factory.id, supplier_id=supplier.id, purchase_order_id=steel_po.id, material_name="Steel (S45C)", lot_number="LOT-8831", quantity_on_hand=3200, unit="kg", unit_cost=480, status="AVAILABLE"),
                MaterialBatch(organization_id=factory.id, supplier_id=supplier.id, purchase_order_id=resin_po.id, material_name="Resin (ABS)", lot_number="LOT-7710", quantity_on_hand=1500, unit="kg", unit_cost=620, status="AVAILABLE"),
                MaterialBatch(organization_id=factory.id, supplier_id=supplier.id, material_name="Screw (M4)", lot_number="LOT-4462", quantity_on_hand=48000, unit="pcs", unit_cost=3.5, status="AVAILABLE"),
            ]
            db.add_all(batches)
            db.flush()
            admin = db.scalar(select(User).where(User.email == "admin@factorylink.jp"))
            for batch in batches:
                db.add(InventoryMovement(organization_id=factory.id, batch_id=batch.id, movement_type="RECEIPT", quantity=batch.quantity_on_hand, reference=f"SEED-{batch.lot_number}", note="Fictional development seed data", created_by=admin.id))
                db.add(TraceabilityEvent(organization_id=factory.id, lot_number=batch.lot_number, event_type="GOODS_RECEIVED", reference=f"SEED-{batch.lot_number}", details=f"Initial receipt from {supplier.name}"))
        if not db.scalar(select(ProductionOrder).where(ProductionOrder.organization_id == factory.id)):
            db.add_all([
                ProductionOrder(organization_id=factory.id, order_number="MO-2026-001", product_name="Precision Bracket A", quantity=1000, completed_quantity=760, rejected_quantity=8, material_name="Steel (S45C)", material_required=0, due_date=date.today()+timedelta(days=2), status="IN_PROGRESS"),
                ProductionOrder(organization_id=factory.id, order_number="MO-2026-002", product_name="Housing Case B", quantity=500, material_name="Resin (ABS)", material_required=0, due_date=date.today()+timedelta(days=5), status="PLANNED"),
                ProductionOrder(organization_id=factory.id, order_number="MO-2026-003", product_name="Machine Cover C", quantity=2000, completed_quantity=2000, material_name="Steel (S45C)", material_required=0, due_date=date.today()-timedelta(days=1), status="COMPLETED"),
            ])
        if not db.scalar(select(QualityInspection).where(QualityInspection.organization_id == factory.id)):
            quality_user = db.scalar(select(User).where(User.email == "quality@factorylink.jp"))
            steel_batch = db.scalar(select(MaterialBatch).where(MaterialBatch.organization_id == factory.id, MaterialBatch.lot_number == "LOT-8831"))
            resin_batch = db.scalar(select(MaterialBatch).where(MaterialBatch.organization_id == factory.id, MaterialBatch.lot_number == "LOT-7710"))
            db.add_all([
                QualityInspection(organization_id=factory.id, inspection_number="QI-2051", product_name="Precision Bracket A", batch_id=steel_batch.id if steel_batch else None, result="PASS", defect_count=0, sample_size=250, notes="Visual and dimensional checks passed", created_by=quality_user.id),
                QualityInspection(organization_id=factory.id, inspection_number="QI-2052", product_name="Housing Case B", batch_id=resin_batch.id if resin_batch else None, result="FAIL", defect_count=3, sample_size=500, notes="Surface defects detected; demo record", corrective_action="Segregate affected batch and investigate process parameters", created_by=quality_user.id),
            ])
            db.flush()
            if resin_batch:
                resin_batch.status = "HOLD"
                db.add(TraceabilityEvent(organization_id=factory.id, lot_number=resin_batch.lot_number, event_type="QUALITY_HOLD", reference="QI-2052", details="Fictional demo: 3 defects in a sample of 500. Batch held pending corrective action."))
        quality_template = db.scalar(select(QualityTemplate).where(QualityTemplate.organization_id == factory.id, QualityTemplate.code == "FINAL-DIM-VIS"))
        if not quality_template:
            quality_template = QualityTemplate(organization_id=factory.id, code="FINAL-DIM-VIS", name="Final dimensional and visual inspection", process_type="FINAL", criteria_json='[{"key":"dimension","label":"Dimensional tolerance","kind":"NUMERIC","minimum":9.95,"maximum":10.05,"required":true},{"key":"surface","label":"Surface finish","kind":"PASS_FAIL","required":true},{"key":"label","label":"Product label","kind":"PASS_FAIL","required":true}]')
            db.add(quality_template)
        failed_demo = db.scalar(select(QualityInspection).where(QualityInspection.organization_id == factory.id, QualityInspection.inspection_number == "QI-2052"))
        if failed_demo and not db.scalar(select(CorrectiveAction).where(CorrectiveAction.organization_id == factory.id, CorrectiveAction.inspection_id == failed_demo.id)):
            db.add(CorrectiveAction(organization_id=factory.id, inspection_id=failed_demo.id, batch_id=failed_demo.batch_id,
                case_number="CAPA-QI-2052", title="Investigate surface defects on Housing Case B", status="OPEN",
                containment_action=failed_demo.corrective_action, created_by=failed_demo.created_by))
        if not db.scalar(select(Equipment).where(Equipment.organization_id == factory.id)):
            equipment = [
                Equipment(organization_id=factory.id, code="MC-01", name="CNC Machining Center", location="Line A", status="OPERATIONAL", next_maintenance=date.today()+timedelta(days=9)),
                Equipment(organization_id=factory.id, code="MC-02", name="Precision Lathe", location="Line B", status="OPERATIONAL", next_maintenance=date.today()+timedelta(days=2)),
                Equipment(organization_id=factory.id, code="MC-03", name="Milling Machine", location="Line C", status="MAINTENANCE_DUE", next_maintenance=date.today()-timedelta(days=3)),
            ]
            db.add_all(equipment)
            db.flush()
            db.add_all([
                MaintenanceTask(organization_id=factory.id, equipment_id=equipment[0].id, title="Monthly spindle inspection", due_date=date.today()+timedelta(days=9), status="SCHEDULED"),
                MaintenanceTask(organization_id=factory.id, equipment_id=equipment[1].id, title="Lubrication and alignment check", due_date=date.today()+timedelta(days=2), status="SCHEDULED"),
                MaintenanceTask(organization_id=factory.id, equipment_id=equipment[2].id, title="Overdue coolant system service", due_date=date.today()-timedelta(days=3), status="OVERDUE", maintenance_type="UNPLANNED", downtime_minutes=135),
            ])
        if not db.scalar(select(Notification).where(Notification.organization_id == factory.id)):
            db.add_all([
                Notification(organization_id=factory.id, title="Purchase order confirmed", body="Osaka Parts Supply confirmed PO-2026-001.", level="SUCCESS"),
                Notification(organization_id=factory.id, title="Maintenance due soon", body="Precision Lathe maintenance is due in 2 days.", level="WARNING"),
            ])
        db.commit()
        print("FactoryLink demo data is ready. Demo password: FactoryLink2026!")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
