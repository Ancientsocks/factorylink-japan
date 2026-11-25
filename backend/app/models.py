from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    org_type: Mapped[str] = mapped_column(String(24), default="MANUFACTURER", nullable=False)
    postal_code: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    prefecture: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    address: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tokyo", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="JPY", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(140), nullable=False)
    # Google-only accounts have no password until they set one through reset.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(40), default="OPERATOR", nullable=False)
    language: Mapped[str] = mapped_column(String(5), default="ja", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # All rotations descended from one login share a family. Reuse of a revoked
    # ancestor revokes the remaining active tokens in that family only.
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[int | None] = mapped_column(ForeignKey("refresh_tokens.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuthActionToken(Base):
    """One-time password-reset and workspace-invitation tokens.

    Only a SHA-256 digest is persisted. Raw tokens are delivered through SMTP
    or exposed through an explicitly enabled development-only action link.
    """
    __tablename__ = "auth_action_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (CheckConstraint("purpose IN ('PASSWORD_RESET', 'INVITATION')", name="ck_auth_action_token_purpose"),)


class EmailVerificationCode(Base):
    """Short-lived email codes for sign-up and password reset.

    Only a digest of the six-digit code and of the verification ticket is
    stored. The row is scoped by email and purpose, not by tenant, because
    registration happens before an organisation exists.
    """
    __tablename__ = "email_verification_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verification_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (
        CheckConstraint("purpose IN ('REGISTRATION', 'PASSWORD_RESET')", name="ck_email_verification_purpose"),
        CheckConstraint("attempts >= 0", name="ck_email_verification_attempts"),
    )


class OAuthLoginCode(Base):
    """One-time hand-off between the Google callback and the browser."""
    __tablename__ = "oauth_login_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(140), default="", nullable=False)
    google_sub: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (CheckConstraint("purpose IN ('SIGNIN', 'SIGNUP')", name="ck_oauth_login_purpose"),)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    supplier_organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    prefecture: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_supplier_org_code"),)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    po_number: Mapped[str] = mapped_column(String(48), nullable=False)
    item_name: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    # Factory-confirmed total stored on the PO so linked supplier accounts can
    # see receipt progress without SELECT access to factory inventory ledgers.
    received_quantity: Mapped[float] = mapped_column(Float, default=0, server_default="0", nullable=False)
    unit: Mapped[str] = mapped_column(String(24), default="pcs", nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    supplier_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("organization_id", "po_number", name="uq_po_org_number"),
        CheckConstraint("quantity > 0", name="ck_po_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_po_unit_price_nonnegative"),
        CheckConstraint("received_quantity >= 0 AND received_quantity <= quantity + 0.000000001", name="ck_po_received_quantity_bounds"),
    )


class MaterialBatch(Base):
    __tablename__ = "material_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id", name="fk_material_batches_purchase_order_id_purchase_orders"),
        nullable=True, index=True,
    )
    material_name: Mapped[str] = mapped_column(String(180), nullable=False)
    lot_number: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity_on_hand: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    quantity_reserved: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(24), default="kg", nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="AVAILABLE", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "lot_number", name="uq_batch_org_lot"), CheckConstraint("quantity_on_hand >= 0", name="ck_batch_on_hand_nonnegative"), CheckConstraint("quantity_reserved >= 0", name="ck_batch_reserved_nonnegative"), CheckConstraint("quantity_reserved <= quantity_on_hand", name="ck_batch_reserved_not_over_on_hand"), CheckConstraint("unit_cost >= 0", name="ck_batch_cost_nonnegative"))


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("material_batches.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (CheckConstraint("quantity != 0", name="ck_movement_quantity_nonzero"),)


class InventoryReconciliation(Base):
    __tablename__ = "inventory_reconciliations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("material_batches.id", ondelete="RESTRICT"), index=True)
    observed_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    ledger_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    variance: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", nullable=False)
    detected_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    resolution_reference: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    adjustment_movement_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_movements.id"), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'RESOLVED')", name="ck_inventory_reconciliation_status"),
        Index(
            "uq_inventory_reconciliation_open_batch",
            "organization_id", "batch_id",
            unique=True,
            sqlite_where=text("status = 'OPEN'"),
            postgresql_where=text("status = 'OPEN'"),
        ),
    )


class ProductionOrder(Base):
    __tablename__ = "production_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    order_number: Mapped[str] = mapped_column(String(48), nullable=False)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    completed_quantity: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    rejected_quantity: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    material_name: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    material_required: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    reserved_batch_ids: Mapped[str] = mapped_column(Text, default="", nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PLANNED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    track_serials: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "order_number", name="uq_prod_org_number"), CheckConstraint("quantity > 0", name="ck_production_quantity_positive"), CheckConstraint("completed_quantity >= 0", name="ck_production_completed_nonnegative"), CheckConstraint("rejected_quantity >= 0", name="ck_production_rejected_nonnegative"), CheckConstraint("completed_quantity + rejected_quantity <= quantity", name="ck_production_output_within_order"), CheckConstraint("material_required >= 0", name="ck_production_material_nonnegative"))


