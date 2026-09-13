from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PageBase(BaseModel):
    # DEDUCIBLE: slug restringido a kebab-case (spec no lo especifica) —
    # mismo criterio defensivo que el resto del proyecto aplica a
    # identificadores usados en URLs públicas.
    slug: str = Field(..., max_length=150, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(..., max_length=300)
    content: str = ""


class PageCreate(PageBase):
    pass


class PageUpdate(BaseModel):
    title: str | None = Field(None, max_length=300)
    content: str | None = None


class PageRead(PageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    status: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FormSubmissionCreate(BaseModel):
    form_name: str = Field(..., max_length=100)
    page_id: int | None = None
    name: str = Field(..., max_length=300)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    message: str | None = None
    # Campos adicionales del formulario sin esquema fijo (ver models.py) —
    # se guardan tal cual en el payload, sin alimentar ningún campo
    # normalizado de Contact.
    extra: dict = Field(default_factory=dict)


class FormSubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    page_id: int | None
    form_name: str
    payload: dict
    contact_id: int
    created_at: datetime
