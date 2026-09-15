from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    event: str
    entity_type: str
    entity_id: int
    user_id: int | None
    correlation_id: str
    changes: dict | None
    created_at: datetime


class AuditRetentionPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    company_id: int
    retention_days: int
    updated_at: datetime


class AuditRetentionPolicyUpdate(BaseModel):
    retention_days: int = Field(..., ge=1, le=3650)


class AuditPurgeEligibleCount(BaseModel):
    """Respuesta de solo-lectura — cuántas filas están vencidas según la
    política vigente. NUNCA borra nada (ver AMB-07 en STATE.md: el
    trigger de inmutabilidad de `audit` bloquea DELETE/UPDATE
    incondicionalmente desde la capa de aplicación; el borrado físico es
    un procedimiento de mantenimiento fuera de la API — ver
    `scripts/purge_audit.py`)."""

    retention_days: int
    eligible_count: int
    excluded_medical_count: int
