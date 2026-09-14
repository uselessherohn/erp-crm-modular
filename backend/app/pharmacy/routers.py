"""
Routers de pharmacy. Todas las rutas exigen el paquete `pharmacy` activo.
Sin RBAC "own patients"/"read-all" (a diferencia de `medical`) — la spec
8.3 no exige ese patrón para Farmacéutico como sí lo hace 8.2 para
Médico; permisos planos, mismo estilo que `sales`/`purchasing`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_package, require_permission
from app.core.models import User
from app.pharmacy import schemas
from app.pharmacy.services import ControlledSubstanceLogService, ControlledSubstanceService, DispensationService

router = APIRouter(prefix="/pharmacy", tags=["pharmacy"], dependencies=[Depends(require_package("pharmacy"))])


# ---------------------------------------------------------------------------------
# Dispensación / POS Farmacia
# ---------------------------------------------------------------------------
@router.post("/dispensations", response_model=schemas.DispensationOrderRead, status_code=201)
async def create_dispensation(
    payload: schemas.DispensationOrderCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:dispensation:create")),
) -> schemas.DispensationOrderRead:
    return await DispensationService.create(db, company_id=company_id, payload=payload, dispensed_by=actor.id)


@router.get("/dispensations/{order_id}", response_model=schemas.DispensationOrderRead)
async def get_dispensation(
    order_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:dispensation:read")),
) -> schemas.DispensationOrderRead:
    return await DispensationService.get(db, company_id=company_id, order_id=order_id)


@router.get("/patients/{patient_contact_id}/dispensations", response_model=list[schemas.DispensationOrderRead])
async def list_dispensations_for_patient(
    patient_contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:dispensation:read")),
) -> list[schemas.DispensationOrderRead]:
    return await DispensationService.list_for_patient(db, company_id=company_id, patient_contact_id=patient_contact_id)


@router.post("/dispensations/{order_id}/void", response_model=schemas.DispensationOrderRead)
async def void_dispensation(
    order_id: int,
    payload: schemas.DispensationVoid,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:dispensation:create")),
) -> schemas.DispensationOrderRead:
    return await DispensationService.void(db, company_id=company_id, order_id=order_id, payload=payload, actor_id=actor.id)


# ---------------------------------------------------------------------------------
# Sustancias Controladas
# ---------------------------------------------------------------------------
@router.post("/controlled-substances", response_model=schemas.ControlledSubstanceProductRead, status_code=201)
async def mark_controlled_substance(
    payload: schemas.ControlledSubstanceMark,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:controlled_substance:manage")),
) -> schemas.ControlledSubstanceProductRead:
    row = await ControlledSubstanceService.mark(db, company_id=company_id, product_id=payload.product_id, created_by=actor.id)
    return schemas.ControlledSubstanceProductRead.model_validate(row)


@router.delete("/controlled-substances/{product_id}", status_code=204)
async def unmark_controlled_substance(
    product_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:controlled_substance:manage")),
) -> None:
    await ControlledSubstanceService.unmark(db, company_id=company_id, product_id=product_id)


@router.get("/controlled-substances", response_model=list[schemas.ControlledSubstanceProductRead])
async def list_controlled_substances(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:controlled_substance:manage")),
) -> list[schemas.ControlledSubstanceProductRead]:
    rows = await ControlledSubstanceService.list(db, company_id=company_id)
    return [schemas.ControlledSubstanceProductRead.model_validate(r) for r in rows]


@router.get("/controlled-substances/log", response_model=list[schemas.ControlledSubstanceLogEntryRead])
async def list_controlled_substance_log(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:controlled_substance:read-log")),
) -> list[schemas.ControlledSubstanceLogEntryRead]:
    rows = await ControlledSubstanceLogService.list(db, company_id=company_id)
    return [schemas.ControlledSubstanceLogEntryRead.model_validate(r) for r in rows]
