"""
Schemas Pydantic v2 del módulo core.

Nota (spec sección 7, Regla 3 del Mensaje 0): estos son los schemas que
`openapi.json` expondrá en Fase 2.5. El frontend (Fase 3) generará Zod desde
ese `openapi.json` — nunca a mano. No hay endpoints todavía (esa es Fase 2);
estos son los contratos de entrada/salida que los servicios usarán.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Enums compartidos (mismos valores que app.core.models)
# ---------------------------------------------------------------------------
class PackageEnum(str, Enum):
    administrative = "administrative"
    medical = "medical"
    pharmacy = "pharmacy"
    web = "web"


class PackageStatusEnum(str, Enum):
    active = "active"
    suspended = "suspended"
    deactivated = "deactivated"


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------
class CompanyBase(BaseModel):
    name: str = Field(..., max_length=200)
    tax_id: str | None = Field(None, max_length=50)
    timezone: str = Field(default="America/Tegucigalpa", max_length=50)
    currency_code: str = Field(default="HNL", max_length=3)
    locale: str = Field(default="es-HN", max_length=10)


class CompanyCreate(CompanyBase):
    pass


class CompanyRead(CompanyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Permission / Role
# ---------------------------------------------------------------------------
class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str = Field(..., description="Formato modulo:accion, ej. sales:create")
    description: str | None = None


class RoleBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: str | None = Field(None, max_length=300)


class RoleCreate(RoleBase):
    permission_ids: list[int] = Field(default_factory=list)


class RoleRead(RoleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    is_active: bool
    permissions: list[PermissionRead] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., max_length=200)
    locale: str | None = Field(None, max_length=10)
    timezone: str | None = Field(None, max_length=50)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    role_ids: list[int] = Field(default_factory=list)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Attachment
# ---------------------------------------------------------------------------
class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    filename: str
    mime_type: str
    uploaded_by: int
    created_at: datetime


# ---------------------------------------------------------------------------
# CompanyPackage (spec sección 2.4)
# ---------------------------------------------------------------------------
class CompanyPackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    package: PackageEnum
    activated_at: datetime
    minimal_modules: list[str] | None = None
    status: PackageStatusEnum
    suspended_at: datetime | None = None
    deactivated_at: datetime | None = None
    status_reason: str | None = None


# ---------------------------------------------------------------------------
# Error uniforme (spec sección 7)
# ---------------------------------------------------------------------------
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
