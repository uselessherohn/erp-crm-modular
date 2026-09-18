from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContactBase(BaseModel):
    name: str = Field(..., max_length=300)
    is_customer: bool = False
    is_vendor: bool = False
    is_patient: bool = False
    is_lead: bool = False
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    tax_id: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def at_least_one_role(self) -> "ContactBase":
        # Regla de negocio no explícita en la spec pero razonable por
        # sentido común de dominio: un Contact sin ningún flag activo no
        # tiene motivo de existir en el sistema. DEDUCIBLE, documentado
        # en el cierre — no es un requisito literal de spec 2.3.
        if not any([self.is_customer, self.is_vendor, self.is_patient, self.is_lead]):
            raise ValueError("El contacto debe tener al menos un rol activo (cliente/proveedor/paciente/lead)")
        return self


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: str | None = Field(None, max_length=300)
    is_customer: bool | None = None
    is_vendor: bool | None = None
    is_patient: bool | None = None
    is_lead: bool | None = None
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    tax_id: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=500)
    is_active: bool | None = None


class ContactCreditLimitUpdate(BaseModel):
    """Endpoint separado, permiso separado (`contacts:contact:update_credit_limit`)
    — hallazgo real de la regresión QA externa, sep-2026: `credit_limit`
    (leído por `accounting.CreditControlService`) no tenía NINGÚN endpoint
    que lo expusiera para escritura. Se gatea aparte del PATCH general de
    contacto porque es un campo financiero sensible (quién puede subir el
    límite de crédito de un cliente no debería ser el mismo permiso que
    quién puede corregirle el teléfono)."""
    credit_limit: Decimal | None = Field(None, ge=0)


class ContactRead(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    credit_limit: Decimal | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
