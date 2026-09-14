from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_package, require_permission
from app.core.models import User
from app.reports import schemas
from app.reports.services import DashboardService, ExportService, MetricService

# DEDUCIBLE (ver STATE.md AMB pendiente): `reports` requiere el paquete
# `administrative` completo (sin `minimal_module`) — a diferencia de
# `notifications` (módulo 26, exento de gating por ser infraestructura
# transversal), `reports` sí es una capa de negocio sobre datos del
# Administrativo, no algo que todos los paquetes verticales necesiten
# usar. No confirmado por Roberto.
router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_package("administrative"))])


@router.get("/metrics", response_model=list[schemas.MetricInfo])
async def list_metrics(_actor: User = Depends(require_permission("reports:metric:read"))) -> list[schemas.MetricInfo]:
    return MetricService.list_metrics()


@router.get("/metrics/{metric_key}/data", response_model=schemas.MetricDataResult)
async def get_metric_data(
    metric_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("reports:metric:read")),
) -> schemas.MetricDataResult:
    return await MetricService.run(db, company_id=company_id, metric_key=metric_key, date_from=date_from, date_to=date_to)


_EXPORT_MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.get("/metrics/{metric_key}/export")
async def export_metric(
    metric_key: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
    format: str = Query(..., pattern="^(csv|xlsx|pdf)$"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("reports:export:run")),
) -> Response:
    result = await MetricService.run(db, company_id=company_id, metric_key=metric_key, date_from=date_from, date_to=date_to)

    if format == "csv":
        content = ExportService.to_csv(columns=result.columns, rows=result.rows)
    elif format == "xlsx":
        content = ExportService.to_xlsx(title=metric_key, columns=result.columns, rows=result.rows)
    else:
        content = ExportService.to_pdf(title=metric_key, columns=result.columns, rows=result.rows)

    filename = f"{metric_key}_{date_from}_{date_to}.{format}"
    return Response(
        content=content,
        media_type=_EXPORT_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/dashboards", response_model=schemas.DashboardRead, status_code=201)
async def create_dashboard(
    payload: schemas.DashboardCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("reports:dashboard:create")),
) -> schemas.DashboardRead:
    dashboard = await DashboardService.create(db, company_id=company_id, payload=payload, owner_user_id=actor.id)
    return schemas.DashboardRead.model_validate(dashboard)


@router.get("/dashboards", response_model=list[schemas.DashboardRead])
async def list_dashboards(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("reports:dashboard:list")),
) -> list[schemas.DashboardRead]:
    dashboards = await DashboardService.list(db, company_id=company_id)
    return [schemas.DashboardRead.model_validate(d) for d in dashboards]


@router.get("/dashboards/{dashboard_id}", response_model=schemas.DashboardRead)
async def get_dashboard(
    dashboard_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("reports:dashboard:read")),
) -> schemas.DashboardRead:
    dashboard = await DashboardService.get(db, company_id=company_id, dashboard_id=dashboard_id)
    return schemas.DashboardRead.model_validate(dashboard)


@router.patch("/dashboards/{dashboard_id}", response_model=schemas.DashboardRead)
async def update_dashboard(
    dashboard_id: int,
    payload: schemas.DashboardUpdate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("reports:dashboard:update")),
) -> schemas.DashboardRead:
    dashboard = await DashboardService.update(db, company_id=company_id, dashboard_id=dashboard_id, payload=payload, actor_id=actor.id)
    return schemas.DashboardRead.model_validate(dashboard)


@router.delete("/dashboards/{dashboard_id}", status_code=204)
async def delete_dashboard(
    dashboard_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("reports:dashboard:delete")),
) -> None:
    await DashboardService.delete(db, company_id=company_id, dashboard_id=dashboard_id, actor_id=actor.id)
