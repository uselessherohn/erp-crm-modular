from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import schemas
from app.audit.services import DEFAULT_RETENTION_DAYS, AuditQueryService, AuditRetentionService
from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_package, require_permission
from app.core.models import User

# DEDUCIBLE (mismo criterio que `reports`, AMB-05 en STATE.md): `audit`
# (paquete completo, spec 8.1) vive DENTRO del paquete `administrative`
# ("Incluye: inventory, purchasing, sales, accounting, hr, reports,
# audit, notifications") — no tiene su propia fila en `company_packages`,
# a diferencia de `medical`/`pharmacy`/`web`. Gatea con el paquete
# `administrative` completo, no con un paquete `audit` que no existe.
router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_package("administrative"))])


@router.get("/logs", response_model=list[schemas.AuditLogRead])
async def list_audit_logs(
    entity_type: str | None = Query(None),
    event: str | None = Query(None),
    user_id: int | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("audit:log:read")),
) -> list[schemas.AuditLogRead]:
    logs = await AuditQueryService.list_events(
        db, company_id=company_id, entity_type=entity_type, event=event, user_id=user_id,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )
    return [schemas.AuditLogRead.model_validate(log) for log in logs]


@router.get("/retention-policy", response_model=schemas.AuditRetentionPolicyRead)
async def get_retention_policy(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("audit:retention:read")),
) -> schemas.AuditRetentionPolicyRead:
    policy = await AuditRetentionService.get_policy(db, company_id=company_id)
    if policy is None:
        # Sin fila propia todavía — se informa el default de spec (90
        # días) en vez de un 404, porque "sin configurar" es un estado
        # válido y esperado, no un error.
        return schemas.AuditRetentionPolicyRead(
            company_id=company_id, retention_days=DEFAULT_RETENTION_DAYS, updated_at=datetime.now(UTC),
        )
    return schemas.AuditRetentionPolicyRead.model_validate(policy)


@router.put("/retention-policy", response_model=schemas.AuditRetentionPolicyRead)
async def update_retention_policy(
    payload: schemas.AuditRetentionPolicyUpdate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("audit:retention:update")),
) -> schemas.AuditRetentionPolicyRead:
    policy = await AuditRetentionService.set_policy(db, company_id=company_id, payload=payload)
    return schemas.AuditRetentionPolicyRead.model_validate(policy)


@router.get("/retention-policy/purge-eligible", response_model=schemas.AuditPurgeEligibleCount)
async def get_purge_eligible_count(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("audit:retention:read")),
) -> schemas.AuditPurgeEligibleCount:
    """Solo cuenta — nunca borra. Ver AMB-07 en STATE.md: el borrado
    físico real es un procedimiento de mantenimiento fuera de esta API
    (`scripts/purge_audit.py`), no un endpoint HTTP."""
    return await AuditRetentionService.count_purge_eligible(db, company_id=company_id)
