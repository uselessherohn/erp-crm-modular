from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_package, require_permission
from app.core.models import User
from app.core.services import IdempotencyService
from app.ecommerce import schemas
from app.ecommerce.dependencies import ensure_ecommerce_active, get_public_db_context
from app.ecommerce.services import CartService, CatalogService, CheckoutService, EcommerceSettingsService, WebhookService
from app.shared.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Panel interno (protegido — JWT + RBAC + paquetes 'web'+ecommerce y
# 'administrative'+sales, spec 2.1/2.4)
# ---------------------------------------------------------------------------
router = APIRouter(
    prefix="/ecommerce",
    tags=["ecommerce"],
    dependencies=[
        Depends(require_package("web", minimal_module="ecommerce")),
        Depends(require_package("administrative", minimal_module="sales")),
    ],
)


@router.post("/settings", response_model=schemas.EcommerceSettingsCreated, status_code=201)
async def create_settings(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("ecommerce:settings:update")),
) -> schemas.EcommerceSettingsCreated:
    settings = await EcommerceSettingsService.create(db, company_id=company_id)
    return schemas.EcommerceSettingsCreated.model_validate(settings)


@router.get("/settings", response_model=schemas.EcommerceSettingsRead)
async def get_settings(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("ecommerce:settings:read")),
) -> schemas.EcommerceSettingsRead:
    settings = await EcommerceSettingsService.get_or_raise(db, company_id=company_id)
    return schemas.EcommerceSettingsRead.model_validate(settings)


@router.patch("/settings", response_model=schemas.EcommerceSettingsRead)
async def update_settings(
    payload: schemas.EcommerceSettingsUpdate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("ecommerce:settings:update")),
) -> schemas.EcommerceSettingsRead:
    settings = await EcommerceSettingsService.update(db, company_id=company_id, payload=payload)
    return schemas.EcommerceSettingsRead.model_validate(settings)


# ---------------------------------------------------------------------------
# Storefront público (sin JWT — spec 10). Gating manual (ver
# ecommerce/dependencies.py) porque `require_package` depende de JWT.
# ---------------------------------------------------------------------------
public_router = APIRouter(prefix="/public/ecommerce", tags=["ecommerce-public"])


@public_router.get("/{company_id}/catalog", response_model=list[schemas.CatalogItem])
async def get_public_catalog(company_id: int, db: AsyncSession = Depends(get_public_db_context)) -> list[schemas.CatalogItem]:
    await ensure_ecommerce_active(db, company_id=company_id)
    return await CatalogService.list_catalog(db, company_id=company_id)


@public_router.post("/{company_id}/carts", response_model=schemas.CartCreated, status_code=201)
async def create_cart(company_id: int, db: AsyncSession = Depends(get_public_db_context)) -> schemas.CartCreated:
    await ensure_ecommerce_active(db, company_id=company_id)
    cart, token = await CartService.create_cart(db, company_id=company_id)
    serialized = await CartService._serialize(db, cart)  # noqa: SLF001 — mismo módulo, no hay getter público redundante
    return schemas.CartCreated(**serialized.model_dump(), session_token=token)


@public_router.get("/{company_id}/carts/{cart_id}", response_model=schemas.CartRead)
async def get_cart(
    company_id: int,
    cart_id: int,
    x_cart_token: str = Header(..., alias="X-Cart-Token"),
    db: AsyncSession = Depends(get_public_db_context),
) -> schemas.CartRead:
    await ensure_ecommerce_active(db, company_id=company_id)
    return await CartService.get_cart(db, company_id=company_id, cart_id=cart_id, session_token=x_cart_token)


@public_router.post("/{company_id}/carts/{cart_id}/items", response_model=schemas.CartRead)
async def add_cart_item(
    company_id: int,
    cart_id: int,
    payload: schemas.AddCartItem,
    x_cart_token: str = Header(..., alias="X-Cart-Token"),
    db: AsyncSession = Depends(get_public_db_context),
) -> schemas.CartRead:
    await ensure_ecommerce_active(db, company_id=company_id)
    return await CartService.add_item(db, company_id=company_id, cart_id=cart_id, session_token=x_cart_token, payload=payload)


@public_router.post("/{company_id}/carts/{cart_id}/checkout", response_model=schemas.CheckoutResult, status_code=201)
async def checkout(
    company_id: int,
    cart_id: int,
    payload: schemas.CheckoutRequest,
    x_cart_token: str = Header(..., alias="X-Cart-Token"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_public_db_context),
) -> schemas.CheckoutResult:
    await ensure_ecommerce_active(db, company_id=company_id)

    async def _command() -> schemas.CheckoutResult:
        return await CheckoutService.checkout(db, company_id=company_id, cart_id=cart_id, session_token=x_cart_token, payload=payload)

    # domain="sales": no existe un TTL propio para "ecommerce" en
    # `IdempotencyService._TTL_HOURS_BY_DOMAIN` — spec 7 declara el mismo
    # TTL de 24h para sales/ecommerce juntos, así que se reutiliza el
    # mismo ajuste de configuración en vez de duplicarlo.
    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint=f"POST /public/ecommerce/{company_id}/carts/{cart_id}/checkout",
        payload_dict={**payload.model_dump(mode="json"), "cart_id": cart_id},
        domain="sales",
        success_status_code=201,
        command=_command,
    )


@public_router.post("/{company_id}/webhooks/{gateway}")
async def payment_webhook(
    company_id: int,
    gateway: str,
    request: Request,
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    db: AsyncSession = Depends(get_public_db_context),
) -> dict:
    await ensure_ecommerce_active(db, company_id=company_id)
    raw_body = await request.body()
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001 — cualquier body no-JSON es un error de validación del caller
        raise ValidationError("Body del webhook no es JSON válido") from exc

    return await WebhookService.handle_payment_event(
        db, company_id=company_id, gateway=gateway, raw_body=raw_body, payload=payload, signature=x_webhook_signature
    )
