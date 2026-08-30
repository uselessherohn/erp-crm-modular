"""
Routers de pipeline — primer módulo del proyecto donde `require_package`
(scaffoldeado desde el módulo 1, nunca antes usado en un router real) se
aplica de verdad, spec 2.3: "activable solo si el paquete Administrativo
está presente". DED-19: reutiliza `PACKAGE_NOT_LICENSED` (403) en vez de
inventar el literal `UNSUPPORTED_WITHOUT_ADMIN_PACKAGE` como código nuevo.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_package, require_permission
from app.core.models import User
from app.pipeline import schemas
from app.pipeline.services import ActivityService, OpportunityService, StageService

router = APIRouter(
    prefix="/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(require_package("administrative"))],
)


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------
@router.post("/stages", response_model=schemas.StageRead, status_code=201)
async def create_stage(
    payload: schemas.StageCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pipeline:stage:create")),
) -> schemas.StageRead:
    stage = await StageService.create(db, company_id=company_id, payload=payload)
    return schemas.StageRead.model_validate(stage)


@router.get("/stages", response_model=list[schemas.StageRead])
async def list_stages(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pipeline:stage:list")),
) -> list[schemas.StageRead]:
    return [schemas.StageRead.model_validate(s) for s in await StageService.list(db, company_id=company_id)]


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------
@router.post("/opportunities", response_model=schemas.OpportunityRead, status_code=201)
async def create_opportunity(
    payload: schemas.OpportunityCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pipeline:opportunity:create")),
) -> schemas.OpportunityRead:
    opportunity = await OpportunityService.create(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.OpportunityRead.model_validate(opportunity)


@router.get("/opportunities", response_model=list[schemas.OpportunityRead])
async def list_opportunities(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pipeline:opportunity:list")),
) -> list[schemas.OpportunityRead]:
    return [schemas.OpportunityRead.model_validate(o) for o in await OpportunityService.list(db, company_id=company_id)]


@router.get("/opportunities/{opportunity_id}", response_model=schemas.OpportunityRead)
async def get_opportunity(
    opportunity_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pipeline:opportunity:read")),
) -> schemas.OpportunityRead:
    opportunity = await OpportunityService.get(db, company_id=company_id, opportunity_id=opportunity_id)
    return schemas.OpportunityRead.model_validate(opportunity)


@router.post("/opportunities/{opportunity_id}/move-stage", response_model=schemas.OpportunityRead)
async def move_opportunity_stage(
    opportunity_id: int,
    payload: schemas.OpportunityMoveStage,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pipeline:opportunity:move_stage")),
) -> schemas.OpportunityRead:
    opportunity = await OpportunityService.move_stage(
        db, company_id=company_id, opportunity_id=opportunity_id, payload=payload, actor_id=actor.id
    )
    return schemas.OpportunityRead.model_validate(opportunity)


@router.post("/opportunities/{opportunity_id}/close-won", response_model=schemas.OpportunityRead)
async def close_opportunity_won(
    opportunity_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pipeline:opportunity:close")),
) -> schemas.OpportunityRead:
    opportunity = await OpportunityService.close_won(db, company_id=company_id, opportunity_id=opportunity_id, actor_id=actor.id)
    return schemas.OpportunityRead.model_validate(opportunity)


@router.post("/opportunities/{opportunity_id}/close-lost", response_model=schemas.OpportunityRead)
async def close_opportunity_lost(
    opportunity_id: int,
    payload: schemas.OpportunityCloseLost,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pipeline:opportunity:close")),
) -> schemas.OpportunityRead:
    opportunity = await OpportunityService.close_lost(
        db, company_id=company_id, opportunity_id=opportunity_id, payload=payload, actor_id=actor.id
    )
    return schemas.OpportunityRead.model_validate(opportunity)


@router.post("/opportunities/{opportunity_id}/reopen", response_model=schemas.OpportunityRead)
async def reopen_opportunity(
    opportunity_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pipeline:opportunity:reopen")),
) -> schemas.OpportunityRead:
    opportunity = await OpportunityService.reopen(db, company_id=company_id, opportunity_id=opportunity_id, actor_id=actor.id)
    return schemas.OpportunityRead.model_validate(opportunity)


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------
@router.post("/activities", response_model=schemas.ActivityRead, status_code=201)
async def create_activity(
    payload: schemas.ActivityCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pipeline:activity:create")),
) -> schemas.ActivityRead:
    activity = await ActivityService.create(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.ActivityRead.model_validate(activity)


@router.get("/activities", response_model=list[schemas.ActivityRead])
async def list_activities(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pipeline:activity:list")),
) -> list[schemas.ActivityRead]:
    return [schemas.ActivityRead.model_validate(a) for a in await ActivityService.list(db, company_id=company_id)]


@router.post("/activities/{activity_id}/complete", response_model=schemas.ActivityRead)
async def complete_activity(
    activity_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pipeline:activity:complete")),
) -> schemas.ActivityRead:
    activity = await ActivityService.complete(db, company_id=company_id, activity_id=activity_id)
    return schemas.ActivityRead.model_validate(activity)
