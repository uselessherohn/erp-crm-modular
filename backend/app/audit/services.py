from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import models, schemas
from app.core.models import AuditLog

DEFAULT_RETENTION_DAYS = 90
"""Spec 8.1: "rotación estándar, ej. 90 días" — usado cuando la compañía
no configuró explícitamente una `AuditRetentionPolicy`."""

MEDICAL_EVENT_PREFIX = "medical."
"""Todo evento registrado por `medical` (expediente, recetas, laboratorio,
teleconsulta, facturación, mensajería, reserva pública — ver
`app/medical/services.py`) usa este prefijo. Spec 8.1 excluye de
cualquier retención/depuración general "los registros de acceso al
expediente clínico descritos en 8.2" — se interpreta acá, de forma
deliberadamente conservadora, como TODO el namespace `medical.*` y no
solo un subconjunto de esos eventos (ej. solo lecturas): distinguir
"acceso al expediente" de "cualquier otro evento clínico" con precisión
requeriría una clasificación evento por evento que la spec no da, y
errar hacia proteger de más datos de salud es la lectura más segura
ante una obligación regulatoria, no solo la más simple de implementar.
Ver DED-60 en STATE.md."""


class AuditQueryService:
    """"Registro de Actividad" [core] — lectura sobre la misma tabla
    `audit` creada en el módulo 1 (`app.core.models.AuditLog`). Este
    módulo no posee esa tabla, solo la consulta (mismo patrón que
    `reports`, que lee tablas de `sales`/`accounting`/`inventory` sin
    poseerlas)."""

    @staticmethod
    async def list_events(
        db: AsyncSession,
        *,
        company_id: int,
        entity_type: str | None = None,
        event: str | None = None,
        user_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        stmt = select(AuditLog).where(AuditLog.company_id == company_id)
        if entity_type is not None:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if event is not None:
            stmt = stmt.where(AuditLog.event == event)
        if user_id is not None:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if date_from is not None:
            stmt = stmt.where(AuditLog.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(AuditLog.created_at <= date_to)
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())


class AuditRetentionService:
    """"Retención y Depuración" [core] — la parte de "Depuración" queda
    deliberadamente limitada a CONTAR filas elegibles, no a borrarlas.
    Ver AMB-07 en STATE.md para por qué el borrado físico real no puede
    exponerse como endpoint de esta API."""

    @staticmethod
    async def get_policy(db: AsyncSession, *, company_id: int) -> models.AuditRetentionPolicy | None:
        result = await db.execute(
            select(models.AuditRetentionPolicy).where(models.AuditRetentionPolicy.company_id == company_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_retention_days(db: AsyncSession, *, company_id: int) -> int:
        policy = await AuditRetentionService.get_policy(db, company_id=company_id)
        return policy.retention_days if policy is not None else DEFAULT_RETENTION_DAYS

    @staticmethod
    async def set_policy(db: AsyncSession, *, company_id: int, payload: schemas.AuditRetentionPolicyUpdate) -> models.AuditRetentionPolicy:
        policy = await AuditRetentionService.get_policy(db, company_id=company_id)
        if policy is None:
            policy = models.AuditRetentionPolicy(company_id=company_id, retention_days=payload.retention_days)
            db.add(policy)
        else:
            policy.retention_days = payload.retention_days
        await db.commit()
        await db.refresh(policy)
        return policy

    @staticmethod
    async def count_purge_eligible(db: AsyncSession, *, company_id: int) -> schemas.AuditPurgeEligibleCount:
        retention_days = await AuditRetentionService.get_retention_days(db, company_id=company_id)
        cutoff = func.now() - func.make_interval(0, 0, 0, retention_days)

        eligible_stmt = select(func.count()).select_from(AuditLog).where(
            AuditLog.company_id == company_id,
            AuditLog.created_at < cutoff,
            ~AuditLog.event.like(f"{MEDICAL_EVENT_PREFIX}%"),
        )
        excluded_stmt = select(func.count()).select_from(AuditLog).where(
            AuditLog.company_id == company_id,
            AuditLog.created_at < cutoff,
            AuditLog.event.like(f"{MEDICAL_EVENT_PREFIX}%"),
        )
        eligible_count = (await db.execute(eligible_stmt)).scalar_one()
        excluded_count = (await db.execute(excluded_stmt)).scalar_one()
        return schemas.AuditPurgeEligibleCount(
            retention_days=retention_days, eligible_count=eligible_count, excluded_medical_count=excluded_count,
        )
