from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class NotificationChannelEnum(StrEnum):
    in_app = "in_app"
    email = "email"


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------
class NotificationTemplateCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    subject_template: str = Field(..., min_length=1, max_length=300)
    body_template: str = Field(..., min_length=1)


class NotificationTemplateUpdate(BaseModel):
    subject_template: str | None = Field(None, min_length=1, max_length=300)
    body_template: str | None = Field(None, min_length=1)


class NotificationTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    code: str
    subject_template: str
    body_template: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Notificaciones
# ---------------------------------------------------------------------------
class NotificationSend(BaseModel):
    recipient_user_id: int
    channel: NotificationChannelEnum = NotificationChannelEnum.in_app
    # Opción A: título/cuerpo directos.
    title: str | None = Field(None, max_length=300)
    body: str | None = None
    # Opción B: plantilla + contexto para placeholders {var} (DED-29).
    template_code: str | None = Field(None, max_length=100)
    context: dict[str, str] = Field(default_factory=dict)

    def has_direct_content(self) -> bool:
        return self.title is not None and self.body is not None


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    recipient_user_id: int
    channel: NotificationChannelEnum
    title: str
    body: str
    template_code: str | None
    email_status: str | None
    read_at: datetime | None
    created_at: datetime