class FinishedProductBatch(Base):
    __tablename__ = "finished_product_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id", ondelete="RESTRICT"), unique=True, index=True)
    batch_number: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    source_lots_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="AVAILABLE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("organization_id", "batch_number", name="uq_finished_batch_org_number"),
        CheckConstraint("quantity > 0", name="ck_finished_batch_quantity_positive"),
        CheckConstraint("status IN ('AVAILABLE', 'HOLD')", name="ck_finished_batch_status"),
    )


class QualityInspection(Base):
    __tablename__ = "quality_inspections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    inspection_number: Mapped[str] = mapped_column(String(48), nullable=False)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("material_batches.id"), nullable=True)
    finished_product_batch_id: Mapped[int | None] = mapped_column(ForeignKey("finished_product_batches.id"), nullable=True, index=True)
    finished_product_serial_id: Mapped[int | None] = mapped_column(ForeignKey("finished_product_serials.id"), nullable=True, index=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    defect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    corrective_action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("quality_templates.id"), nullable=True)
    criteria_results_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "inspection_number", name="uq_qi_org_number"), CheckConstraint("defect_count >= 0", name="ck_inspection_defects_nonnegative"), CheckConstraint("sample_size >= 1", name="ck_inspection_sample_positive"), CheckConstraint("defect_count <= sample_size", name="ck_inspection_defects_within_sample"))


class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    location: Mapped[str] = mapped_column(String(140), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="OPERATIONAL", nullable=False)
    next_maintenance: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    total_downtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_equipment_org_code"),)


class MaintenanceTask(Base):
    __tablename__ = "maintenance_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="SCHEDULED", nullable=False)
    downtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    maintenance_type: Mapped[str] = mapped_column(String(24), default="PREVENTIVE", server_default="PREVENTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (CheckConstraint("downtime_minutes >= 0", name="ck_maintenance_downtime_nonnegative"), CheckConstraint("maintenance_type IN ('PREVENTIVE', 'UNPLANNED')", name="ck_maintenance_type"))


class TraceabilityEvent(Base):
    __tablename__ = "traceability_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    lot_number: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Notification(Base):
    __tablename__ = "notifications"
    # Cross-tenant inserts are allowed for linked recipients, but those rows
    # are intentionally not visible under the sender's tenant SELECT policy.
    __table_args__ = {"implicit_returning": False}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


Index("ix_movements_org_batch_created", InventoryMovement.organization_id, InventoryMovement.batch_id, InventoryMovement.created_at)

class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class QualityTemplate(Base):
    __tablename__ = "quality_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    process_type: Mapped[str] = mapped_column(String(24), default="FINAL", nullable=False)
    criteria_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_quality_template_org_code"), CheckConstraint("process_type IN ('RECEIVING', 'IN_PROCESS', 'FINAL')", name="ck_quality_template_process_type"))


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("quality_inspections.id", ondelete="CASCADE"), unique=True, index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("material_batches.id"), nullable=True, index=True)
    finished_product_batch_id: Mapped[int | None] = mapped_column(ForeignKey("finished_product_batches.id"), nullable=True, index=True)
    case_number: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="OPEN", nullable=False)
    containment_action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, default="", nullable=False)
    corrective_action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    preventive_action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verification: Mapped[str] = mapped_column(Text, default="", nullable=False)
    owner: Mapped[str] = mapped_column(String(140), default="", nullable=False)
    due_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("organization_id", "case_number", name="uq_capa_org_case"), CheckConstraint("status IN ('OPEN', 'CONTAINED', 'INVESTIGATING', 'IMPLEMENTED', 'VERIFIED', 'CLOSED')", name="ck_capa_status"))


class FinishedProductSerial(Base):
    __tablename__ = "finished_product_serials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id", ondelete="RESTRICT"), index=True)
    finished_product_batch_id: Mapped[int | None] = mapped_column(ForeignKey("finished_product_batches.id"), nullable=True, index=True)
    serial_number: Mapped[str] = mapped_column(String(96), nullable=False)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    source_lots_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="AVAILABLE", nullable=False)
    customer_name: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    shipment_reference: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "serial_number", name="uq_finished_serial_org_number"), CheckConstraint("status IN ('AVAILABLE', 'SHIPPED', 'QUARANTINED')", name="ck_finished_serial_status"))
