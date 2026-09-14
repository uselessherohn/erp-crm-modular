from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DispensationStatusEnum(str, Enum):
    dispensed = "dispensed"
    voided = "voided"


class AllergyCheckSourceEnum(str, Enum):
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
    def _prescription_xor_walkin(self) -> "DispensationOrderCreate":
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
