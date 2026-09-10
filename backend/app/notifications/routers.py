"""
Routers de notifications. Sin `require_package` — módulo Transversal
(ver docstring de `models.py`). Lectura de notificaciones siempre
filtrada por `recipient_user_id = actor.id`, sin permiso adicional — es
inherentemente personal.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_current_user, get_db_with_tenant_context, require_permission
from app.core.models import User
from app.notifications import schemas
from app.notifications.services import NotificationService, NotificationTemplateService

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------
@router.post("/templates", response_model=schemas.NotificationTemplateRead, status_code=201)
async def create_template(
    payload: schemas.NotificationTemplateCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("notifications:template:create")),
) -> schemas.NotificationTemplateRead:
    template = await NotificationTemplateService.create(db, company_id=company_id, payload=payload)
    return schemas.NotificationTemplateRead.model_validate(template)


@router.get("/templates", response_model=list[schemas.NotificationTemplateRead])
async def list_templates(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("notifications:template:list")),
) -> list[schemas.NotificationTemplateRead]:
    templates = await NotificationTemplateService.list(db, company_id=company_id)
    return [schemas.NotificationTemplateRead.model_validate(t) for t in templates]


@router.patch("/templates/{code}", response_model=schemas.NotificationTemplateRead)
async def update_template(
    code: str,
    payload: schemas.NotificationTemplateUpdate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("notifications:template:create")),
) -> schemas.NotificationTemplateRead:
    template = await NotificationTemplateService.update(db, company_id=company_id, code=code, payload=payload)
    return schemas.NotificationTemplateRead.model_validate(template)


# ---------------------------------------------------------------------------
# Notificaciones
# ---------------------------------------------------------------------------
@router.post("/send", response_model=schemas.NotificationRead, status_code=201)
async def send_notification(
    payload: schemas.NotificationSend,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("notifications:notification:send")),
) -> schemas.NotificationRead:
    recipient_email = None
    if payload.channel == schemas.NotificationChannelEnum.email:
        from sqlalchemy import select as sa_select

        row = (await db.execute(sa_select(User.email).where(User.id == payload.recipient_user_id))).scalar_one_or_none()
        recipient_email = row
    notification = await NotificationService.send(
        db, company_id=company_id, payload=payload, recipient_email=recipient_email
    )
    return schemas.NotificationRead.model_validate(notification)


@router.get("", response_model=list[schemas.NotificationRead])
async def list_my_notifications(
    unread_only: bool = False,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> list[schemas.NotificationRead]:
    notifications = await NotificationService.list_for_user(
        db, company_id=company_id, user_id=actor.id, unread_only=unread_only
    )
    return [schemas.NotificationRead.model_validate(n) for n in notifications]


@router.post("/{notification_id}/read", response_model=schemas.NotificationRead)
async def mark_notification_read(
    notification_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> schemas.NotificationRead:
    notification = await NotificationService.mark_read(
        db, company_id=company_id, user_id=actor.id, notification_id=notification_id
    )
    return schemas.NotificationRead.model_validate(notification)


@router.post("/read-all", response_model=dict)
async def mark_all_notifications_read(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> dict:
    count = await NotificationService.mark_all_read(db, company_id=company_id, user_id=actor.id)
    return {"marked_read": count}
