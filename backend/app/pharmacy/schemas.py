from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DispensationStatusEnum(StrEnum):
    dispensed = "dispensed"
    voided = "voided"


class AllergyCheckSourceEnum(StrEnum):
    medical_record = "medical_record"
    form = "form"


class DispensationLineRequest(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)


class DispensationOrderCreate(BaseModel):
    warehouse_id: int
    patient_contact_id: int
    prescription_id: int | None = None
    walk_in_reference: str | None = Field(None, max_length=300)
    # DED-47: obligatorio solo si medical no está activo (o no hay
    # alergias registradas para el paciente) — validado en el servicio,
    # no acá, porque depende del estado del paquete.
    allergy_check_notes: str | None = Field(None, max_length=1000)
    payment_method: str | None = Field(None, max_length=50)
    amount_charged: Decimal | None = Field(None, ge=0)
    lines: list[DispensationLineRequest] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _prescription_xor_walkin(self) -> DispensationOrderCreate:
        if self.prescription_id is not None and self.walk_in_reference is not None:
            raise ValueError("prescription_id y walk_in_reference son mutuamente excluyentes")
        return self


class DispensationVoid(BaseModel):
    void_reason: str = Field(..., min_length=1, max_length=500)


class DispensationLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    lot_id: int | None
    quantity: Decimal


class DispensationOrderRead(BaseModel):
    id: int
    company_id: int
    warehouse_id: int
    patient_contact_id: int
    dispensed_by: int
    document_number: str
    prescription_id: int | None
    walk_in_reference: str | None
    allergy_check_source: AllergyCheckSourceEnum
    allergy_check_notes: str | None
    payment_method: str | None
    amount_charged: Decimal | None
    status: DispensationStatusEnum
    voided_at: datetime | None
    void_reason: str | None
    dispensed_at: datetime
    lines: list[DispensationLineRead]


class ControlledSubstanceMark(BaseModel):
    product_id: int


class ControlledSubstanceProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    created_at: datetime


class ControlledSubstanceLogEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    dispensation_line_id: int
    product_id: int
    patient_contact_id: int
    dispensed_by: int
    quantity: Decimal
    created_at: datetime


# ---------------------------------------------------------------------------
# Módulo 21 — MTM / Consulta Farmacéutica. Ver DED-62/63/64 en models.py.
# ---------------------------------------------------------------------------
class MtmSessionStatusEnum(StrEnum):
    open = "open"
    closed = "closed"
    cancelled = "cancelled"


class MtmBillingModeEnum(StrEnum):
    accounting_invoice = "accounting_invoice"
    simple_receipt = "simple_receipt"


class MtmSessionCreate(BaseModel):
    patient_contact_id: int
    session_date: date
    medication_review: str = Field(..., min_length=1)
    adherence_notes: str | None = None
    adverse_effects_notes: str | None = None
    recommendations: str | None = None
    fee_amount: Decimal = Field(..., gt=0)
    currency_code: str = Field(default="HNL", max_length=3)


class MtmSessionCancel(BaseModel):
    cancel_reason: str = Field(..., min_length=1, max_length=500)


class MtmSessionClose(BaseModel):
    """Dispara la facturación en la misma operación (DED-62) — issue_date
    y tax_rate_id son del comprobante, no de la sesión (que ya trae su
    propio `session_date`/`fee_amount` desde la creación)."""

    issue_date: date
    tax_rate_id: int | None = None


class MtmSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    patient_contact_id: int
    pharmacist_user_id: int
    session_date: date
    medication_review: str
    adherence_notes: str | None
    adverse_effects_notes: str | None
    recommendations: str | None
    fee_amount: Decimal
    currency_code: str
    status: MtmSessionStatusEnum
    closed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime


class MtmBillingRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    session_id: int
    billing_mode: MtmBillingModeEnum
    status: str
    amount: Decimal
    currency_code: str
    issue_date: date
    invoice_id: int | None
    receipt_number: str | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Módulo 20 — Reposición a Droguerías. Ver DED-65/66/67 en models.py.
# ---------------------------------------------------------------------------
class ReorderPointUpsert(BaseModel):
    product_id: int
    warehouse_id: int
    reorder_point: Decimal = Field(..., ge=0)
    reorder_quantity: Decimal = Field(..., gt=0)
    preferred_vendor_id: int | None = None


class ReorderPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    product_id: int
    warehouse_id: int
    reorder_point: Decimal
    reorder_quantity: Decimal
    preferred_vendor_id: int | None
    created_at: datetime
    updated_at: datetime


