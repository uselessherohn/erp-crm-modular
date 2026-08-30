"""
Tests de integración del módulo purchasing — contra PostgreSQL real.
El test de numeración concurrente sigue el mismo patrón que
test_concurrent_stock_deductions_never_go_negative de inventory: conexiones
reales separadas en paralelo, no una sesión secuencial disfrazada.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.contacts import models as contacts_models
from app.contacts import schemas as contacts_schemas
from app.core import models as core_models
from app.core.services import DocumentNumberingService
from app.inventory import schemas as inventory_schemas
from app.inventory.services import ProductService, StockService, WarehouseService
from app.purchasing import schemas
from app.purchasing.services import PurchaseOrderService
from app.database import AsyncSessionLocal
from app.shared.exceptions import ConflictError, ValidationError, NotFoundError


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
async def vendor(db, company):
    from app.contacts.services import ContactService

    return await ContactService.create_contact(
        db, company_id=company.id, payload=contacts_schemas.ContactCreate(name="Proveedor Test", is_vendor=True), created_by=None
    )


@pytest_asyncio.fixture
async def non_vendor_contact(db, company):
    from app.contacts.services import ContactService

    return await ContactService.create_contact(
        db, company_id=company.id, payload=contacts_schemas.ContactCreate(name="Solo Cliente", is_customer=True), created_by=None
    )


@pytest_asyncio.fixture
async def warehouse(db, company):
    return await WarehouseService.create(db, company_id=company.id, payload=inventory_schemas.WarehouseCreate(name="Bodega Test"))


@pytest_asyncio.fixture
async def product(db, company):
    return await ProductService.create(
        db, company_id=company.id,
        payload=inventory_schemas.ProductCreate(sku="P-001", name="Tornillo", product_type=inventory_schemas.ProductTypeEnum.facturable),
        created_by=None,
    )


@pytest.mark.asyncio
async def test_document_numbering_format(db, company):
    number = await DocumentNumberingService.next_number(db, company_id=company.id, doc_type="test_doc", prefix="TD", year=2026)
    assert number == "TD-2026-000001"
    number2 = await DocumentNumberingService.next_number(db, company_id=company.id, doc_type="test_doc", prefix="TD", year=2026)
    assert number2 == "TD-2026-000002"


@pytest.mark.asyncio
async def test_document_numbering_concurrent_never_duplicates(company):
    """Mismo espíritu que el test de concurrencia de inventory: 15
    llamadas reales en paralelo, conexiones separadas, deben producir 15
    números ÚNICOS y CONSECUTIVOS — nunca MAX()+1 en la app (spec 5)."""

    async def get_number():
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company.id)})
            number = await DocumentNumberingService.next_number(
                session, company_id=company.id, doc_type="concurrent_test", prefix="CT", year=2026
            )
            await session.commit()
            return number

    results = await asyncio.gather(*[get_number() for _ in range(15)])
    assert len(set(results)) == 15, f"Números duplicados bajo concurrencia real: {results}"
    numbers = sorted(int(r.split("-")[-1]) for r in results)
    assert numbers == list(range(1, 16))


@pytest.mark.asyncio
async def test_create_draft_requires_vendor_flag(db, company, warehouse, product, non_vendor_contact):
    with pytest.raises(ValidationError, match="is_vendor"):
        await PurchaseOrderService.create_draft(
            db, company_id=company.id,
            payload=schemas.PurchaseOrderCreate(
                vendor_id=non_vendor_contact.id, warehouse_id=warehouse.id,
                lines=[schemas.PurchaseOrderLineCreate(product_id=product.id, quantity_ordered=Decimal(10), unit_cost=Decimal("5.50"))],
            ),
            created_by=None,
        )


@pytest.mark.asyncio
async def test_full_lifecycle_draft_to_closed(db, company, vendor, warehouse, product):
    po = await PurchaseOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.PurchaseOrderCreate(
            vendor_id=vendor.id, warehouse_id=warehouse.id,
            lines=[schemas.PurchaseOrderLineCreate(product_id=product.id, quantity_ordered=Decimal(100), unit_cost=Decimal("12.75"))],
        ),
        created_by=None,
    )
    assert po.status == "draft"
    assert po.number.startswith("PO-")

    po = await PurchaseOrderService.confirm(db, company_id=company.id, po_id=po.id, actor_id=None)
    assert po.status == "confirmed"

    line_id = po.lines[0].id
    po = await PurchaseOrderService.receive(
        db, company_id=company.id, po_id=po.id,
        payload=schemas.ReceivePurchaseOrder(lines=[schemas.ReceiveLineItem(line_id=line_id, quantity=Decimal(100))]),
        actor_id=None,
    )
    assert po.status == "received"
    assert po.lines[0].quantity_received == Decimal(100)

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
    assert levels[0].quantity == Decimal(100)

    po = await PurchaseOrderService.close(db, company_id=company.id, po_id=po.id, actor_id=None)
    assert po.status == "closed"


@pytest.mark.asyncio
async def test_partial_reception_keeps_status_confirmed(db, company, vendor, warehouse, product):
    po = await PurchaseOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.PurchaseOrderCreate(
            vendor_id=vendor.id, warehouse_id=warehouse.id,
            lines=[schemas.PurchaseOrderLineCreate(product_id=product.id, quantity_ordered=Decimal(100), unit_cost=Decimal("10"))],
        ),
        created_by=None,
    )
    po = await PurchaseOrderService.confirm(db, company_id=company.id, po_id=po.id, actor_id=None)
    line_id = po.lines[0].id

    po = await PurchaseOrderService.receive(
        db, company_id=company.id, po_id=po.id,
        payload=schemas.ReceivePurchaseOrder(lines=[schemas.ReceiveLineItem(line_id=line_id, quantity=Decimal(40))]),
        actor_id=None,
    )
    assert po.status == "confirmed"  # todavía no completo
    assert po.lines[0].quantity_received == Decimal(40)

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
    assert levels[0].quantity == Decimal(40)

    po = await PurchaseOrderService.receive(
        db, company_id=company.id, po_id=po.id,
        payload=schemas.ReceivePurchaseOrder(lines=[schemas.ReceiveLineItem(line_id=line_id, quantity=Decimal(60))]),
        actor_id=None,
    )
    assert po.status == "received"
    assert po.lines[0].quantity_received == Decimal(100)

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
    assert levels[0].quantity == Decimal(100)


@pytest.mark.asyncio
async def test_receive_more_than_ordered_rejected(db, company, vendor, warehouse, product):
    po = await PurchaseOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.PurchaseOrderCreate(
            vendor_id=vendor.id, warehouse_id=warehouse.id,
            lines=[schemas.PurchaseOrderLineCreate(product_id=product.id, quantity_ordered=Decimal(10), unit_cost=Decimal("1"))],
        ),
        created_by=None,
    )
    po = await PurchaseOrderService.confirm(db, company_id=company.id, po_id=po.id, actor_id=None)
    line_id = po.lines[0].id

    with pytest.raises(ValidationError, match="pendientes"):
        await PurchaseOrderService.receive(
            db, company_id=company.id, po_id=po.id,
            payload=schemas.ReceivePurchaseOrder(lines=[schemas.ReceiveLineItem(line_id=line_id, quantity=Decimal(999))]),
            actor_id=None,
        )


@pytest.mark.asyncio
async def test_cannot_confirm_twice(db, company, vendor, warehouse, product):
    po = await PurchaseOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.PurchaseOrderCreate(
            vendor_id=vendor.id, warehouse_id=warehouse.id,
            lines=[schemas.PurchaseOrderLineCreate(product_id=product.id, quantity_ordered=Decimal(10), unit_cost=Decimal("1"))],
        ),
        created_by=None,
    )
    await PurchaseOrderService.confirm(db, company_id=company.id, po_id=po.id, actor_id=None)
    with pytest.raises(ConflictError, match="draft"):
        await PurchaseOrderService.confirm(db, company_id=company.id, po_id=po.id, actor_id=None)


@pytest.mark.asyncio
async def test_cannot_cancel_after_receiving(db, company, vendor, warehouse, product):
    po = await PurchaseOrderService.create_draft(
        db, company_id=company.id,
        payload=schemas.PurchaseOrderCreate(
            vendor_id=vendor.id, warehouse_id=warehouse.id,
            lines=[schemas.PurchaseOrderLineCreate(product_id=product.id, quantity_ordered=Decimal(10), unit_cost=Decimal("1"))],
        ),
        created_by=None,
    )
    po = await PurchaseOrderService.confirm(db, company_id=company.id, po_id=po.id, actor_id=None)
    line_id = po.lines[0].id
    await PurchaseOrderService.receive(
        db, company_id=company.id, po_id=po.id,
        payload=schemas.ReceivePurchaseOrder(lines=[schemas.ReceiveLineItem(line_id=line_id, quantity=Decimal(10))]),
        actor_id=None,
    )
    with pytest.raises(ConflictError, match="recepciones"):
        await PurchaseOrderService.cancel(db, company_id=company.id, po_id=po.id, actor_id=None)


@pytest.mark.asyncio
async def test_duplicate_product_in_lines_rejected():
    with pytest.raises(Exception, match="repetir"):
        schemas.PurchaseOrderCreate(
            vendor_id=1, warehouse_id=1,
            lines=[
                schemas.PurchaseOrderLineCreate(product_id=1, quantity_ordered=Decimal(10), unit_cost=Decimal(1)),
                schemas.PurchaseOrderLineCreate(product_id=1, quantity_ordered=Decimal(5), unit_cost=Decimal(1)),
            ],
        )


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_purchase_order_read(db):
    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    company_a = core_models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = core_models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    from app.contacts.services import ContactService

    vendor_a = await ContactService.create_contact(
        db, company_id=company_a.id, payload=contacts_schemas.ContactCreate(name="Vendor A", is_vendor=True), created_by=None
    )
    wh_a = await WarehouseService.create(db, company_id=company_a.id, payload=inventory_schemas.WarehouseCreate(name="WH A"))
    prod_a = await ProductService.create(
        db, company_id=company_a.id,
        payload=inventory_schemas.ProductCreate(sku="A-1", name="Prod A", product_type=inventory_schemas.ProductTypeEnum.facturable),
        created_by=None,
    )
    po_a = await PurchaseOrderService.create_draft(
        db, company_id=company_a.id,
        payload=schemas.PurchaseOrderCreate(
            vendor_id=vendor_a.id, warehouse_id=wh_a.id,
            lines=[schemas.PurchaseOrderLineCreate(product_id=prod_a.id, quantity_ordered=Decimal(1), unit_cost=Decimal(1))],
        ),
        created_by=None,
    )

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    with pytest.raises(NotFoundError):
        await PurchaseOrderService.get(db, company_id=company_b.id, po_id=po_a.id)
