from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClinicalRecordEntryTypeEnum(str, Enum):
    antecedent = "antecedent"
    allergy = "allergy"
    diagnosis = "diagnosis"
    note = "note"


class AppointmentStatusEnum(str, Enum):
    scheduled = "scheduled"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


# ---------------------------------------------------------------------------
# Expediente Clínico
# ---------------------------------------------------------------------------
class ClinicalRecordEntryCreate(BaseModel):
    patient_contact_id: int
    entry_type: ClinicalRecordEntryTypeEnum
    content: str = Field(..., min_length=1)
    # Si se provee, esta entrada es una CORRECCIÓN de `previous_entry_id`
    # (DED-25) — nunca se edita la anterior, se enlaza una nueva.
    previous_entry_id: int | None = None


class ClinicalRecordEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    patient_contact_id: int
    entry_type: ClinicalRecordEntryTypeEnum
    content: str
    previous_entry_id: int | None
    author_user_id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Agenda Médica
# ---------------------------------------------------------------------------
class AppointmentCreate(BaseModel):
    patient_contact_id: int
    professional_user_id: int
    scheduled_start: datetime
    scheduled_end: datetime
    reason: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _end_after_start(self) -> "AppointmentCreate":
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end debe ser posterior a scheduled_start")
        return self


class AppointmentReschedule(BaseModel):
    scheduled_start: datetime
    scheduled_end: datetime
    reason: str = Field(..., min_length=1, max_length=500)

    @model_validator(mode="after")
    def _end_after_start(self) -> "AppointmentReschedule":
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end debe ser posterior a scheduled_start")
        return self


class AppointmentCancel(BaseModel):
    cancellation_reason: str = Field(..., min_length=1, max_length=500)


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    patient_contact_id: int
    professional_user_id: int
    scheduled_start: datetime
    scheduled_end: datetime
    status: AppointmentStatusEnum
    reason: str | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------
class ConsultationCreate(BaseModel):
    appointment_id: int
    physical_exam: str | None = None
    diagnosis_cie10: str | None = Field(None, max_length=10)
    diagnosis_text: str | None = None
    treatment_plan: str | None = None


class ConsultationCorrect(BaseModel):
    """Corrección de una consulta ya existente (DED-25) — crea una fila
    nueva enlazada vía `previous_consultation_id`, la anterior queda
    marcada `superseded_by_id` pero nunca se modifica su contenido."""

    physical_exam: str | None = None
    diagnosis_cie10: str | None = Field(None, max_length=10)
    diagnosis_text: str | None = None
    treatment_plan: str | None = None


class ConsultationRead(BaseModel):
    id: int
    company_id: int
    appointment_id: int
    patient_contact_id: int
    professional_user_id: int
    physical_exam: str | None
    diagnosis_cie10: str | None
    diagnosis_text: str | None
    treatment_plan: str | None
    previous_consultation_id: int | None
    superseded_by_id: int | None
    created_by: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Módulo 10 — Recetas
# ---------------------------------------------------------------------------
class PrescriptionDispensingStatusEnum(str, Enum):
    not_applicable = "not_applicable"
    pending = "pending"
    dispensed = "dispensed"


class PrescriptionLineCreate(BaseModel):
    medication_name: str = Field(..., min_length=1, max_length=300)
    dosage: str = Field(..., min_length=1, max_length=100)
    route: str = Field(..., min_length=1, max_length=100)
    frequency: str = Field(..., min_length=1, max_length=100)
    duration: str = Field(..., min_length=1, max_length=100)


class PrescriptionLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    medication_name: str
    dosage: str
    route: str
    frequency: str
    duration: str
    dispensing_status: PrescriptionDispensingStatusEnum


class PrescriptionCreate(BaseModel):
    consultation_id: int
    notes: str | None = Field(None, max_length=500)
    lines: list[PrescriptionLineCreate] = Field(..., min_length=1)


class PrescriptionVoid(BaseModel):
    void_reason: str = Field(..., min_length=1, max_length=500)


class PrescriptionRead(BaseModel):
    id: int
    company_id: int
    consultation_id: int
    patient_contact_id: int
    professional_user_id: int
    notes: str | None
    voided_at: datetime | None
    void_reason: str | None
    issued_at: datetime
    created_by: int
    lines: list[PrescriptionLineRead]


# ---------------------------------------------------------------------------
# Módulo 11 — Laboratorio
# ---------------------------------------------------------------------------
class LabOrderStatusEnum(str, Enum):
    ordered = "ordered"
    completed = "completed"
    cancelled = "cancelled"


class LabOrderTestStatusEnum(str, Enum):
    pending = "pending"
    resulted = "resulted"


class LabOrderTestRequest(BaseModel):
    test_name: str = Field(..., min_length=1, max_length=300)


class LabOrderCreate(BaseModel):
    consultation_id: int
    tests: list[LabOrderTestRequest] = Field(..., min_length=1)


class LabOrderTestResult(BaseModel):
    result_value: str = Field(..., min_length=1, max_length=300)
    result_unit: str | None = Field(None, max_length=50)
    reference_range_text: str | None = Field(None, max_length=200)
    is_critical: bool = False


class LabOrderTestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    test_name: str
    status: LabOrderTestStatusEnum
    result_value: str | None
    result_unit: str | None
    reference_range_text: str | None
    is_critical: bool
    resulted_at: datetime | None
    resulted_by: int | None


class LabOrderRead(BaseModel):
    id: int
    company_id: int
    consultation_id: int
    patient_contact_id: int
    professional_user_id: int
    status: LabOrderStatusEnum
    ordered_at: datetime
    created_by: int
    tests: list[LabOrderTestRead]


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entity_type: str
    entity_id: int
    filename: str
    mime_type: str
    uploaded_by: int
    created_at: datetime