class ReorderSuggestionRead(BaseModel):
    """Calculada al vuelo — no es una fila de base de datos (ver DED-65
    en models.py). `below_by` es puramente informativo (reorder_point -
    available_quantity), para ordenar/priorizar en el frontend."""

    product_id: int
    warehouse_id: int
    available_quantity: Decimal
    reorder_point: Decimal
    reorder_quantity: Decimal
    below_by: Decimal
    preferred_vendor_id: int | None


class ReorderPurchaseOrderLineInput(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., ge=0)


class ReorderPurchaseOrderGenerate(BaseModel):
    """El pharmacista confirma/ajusta las líneas antes de generar la PO
    real — ver DED-67 (el sistema no infiere costos)."""

    warehouse_id: int
    vendor_id: int
    currency_code: str = Field(default="HNL", max_length=3)
    expected_date: date | None = None
    lines: list[ReorderPurchaseOrderLineInput] = Field(..., min_length=1)


class InteractionSeverityEnum(StrEnum):
    moderate = "moderate"
    major = "major"


class ProductActiveIngredientSet(BaseModel):
    product_id: int
    active_ingredient: str = Field(..., min_length=1, max_length=200)


class ProductActiveIngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    active_ingredient: str


class InteractionCheckRequest(BaseModel):
    # Lista de productos que se piensan dispensar juntos (típicamente las
    # líneas de una DispensationOrder en borrador, pero es independiente
    # — DED-61: no depende de que la orden ya exista).
    product_ids: list[int] = Field(..., min_length=2)


class InteractionWarning(BaseModel):
    product_id_a: int
    product_id_b: int
    ingredient_a: str
    ingredient_b: str
    severity: InteractionSeverityEnum
    description: str


class InteractionCheckResult(BaseModel):
    warnings: list[InteractionWarning]
    # Productos del request que no tienen principio activo mapeado
    # (ProductActiveIngredient) y por lo tanto quedaron fuera del chequeo
    # — DED-59, expuesto explícitamente para que el frontend lo muestre
    # en vez de dar una falsa sensación de cobertura completa.
    unchecked_product_ids: list[int]


# ---------------------------------------------------------------------------------------------
# Módulo 18 — Aseguradoras [extendido]. Ver DED-62 a DED-64 en models.py.
# ---------------------------------------------------------------------------------------------
class InsuranceClaimStatusEnum(StrEnum):
    pending = "pending"
    submitted = "submitted"
    approved = "approved"
    paid = "paid"
    rejected = "rejected"


class InsuranceProviderCreate(BaseModel):
    contact_id: int
    default_coverage_percentage: Decimal | None = Field(None, ge=0, le=100)


class InsuranceProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    contact_id: int
    default_coverage_percentage: Decimal | None
    is_active: bool
    created_at: datetime


class PatientInsurancePolicyCreate(BaseModel):
    patient_contact_id: int
    insurance_provider_id: int
    policy_number: str = Field(..., min_length=1, max_length=100)
    coverage_percentage: Decimal = Field(..., ge=0, le=100)


class PatientInsurancePolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_contact_id: int
    insurance_provider_id: int
    policy_number: str
    coverage_percentage: Decimal
    is_active: bool
    created_at: datetime


class InsuranceClaimCreate(BaseModel):
    dispensation_order_id: int
    insurance_provider_id: int
    amount_total: Decimal = Field(..., gt=0)
    amount_patient_copay: Decimal = Field(..., ge=0)
    amount_claimed_insurer: Decimal = Field(..., ge=0)

    @model_validator(mode="after")
    def _validate_sum(self) -> InsuranceClaimCreate:
        if self.amount_patient_copay + self.amount_claimed_insurer != self.amount_total:
            raise ValueError("amount_patient_copay + amount_claimed_insurer debe ser igual a amount_total")
        return self


class InsuranceClaimReject(BaseModel):
    rejection_reason: str = Field(..., min_length=1, max_length=500)


class InsuranceClaimPay(BaseModel):
    # Monto que efectivamente pagó la aseguradora — puede ser menor al
    # reclamado (aprobación parcial); por defecto, el total reclamado.
    amount_paid: Decimal | None = Field(None, gt=0)


class InsuranceClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    dispensation_order_id: int
    insurance_provider_id: int
    patient_contact_id: int
    claim_number: str
    amount_total: Decimal
    amount_patient_copay: Decimal
    amount_claimed_insurer: Decimal
    status: InsuranceClaimStatusEnum
    billing_mode: str | None
    invoice_id: int | None
    payment_id: int | None
    rejection_reason: str | None
    created_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    paid_at: datetime | None
    rejected_at: datetime | None
