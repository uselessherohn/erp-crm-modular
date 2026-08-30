"""
Tests de integración del módulo sales — contra PostgreSQL real.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.contacts import schemas as contacts_schemas
from app.contacts.services import ContactService
from app.core import models as core_models
from app.inventory import schemas as inventory_schemas
from app.inventory.services import ProductService, StockService, WarehouseService
from app.sales import schemas
from app.sales.services import PriceListService, QuoteService, SalesOrderService
from app.database import AsyncSessionLocal
from app.shared.exceptions import ConflictError, NotFoundError


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
async def customer(db, company):
    return await ContactService.create_contact(
        db, company_id=company.id, payload=contacts_schemas.ContactCreate(name="Cliente Test", is_customer=True), created_by=None
    )


@pytest_asyncio.fixture
async def warehouse(db, company):
    return await WarehouseService.create(db, company_id=company.id, payload=inventory_schemas.WarehouseCreate(name="Bodega Test"))


@pytest_asyncio.fixture
async def product(db, company):
    return await ProductService.create(
        db, company_id=company.id,
        payload=inventory_schemas.ProductCreate(sku="S-001", name="Producto Venta", product_type=inventory_schemas.ProductTypeEnum.facturable),
        created_by=None,
    )


async def _stock_in(db, company_id, product_id, warehouse_id, quantity):
    await StockService.record_movement(
        db, company_id=company_id,
        payload=inventory_schemas.StockMovementCreate(
            product_id=product_id, warehouse_id=warehouse_id, movement_type=inventory_schemas.MovementTypeEnum.entrada, quantity=quantity
        ),
        created_by=None,
    )


@pytest.mark.asyncio
async def test_price_list_volume_pricing(db, company, product):
    pl = await PriceListService.create(
        db, company_id=company.id,
        payload=schemas.PriceListCreate(
            name="Lista General",
            items=[
                schemas.PriceListItemCreate(product_id=product.id, unit_price=Decimal("10.00"), min_quantity=Decimal(1)),
                schemas.PriceListItemCreate(product_id=product.id, unit_price=Decimal("8.50"), min_quantity=Decimal(50)),
            ],
        ),
    )
    price_low = await PriceListService.get_price(db, company_id=company.id, price_list_id=pl.id, product_id=product.id, quantity=Decimal(10))
    price_high = await PriceListService.get_price(db, company_id=company.id, price_list_id=pl.id, product_id=product.id, quantity=Decimal(100))
    assert price_low == Decimal("10.00")
    assert price_high == Decimal("8.50")


@pytest.mark.asyncio
async def test_confirm_reserves_stock_not_physical(db, company, customer, warehouse, product):
    await _stock_in(db, company.id, product.id, warehouse.id, Decimal(100))

    order = await SalesOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.SalesOrderCreate(
            customer_id=customer.id, warehouse_id=warehouse.id,
            lines=[schemas.SalesOrderLineCreate(product_id=product.id, quantity=Decimal(30), unit_price=Decimal(10))],
        ),
        created_by=None,
    )
    order = await SalesOrderService.confirm(db, company_id=company.id, order_id=order.id, actor_id=None)
    assert order.status == "confirmed"

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
    assert levels[0].quantity == Decimal(100)
    assert levels[0].reserved_quantity == Decimal(30)


@pytest.mark.asyncio
async def test_confirm_insufficient_available_rejected(db, company, customer, warehouse, product):
    await _stock_in(db, company.id, product.id, warehouse.id, Decimal(10))

    order = await SalesOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.SalesOrderCreate(
            customer_id=customer.id, warehouse_id=warehouse.id,
            lines=[schemas.SalesOrderLineCreate(product_id=product.id, quantity=Decimal(50), unit_price=Decimal(10))],
        ),
        created_by=None,
    )
    with pytest.raises(ConflictError, match="disponible"):
        await SalesOrderService.confirm(db, company_id=company.id, order_id=order.id, actor_id=None)


@pytest.mark.asyncio
async def test_ship_deducts_physical_and_releases_reservation(db, company, customer, warehouse, product):
    await _stock_in(db, company.id, product.id, warehouse.id, Decimal(100))
    order = await SalesOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.SalesOrderCreate(
            customer_id=customer.id, warehouse_id=warehouse.id,
            lines=[schemas.SalesOrderLineCreate(product_id=product.id, quantity=Decimal(40), unit_price=Decimal(10))],
        ),
        created_by=None,
    )
    order = await SalesOrderService.confirm(db, company_id=company.id, order_id=order.id, actor_id=None)
    line_id = order.lines[0].id

    order = await SalesOrderService.ship(
        db, company_id=company.id, order_id=order.id,
        payload=schemas.ShipSalesOrder(lines=[schemas.ShipLineItem(line_id=line_id, quantity=Decimal(40))]),
        actor_id=None,
    )
    assert order.status == "enviado"

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
    assert levels[0].quantity == Decimal(60)
    assert levels[0].reserved_quantity == Decimal(0)


@pytest.mark.asyncio
async def test_partial_ship_keeps_en_preparacion(db, company, customer, warehouse, product):
    await _stock_in(db, company.id, product.id, warehouse.id, Decimal(100))
    order = await SalesOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.SalesOrderCreate(
            customer_id=customer.id, warehouse_id=warehouse.id,
            lines=[schemas.SalesOrderLineCreate(product_id=product.id, quantity=Decimal(40), unit_price=Decimal(10))],
        ),
        created_by=None,
    )
    order = await SalesOrderService.confirm(db, company_id=company.id, order_id=order.id, actor_id=None)
    line_id = order.lines[0].id

    order = await SalesOrderService.ship(
        db, company_id=company.id, order_id=order.id,
        payload=schemas.ShipSalesOrder(lines=[schemas.ShipLineItem(line_id=line_id, quantity=Decimal(15))]),
        actor_id=None,
    )
    assert order.status == "en_preparacion"

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
    assert levels[0].quantity == Decimal(85)
    assert levels[0].reserved_quantity == Decimal(25)


@pytest.mark.asyncio
async def test_cancel_confirmed_releases_reservation(db, company, customer, warehouse, product):
    await _stock_in(db, company.id, product.id, warehouse.id, Decimal(100))
    order = await SalesOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.SalesOrderCreate(
            customer_id=customer.id, warehouse_id=warehouse.id,
            lines=[schemas.SalesOrderLineCreate(product_id=product.id, quantity=Decimal(40), unit_price=Decimal(10))],
        ),
        created_by=None,
    )
    order = await SalesOrderService.confirm(db, company_id=company.id, order_id=order.id, actor_id=None)
    order = await SalesOrderService.cancel(db, company_id=company.id, order_id=order.id, actor_id=None)
    assert order.status == "cancelado"

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
    assert levels[0].quantity == Decimal(100)
    assert levels[0].reserved_quantity == Decimal(0)


@pytest.mark.asyncio
async def test_cannot_cancel_after_shipping(db, company, customer, warehouse, product):
    await _stock_in(db, company.id, product.id, warehouse.id, Decimal(100))
    order = await SalesOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.SalesOrderCreate(
            customer_id=customer.id, warehouse_id=warehouse.id,
            lines=[schemas.SalesOrderLineCreate(product_id=product.id, quantity=Decimal(40), unit_price=Decimal(10))],
        ),
        created_by=None,
    )
    order = await SalesOrderService.confirm(db, company_id=company.id, order_id=order.id, actor_id=None)
    line_id = order.lines[0].id
    order = await SalesOrderService.ship(
        db, company_id=company.id, order_id=order.id,
        payload=schemas.ShipSalesOrder(lines=[schemas.ShipLineItem(line_id=line_id, quantity=Decimal(40))]),
        actor_id=None,
    )
    with pytest.raises(ConflictError, match="envíos"):
        await SalesOrderService.cancel(db, company_id=company.id, order_id=order.id, actor_id=None)


@pytest.mark.asyncio
async def test_quote_expired_cannot_be_accepted(db, company, customer, product):
    quote = await QuoteService.create_draft(
        db, company_id=company.id,
        payload=schemas.QuoteCreate(
            customer_id=customer.id, valid_until=date.today() - timedelta(days=1),
            lines=[schemas.QuoteLineCreate(product_id=product.id, quantity=Decimal(5), unit_price=Decimal(20))],
        ),
        created_by=None,
    )
    quote = await QuoteService.send(db, company_id=company.id, quote_id=quote.id, actor_id=None)
    with pytest.raises(ConflictError, match="venció"):
        await QuoteService.accept(db, company_id=company.id, quote_id=quote.id, actor_id=None)


@pytest.mark.asyncio
async def test_quote_full_lifecycle_convert_to_order(db, company, customer, warehouse, product):
    await _stock_in(db, company.id, product.id, warehouse.id, Decimal(100))
    quote = await QuoteService.create_draft(
        db, company_id=company.id,
        payload=schemas.QuoteCreate(
            customer_id=customer.id, valid_until=date.today() + timedelta(days=30),
            lines=[schemas.QuoteLineCreate(product_id=product.id, quantity=Decimal(20), unit_price=Decimal(15))],
        ),
        created_by=None,
    )
    quote = await QuoteService.send(db, company_id=company.id, quote_id=quote.id, actor_id=None)
    quote = await QuoteService.accept(db, company_id=company.id, quote_id=quote.id, actor_id=None)
    assert quote.status == "accepted"

    order = await QuoteService.convert_to_order(db, company_id=company.id, quote_id=quote.id, warehouse_id=warehouse.id, actor_id=None)
    assert order.status == "draft"
    assert order.lines[0].quantity == Decimal(20)
    assert order.lines[0].unit_price == Decimal(15)

    quote_after = await QuoteService.get(db, company_id=company.id, quote_id=quote.id)
    assert quote_after.status == "converted"
    assert quote_after.converted_to_order_id == order.id


@pytest.mark.asyncio
async def test_concurrent_reservations_never_oversell(company, warehouse, product):
    """10 confirmaciones reales en paralelo (conexiones separadas) contra
    un stock que solo alcanza para 6 reservas de 15, nunca sobrevende."""
    async with AsyncSessionLocal() as setup_db:
        await setup_db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company.id)})
        await _stock_in(setup_db, company.id, product.id, warehouse.id, Decimal(90))

    async def attempt_confirm():
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company.id)})
            cust = await ContactService.create_contact(
                session, company_id=company.id,
                payload=contacts_schemas.ContactCreate(name=f"C{uuid.uuid4().hex[:6]}", is_customer=True), created_by=None,
            )
            order = await SalesOrderService.create_draft(
                session, company_id=company.id,
                payload=schemas.SalesOrderCreate(
                    customer_id=cust.id, warehouse_id=warehouse.id,
                    lines=[schemas.SalesOrderLineCreate(product_id=product.id, quantity=Decimal(15), unit_price=Decimal(10))],
                ),
                created_by=None,
            )
            try:
                await SalesOrderService.confirm(session, company_id=company.id, order_id=order.id, actor_id=None)
                return "ok"
            except ConflictError:
                await session.rollback()
                return "insufficient"

    results = await asyncio.gather(*[attempt_confirm() for _ in range(10)])
    successes = results.count("ok")
    assert successes <= 6, f"Se permitieron {successes} reservas — sobreventa real, bug de concurrencia"

    async with AsyncSessionLocal() as check_db:
        await check_db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company.id)})
        levels = await StockService.get_levels(check_db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
        assert levels[0].reserved_quantity == Decimal(15) * successes
        assert levels[0].reserved_quantity <= levels[0].quantity


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_sales_order_read(db):
    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    company_a = core_models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = core_models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    customer_a = await ContactService.create_contact(
        db, company_id=company_a.id, payload=contacts_schemas.ContactCreate(name="Cust A", is_customer=True), created_by=None
    )
    wh_a = await WarehouseService.create(db, company_id=company_a.id, payload=inventory_schemas.WarehouseCreate(name="WH A"))
    prod_a = await ProductService.create(
        db, company_id=company_a.id,
        payload=inventory_schemas.ProductCreate(sku="A-1", name="Prod A", product_type=inventory_schemas.ProductTypeEnum.facturable),
        created_by=None,
    )
    order_a = await SalesOrderService.create_draft(
        db, company_id=company_a.id,
        payload=schemas.SalesOrderCreate(
            customer_id=customer_a.id, warehouse_id=wh_a.id,
            lines=[schemas.SalesOrderLineCreate(product_id=prod_a.id, quantity=Decimal(1), unit_price=Decimal(1))],
        ),
        created_by=None,
    )

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    with pytest.raises(NotFoundError):
        await SalesOrderService.get(db, company_id=company_b.id, order_id=order_a.id)
