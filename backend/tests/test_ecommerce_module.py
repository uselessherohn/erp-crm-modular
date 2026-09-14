"""
Tests de integración del módulo ecommerce — contra PostgreSQL real, mismo
patrón que tests/test_website_module.py y tests/test_contacts_module.py.

NOTA DE ESTE CIERRE: escritos y revisados estáticamente (sintaxis, imports,
consistencia de firmas con services.py/models.py de ecommerce, sales,
accounting e inventory) pero NO ejecutados — mismo motivo y misma
advertencia que en `test_website_module.py` (sin Postgres/red en este
entorno). Correr `pytest tests/test_ecommerce_module.py` contra una base
real antes de marcar el módulo 23 como (✓) en STATE.md.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core import models as core_models
from app.database import AsyncSessionLocal
from app.ecommerce import models as ecommerce_models
from app.ecommerce import schemas as ecommerce_schemas
from app.ecommerce.services import CartService, CatalogService, CheckoutService, EcommerceSettingsService, WebhookService
from app.inventory import schemas as inventory_schemas
from app.inventory.services import ProductService, WarehouseService
from app.sales import schemas as sales_schemas
from app.sales.services import PriceListService
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def company(db):
    unique = uuid.uuid4().hex[:8]
    c = core_models.Company(name=f"Test Co {unique}", tax_id=unique)
    db.add(c)
    await db.flush()
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(c.id)})
    await db.commit()
    return c


@pytest_asyncio.fixture
async def store(db, company):
    """Almacén + lista de precios por defecto + un producto con precio —
    lo mínimo que `EcommerceSettingsService`/`CatalogService` necesitan
    para funcionar."""
    warehouse = await WarehouseService.create(db, company_id=company.id, payload=inventory_schemas.WarehouseCreate(name="Bodega Online"))
    product = await ProductService.create(
        db, company_id=company.id, created_by=None,
        payload=inventory_schemas.ProductCreate(sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Producto de Prueba", product_type="facturable"),
    )
    price_list = await PriceListService.create(
        db, company_id=company.id,
        payload=sales_schemas.PriceListCreate(
            name="Lista Base", is_default=True,
            items=[sales_schemas.PriceListItemCreate(product_id=product.id, unit_price=Decimal("100.00"))],
        ),
    )
    settings = await EcommerceSettingsService.create(db, company_id=company.id)
    settings = await EcommerceSettingsService.update(
        db, company_id=company.id,
        payload=ecommerce_schemas.EcommerceSettingsUpdate(default_warehouse_id=warehouse.id, default_price_list_id=price_list.id),
    )
    return {"warehouse": warehouse, "product": product, "price_list": price_list, "settings": settings}


@pytest.mark.asyncio
async def test_checkout_requires_settings_configured(db, company):
    with pytest.raises(ValidationError):
        await CatalogService.list_catalog(db, company_id=company.id)


@pytest.mark.asyncio
async def test_catalog_lists_only_priced_products(db, company, store):
    catalog = await CatalogService.list_catalog(db, company_id=company.id)
    assert len(catalog) == 1
    assert catalog[0].product_id == store["product"].id
    assert catalog[0].unit_price == Decimal("100.00")


@pytest.mark.asyncio
async def test_cart_create_add_item_and_checkout_creates_sales_order(db, company, store):
    cart, token = await CartService.create_cart(db, company_id=company.id)

    cart_read = await CartService.add_item(
        db, company_id=company.id, cart_id=cart.id, session_token=token,
        payload=ecommerce_schemas.AddCartItem(product_id=store["product"].id, quantity=Decimal("2")),
    )
    assert len(cart_read.items) == 1
    assert cart_read.items[0].unit_price_snapshot == Decimal("100.00")

    result = await CheckoutService.checkout(
        db, company_id=company.id, cart_id=cart.id, session_token=token,
        payload=ecommerce_schemas.CheckoutRequest(name="Cliente Prueba", email="cliente@example.com"),
    )
    assert result.status == "draft"
    assert result.total_lines == 1

    # El carrito ya no debería aceptar más cambios.
    with pytest.raises(ConflictError):
        await CheckoutService.checkout(
            db, company_id=company.id, cart_id=cart.id, session_token=token,
            payload=ecommerce_schemas.CheckoutRequest(name="Cliente Prueba", email="cliente@example.com"),
        )

    result_contact = await db.execute(text("SELECT is_customer FROM contacts WHERE email = :e"), {"e": "cliente@example.com"})
    assert result_contact.scalar_one() is True


@pytest.mark.asyncio
async def test_cart_wrong_token_returns_not_found(db, company, store):
    cart, _real_token = await CartService.create_cart(db, company_id=company.id)
    with pytest.raises(NotFoundError):
        await CartService.get_cart(db, company_id=company.id, cart_id=cart.id, session_token="token-incorrecto")


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(db, company, store):
    body = json.dumps({"event_id": "evt_1", "sales_order_id": 1, "status": "paid"}).encode()
    with pytest.raises(ValidationError):
        await WebhookService.handle_payment_event(
            db, company_id=company.id, gateway="stripe", raw_body=body,
            payload=json.loads(body), signature="firma-invalida",
        )


@pytest.mark.asyncio
async def test_webhook_confirms_order_and_posts_invoice(db, company, store):
    cart, token = await CartService.create_cart(db, company_id=company.id)
    await CartService.add_item(
        db, company_id=company.id, cart_id=cart.id, session_token=token,
        payload=ecommerce_schemas.AddCartItem(product_id=store["product"].id, quantity=Decimal("1")),
    )
    result = await CheckoutService.checkout(
        db, company_id=company.id, cart_id=cart.id, session_token=token,
        payload=ecommerce_schemas.CheckoutRequest(name="Cliente Prueba", email="cliente2@example.com"),
    )

    settings = await EcommerceSettingsService.get_or_raise(db, company_id=company.id)
    body = json.dumps({"event_id": "evt_ok_1", "sales_order_id": result.sales_order_id, "status": "paid"}).encode()
    signature = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()

    response = await WebhookService.handle_payment_event(
        db, company_id=company.id, gateway="stripe", raw_body=body, payload=json.loads(body), signature=signature
    )
    assert response["status"] == "processed"

    order_status = await db.execute(text("SELECT status FROM sales_orders WHERE id = :id"), {"id": result.sales_order_id})
    assert order_status.scalar_one() == "confirmed"

    invoice_row = await db.execute(
        text("SELECT status FROM invoices WHERE source_document_type = 'sales_order' AND source_document_id = :id"),
        {"id": result.sales_order_id},
    )
    assert invoice_row.scalar_one() == "posted"

    # Reintento del mismo event_id — idempotente, no vuelve a procesar.
    replay = await WebhookService.handle_payment_event(
        db, company_id=company.id, gateway="stripe", raw_body=body, payload=json.loads(body), signature=signature
    )
    assert replay["status"] == "already_processed"


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_cart_read(db):
    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    company_a = core_models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = core_models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    cart = ecommerce_models.Cart(company_id=company_a.id, session_token="tok-a")
    db.add(cart)
    await db.commit()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    result = await db.execute(text("SELECT count(*) FROM ecommerce_carts WHERE id = :id"), {"id": cart.id})
    assert result.scalar_one() == 0, "RLS falló: la compañía B pudo leer un carrito de la compañía A"
