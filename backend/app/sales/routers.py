from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_permission
from app.core.models import User
from app.sales import schemas
from app.sales.services import PriceListService, QuoteService, SalesOrderService

router = APIRouter(prefix="/sales", tags=["sales"])


# ---------------------------------------------------------------------------
# Listas de precios
# ---------------------------------------------------------------------------
@router.post("/price-lists", response_model=schemas.PriceListRead, status_code=201)
async def create_price_list(
    payload: schemas.PriceListCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("sales:price_list:create")),
) -> schemas.PriceListRead:
    pl = await PriceListService.create(db, company_id=company_id, payload=payload)
    return schemas.PriceListRead.model_validate(pl)


@router.get("/price-lists", response_model=list[schemas.PriceListRead])
async def list_price_lists(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("sales:price_list:list")),
) -> list[schemas.PriceListRead]:
    return [schemas.PriceListRead.model_validate(pl) for pl in await PriceListService.list(db, company_id=company_id)]


# ---------------------------------------------------------------------------
# Cotizaciones
# ---------------------------------------------------------------------------
@router.post("/quotes", response_model=schemas.QuoteRead, status_code=201)
async def create_quote(
    payload: schemas.QuoteCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:quote:create")),
) -> schemas.QuoteRead:
    quote = await QuoteService.create_draft(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.QuoteRead.model_validate(quote)


@router.get("/quotes", response_model=list[schemas.QuoteRead])
async def list_quotes(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("sales:quote:list")),
) -> list[schemas.QuoteRead]:
    return [schemas.QuoteRead.model_validate(q) for q in await QuoteService.list(db, company_id=company_id)]


@router.get("/quotes/{quote_id}", response_model=schemas.QuoteRead)
async def get_quote(
    quote_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("sales:quote:read")),
) -> schemas.QuoteRead:
    return schemas.QuoteRead.model_validate(await QuoteService.get(db, company_id=company_id, quote_id=quote_id))


@router.post("/quotes/{quote_id}/send", response_model=schemas.QuoteRead)
async def send_quote(
    quote_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:quote:send")),
) -> schemas.QuoteRead:
    return schemas.QuoteRead.model_validate(await QuoteService.send(db, company_id=company_id, quote_id=quote_id, actor_id=actor.id))


@router.post("/quotes/{quote_id}/accept", response_model=schemas.QuoteRead)
async def accept_quote(
    quote_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:quote:accept")),
) -> schemas.QuoteRead:
    return schemas.QuoteRead.model_validate(await QuoteService.accept(db, company_id=company_id, quote_id=quote_id, actor_id=actor.id))


@router.post("/quotes/{quote_id}/cancel", response_model=schemas.QuoteRead)
async def cancel_quote(
    quote_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:quote:cancel")),
) -> schemas.QuoteRead:
    return schemas.QuoteRead.model_validate(await QuoteService.cancel(db, company_id=company_id, quote_id=quote_id, actor_id=actor.id))


@router.post("/quotes/{quote_id}/convert", response_model=schemas.SalesOrderRead)
async def convert_quote(
    quote_id: int,
    warehouse_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:quote:convert")),
) -> schemas.SalesOrderRead:
    order = await QuoteService.convert_to_order(db, company_id=company_id, quote_id=quote_id, warehouse_id=warehouse_id, actor_id=actor.id)
    return schemas.SalesOrderRead.model_validate(order)


# ---------------------------------------------------------------------------
# Órdenes de venta
# ---------------------------------------------------------------------------
@router.post("/sales-orders", response_model=schemas.SalesOrderRead, status_code=201)
async def create_sales_order(
    payload: schemas.SalesOrderCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:order:create")),
) -> schemas.SalesOrderRead:
    order = await SalesOrderService.create_draft(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.SalesOrderRead.model_validate(order)


@router.get("/sales-orders", response_model=list[schemas.SalesOrderRead])
async def list_sales_orders(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("sales:order:list")),
) -> list[schemas.SalesOrderRead]:
    return [schemas.SalesOrderRead.model_validate(o) for o in await SalesOrderService.list(db, company_id=company_id)]


@router.get("/sales-orders/{order_id}", response_model=schemas.SalesOrderRead)
async def get_sales_order(
    order_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("sales:order:read")),
) -> schemas.SalesOrderRead:
    return schemas.SalesOrderRead.model_validate(await SalesOrderService.get(db, company_id=company_id, order_id=order_id))


@router.post("/sales-orders/{order_id}/confirm", response_model=schemas.SalesOrderRead)
async def confirm_sales_order(
    order_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:order:confirm")),
) -> schemas.SalesOrderRead:
    return schemas.SalesOrderRead.model_validate(await SalesOrderService.confirm(db, company_id=company_id, order_id=order_id, actor_id=actor.id))


@router.post("/sales-orders/{order_id}/start-preparation", response_model=schemas.SalesOrderRead)
async def start_preparation_sales_order(
    order_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:order:prepare")),
) -> schemas.SalesOrderRead:
    return schemas.SalesOrderRead.model_validate(
        await SalesOrderService.start_preparation(db, company_id=company_id, order_id=order_id, actor_id=actor.id)
    )


@router.post("/sales-orders/{order_id}/ship", response_model=schemas.SalesOrderRead)
async def ship_sales_order(
    order_id: int,
    payload: schemas.ShipSalesOrder,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:order:ship")),
) -> schemas.SalesOrderRead:
    order = await SalesOrderService.ship(db, company_id=company_id, order_id=order_id, payload=payload, actor_id=actor.id)
    return schemas.SalesOrderRead.model_validate(order)


@router.post("/sales-orders/{order_id}/invoice", response_model=schemas.SalesOrderRead)
async def invoice_sales_order(
    order_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:order:invoice")),
) -> schemas.SalesOrderRead:
    return schemas.SalesOrderRead.model_validate(
        await SalesOrderService.invoice(db, company_id=company_id, order_id=order_id, actor_id=actor.id)
    )


@router.post("/sales-orders/{order_id}/cancel", response_model=schemas.SalesOrderRead)
async def cancel_sales_order(
    order_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("sales:order:cancel")),
) -> schemas.SalesOrderRead:
    return schemas.SalesOrderRead.model_validate(
        await SalesOrderService.cancel(db, company_id=company_id, order_id=order_id, actor_id=actor.id)
    )
