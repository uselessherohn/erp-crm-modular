from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_permission
from app.core.models import User
from app.purchasing import schemas
from app.purchasing.services import PurchaseOrderService

router = APIRouter(prefix="/purchasing/purchase-orders", tags=["purchasing"])


@router.post("", response_model=schemas.PurchaseOrderRead, status_code=201)
async def create_purchase_order(
    payload: schemas.PurchaseOrderCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("purchasing:po:create")),
) -> schemas.PurchaseOrderRead:
    po = await PurchaseOrderService.create_draft(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.PurchaseOrderRead.model_validate(po)


@router.get("", response_model=list[schemas.PurchaseOrderRead])
async def list_purchase_orders(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("purchasing:po:list")),
) -> list[schemas.PurchaseOrderRead]:
    orders = await PurchaseOrderService.list(db, company_id=company_id)
    return [schemas.PurchaseOrderRead.model_validate(po) for po in orders]


@router.get("/{po_id}", response_model=schemas.PurchaseOrderRead)
async def get_purchase_order(
    po_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("purchasing:po:read")),
) -> schemas.PurchaseOrderRead:
    po = await PurchaseOrderService.get(db, company_id=company_id, po_id=po_id)
    return schemas.PurchaseOrderRead.model_validate(po)


@router.post("/{po_id}/confirm", response_model=schemas.PurchaseOrderRead)
async def confirm_purchase_order(
    po_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("purchasing:po:confirm")),
) -> schemas.PurchaseOrderRead:
    po = await PurchaseOrderService.confirm(db, company_id=company_id, po_id=po_id, actor_id=actor.id)
    return schemas.PurchaseOrderRead.model_validate(po)


@router.post("/{po_id}/cancel", response_model=schemas.PurchaseOrderRead)
async def cancel_purchase_order(
    po_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("purchasing:po:cancel")),
) -> schemas.PurchaseOrderRead:
    po = await PurchaseOrderService.cancel(db, company_id=company_id, po_id=po_id, actor_id=actor.id)
    return schemas.PurchaseOrderRead.model_validate(po)


@router.post("/{po_id}/receive", response_model=schemas.PurchaseOrderRead)
async def receive_purchase_order(
    po_id: int,
    payload: schemas.ReceivePurchaseOrder,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("purchasing:po:receive")),
) -> schemas.PurchaseOrderRead:
    po = await PurchaseOrderService.receive(db, company_id=company_id, po_id=po_id, payload=payload, actor_id=actor.id)
    return schemas.PurchaseOrderRead.model_validate(po)


@router.post("/{po_id}/close", response_model=schemas.PurchaseOrderRead)
async def close_purchase_order(
    po_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("purchasing:po:close")),
) -> schemas.PurchaseOrderRead:
    po = await PurchaseOrderService.close(db, company_id=company_id, po_id=po_id, actor_id=actor.id)
    return schemas.PurchaseOrderRead.model_validate(po)
