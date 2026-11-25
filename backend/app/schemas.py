from datetime import date
from typing import Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator, field_validator

class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class OrganizationRegister(BaseModel):
    organization_name: str = Field(min_length=2, max_length=180)
    organization_code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]+$")
    organization_type: str = Field(pattern=r"^(MANUFACTURER|SUPPLIER)$")
    owner_name: str = Field(min_length=2, max_length=140)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    email_verification_token: str = Field(min_length=20, max_length=256)
    language: str = Field(default="ja", pattern=r"^(en|ja)$")
    postal_code: str = Field(default="", max_length=16)
    prefecture: str = Field(default="", max_length=80)

    @field_validator("organization_code")
    @classmethod
    def normalise_code(cls, value: str) -> str:
        return value.strip().upper()

class RefreshInput(BaseModel):
    refresh_token: str

class LogoutInput(BaseModel):
    refresh_token: str

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    language: str
    organization_id: int
    organization_name: str
    model_config = ConfigDict(from_attributes=True)

class SupplierCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=180)
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    prefecture: str = ""
    supplier_organization_code: str = ""

class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    po_number: str = Field(min_length=3, max_length=48)
    item_name: str
    quantity: float = Field(gt=0)
    unit: str = "pcs"
    unit_price: float = Field(default=0, ge=0)
    due_date: date | None = None

class StatusUpdate(BaseModel):
    status: str
    note: str = ""

class ReceiptCreate(BaseModel):
    material_name: str
    lot_number: str = Field(min_length=2, max_length=64)
    quantity: float = Field(gt=0)
    unit: str = "kg"
    unit_cost: float = Field(default=0, ge=0)
    supplier_id: int | None = None
    purchase_order_id: int | None = Field(default=None, gt=0)
    reference: str = Field(min_length=2, max_length=80)

class InventoryAdjustment(BaseModel):
    batch_id: int
    quantity_delta: float = Field(allow_inf_nan=False)
    reference: str = Field(min_length=2, max_length=80)
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("quantity_delta")
    @classmethod
    def nonzero_delta(cls, value: float) -> float:
        if value == 0:
            raise ValueError("Quantity adjustment must be non-zero")
        return value


class InventoryReconciliationResolve(BaseModel):
    counted_quantity: float = Field(ge=0, allow_inf_nan=False)
    reference: str = Field(min_length=2, max_length=80)
    reason: str = Field(min_length=5, max_length=2000)

    @field_validator("reason")
    @classmethod
    def meaningful_reconciliation_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("A meaningful reconciliation reason is required")
        return cleaned


class ProductionCreate(BaseModel):
    order_number: str = Field(min_length=3, max_length=48)
    product_name: str
    quantity: float = Field(gt=0)
    material_name: str = ""
    material_required: float = Field(default=0, ge=0)
    due_date: date | None = None
    track_serials: bool = True

class ProductionProgress(BaseModel):
    completed_quantity: float = Field(ge=0)
    rejected_quantity: float = Field(default=0, ge=0)

class InspectionCreate(BaseModel):
    inspection_number: str
    product_name: str
    batch_id: int | None = None
    finished_product_batch_id: int | None = Field(default=None, gt=0)
    finished_product_serial_id: int | None = Field(default=None, gt=0)
    result: str
    defect_count: int = Field(default=0, ge=0)
    sample_size: int = Field(default=1, ge=1)
    notes: str = ""
    corrective_action: str = ""
    template_id: int | None = Field(default=None, gt=0)
    criteria_results: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_sample(self):
        if self.defect_count > self.sample_size:
            raise ValueError("Defect count cannot exceed the inspected sample size")
        return self

class QualityRelease(BaseModel):
    inspection_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=2000)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("A meaningful quality-release reason is required")
        return cleaned


class EquipmentCreate(BaseModel):
    code: str
    name: str
    location: str = ""
    next_maintenance: date | None = None

class MaintenanceCreate(BaseModel):
    equipment_id: int
    title: str
    due_date: date | None = None
    notes: str = ""
    maintenance_type: str = Field(default="PREVENTIVE", pattern="^(PREVENTIVE|UNPLANNED)$")

class MaintenanceUpdate(BaseModel):
    status: str
    downtime_minutes: int = Field(default=0, ge=0)
    notes: str = ""
    maintenance_type: str | None = Field(default=None, pattern="^(PREVENTIVE|UNPLANNED)$")

class LanguageUpdate(BaseModel):
    language: str = Field(pattern="^(en|ja)$")

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=140)
    password: str = Field(min_length=12, max_length=128)
    role: str
    language: str = Field(default="ja", pattern="^(en|ja)$")


class EmailActionRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str | None = Field(default=None, min_length=32, max_length=256)
    verification_token: str | None = Field(default=None, min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def exactly_one_proof(self):
        if bool(self.token) == bool(self.verification_token):
            raise ValueError("Provide exactly one of token or verification_token")
        return self


class EmailCodeRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(pattern=r"^(REGISTRATION|PASSWORD_RESET)$")


class EmailCodeVerify(EmailCodeRequest):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class GoogleExchangeInput(BaseModel):
    code: str = Field(min_length=16, max_length=512)


class GoogleRegisterInput(BaseModel):
    signup_token: str = Field(min_length=20, max_length=4096)
    organization_name: str = Field(min_length=2, max_length=180)
    organization_code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]+$")
    organization_type: str = Field(pattern=r"^(MANUFACTURER|SUPPLIER)$")
    owner_name: str = Field(min_length=2, max_length=140)
    language: str = Field(default="ja", pattern=r"^(en|ja)$")
    postal_code: str = Field(default="", max_length=16)
    prefecture: str = Field(default="", max_length=80)

    @field_validator("organization_code")
    @classmethod
    def normalise_code(cls, value: str) -> str:
        return value.strip().upper()


class InvitationCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=140)
    role: str = Field(min_length=3, max_length=40)
    language: str = Field(default="ja", pattern="^(en|ja)$")


class InvitationAccept(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=12, max_length=128)


class QualityTemplateCreate(BaseModel):
    code: str = Field(min_length=2, max_length=48)
    name: str = Field(min_length=2, max_length=180)
    process_type: str = Field(default="FINAL", pattern="^(RECEIVING|IN_PROCESS|FINAL)$")
    criteria: list[dict[str, Any]] = Field(min_length=1, max_length=40)

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, value):
        seen = set()
        for item in value:
            key = str(item.get("key", "")).strip()
            label = str(item.get("label", "")).strip()
            kind = str(item.get("kind", "PASS_FAIL")).upper()
            if not key or not label or key in seen:
                raise ValueError("Each quality criterion needs a unique key and label")
            if kind not in {"PASS_FAIL", "NUMERIC", "TEXT"}:
                raise ValueError("Criterion kind must be PASS_FAIL, NUMERIC or TEXT")
            if kind == "NUMERIC":
                if item.get("minimum") is None and item.get("maximum") is None:
                    raise ValueError("Numeric criteria need a minimum or maximum")
                if item.get("minimum") is not None and item.get("maximum") is not None and float(item["minimum"]) > float(item["maximum"]):
                    raise ValueError("Criterion minimum cannot exceed maximum")
            seen.add(key)
        return value


class CorrectiveActionUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(OPEN|CONTAINED|INVESTIGATING|IMPLEMENTED|VERIFIED|CLOSED)$")
    containment_action: str | None = Field(default=None, max_length=4000)
    root_cause: str | None = Field(default=None, max_length=4000)
    corrective_action: str | None = Field(default=None, max_length=4000)
    preventive_action: str | None = Field(default=None, max_length=4000)
    verification: str | None = Field(default=None, max_length=4000)
    owner: str | None = Field(default=None, max_length=140)
    due_date: date | None = None


class SerialShipmentUpdate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=180)
    shipment_reference: str = Field(min_length=2, max_length=80)


# Partial-update payloads. Unset fields are left untouched; an explicitly sent
# null clears a nullable field (due dates, supplier workspace links).
class SupplierUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=180)
    contact_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    prefecture: str | None = Field(default=None, max_length=80)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    supplier_organization_code: str | None = Field(default=None, max_length=40)

class PurchaseOrderUpdate(BaseModel):
    supplier_id: int | None = Field(default=None, gt=0)
    po_number: str | None = Field(default=None, min_length=3, max_length=48)
    item_name: str | None = Field(default=None, min_length=1, max_length=180)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=24)
    unit_price: float | None = Field(default=None, ge=0)
    due_date: date | None = None

class ProductionUpdate(BaseModel):
    order_number: str | None = Field(default=None, min_length=3, max_length=48)
    product_name: str | None = Field(default=None, min_length=1, max_length=180)
    quantity: float | None = Field(default=None, gt=0)
    material_name: str | None = Field(default=None, max_length=180)
    material_required: float | None = Field(default=None, ge=0)
    due_date: date | None = None
    track_serials: bool | None = None

class EquipmentUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=180)
    location: str | None = Field(default=None, max_length=140)
    status: str | None = Field(default=None, pattern="^(OPERATIONAL|MAINTENANCE_DUE)$")
    next_maintenance: date | None = None

class MaintenanceDetailsUpdate(BaseModel):
    equipment_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=180)
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    maintenance_type: str | None = Field(default=None, pattern="^(PREVENTIVE|UNPLANNED)$")

class QualityTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    process_type: str | None = Field(default=None, pattern="^(RECEIVING|IN_PROCESS|FINAL)$")
    criteria: list[dict[str, Any]] | None = None

class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=140)
    role: str | None = Field(default=None, max_length=40)
    language: str | None = Field(default=None, pattern="^(en|ja)$")
    is_active: bool | None = None
