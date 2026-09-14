"""
Tests de integración del módulo pharmacy — contra PostgreSQL real.
Mismo patrón que sales/medical: capa de servicio directa.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app import models_registry  # noqa: F401
from app.contacts import schemas as contacts_schemas
from app.contacts.services import ContactService
from app.core import models as core_models
from app.core import schemas as core_schemas
from app.core.services import UserService
from app.database import AsyncSessionLocal
from app.inventory import schemas as inventory_schemas
from app.inventory.services import ProductService, StockService, WarehouseService
from app.pharmacy import schemas as pharmacy_schemas
from app.pharmacy.services import ControlledSubstanceLogService, ControlledSubstanceService, DispensationService
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
async def warehouse(db, company):
    return await WarehouseService.create(db, company_id=company.id, payload=inventory_schemas.WarehouseCreate(name="Farmacia Central"))


@pytest_asyncio.fixture
async def product(db, company):
    unique = uuid.uuid4().hex[:6]
    return await ProductService.create(
        db, company_id=company.id,
        payload=inventory_schemas.ProductCreate(
            sku=f"MED-{unique}", name="Amoxicilina 500mg", product_type=inventory_schemas.ProductTypeEnum.consumible, tracks_lots=True,
        ),
        created_by=None,
    )


@pytest_asyncio.fixture
async def patient_contact(db, company):
    return await ContactService.create_contact(
        db, company_id=company.id, payload=contacts_schemas.ContactCreate(name="Cliente Farmacia", is_customer=True),
        created_by=None,
    )


@pytest_asyncio.fixture
async def pharmacist(db, company):
    unique = uuid.uuid4().hex[:8]
    return await UserService.create_user(
        db, company_id=company.id,
        payload=core_schemas.UserCreate(email=f"pharm.{unique}@test.hn", full_name="Farmacéutico Test", password="SuperSegura123"),
        created_by=None,
    )


async def _seed_lot(db, company, product, warehouse, *, lot_number: str, expiry_date, quantity: Decimal):
    await StockService.record_movement(
        db, company_id=company.id,
        payload=inventory_schemas.StockMovementCreate(
            product_id=product.id, warehouse_id=warehouse.id, movement_type=inventory_schemas.MovementTypeEnum.entrada,
            quantity=quantity, lot_number=lot_number, expiry_date=expiry_date,
        ),
        created_by=None,
    )


def _dispense_payload(patient_contact, product, quantity: Decimal, **kwargs):
    return pharmacy_schemas.DispensationOrderCreate(
        warehouse_id=kwargs.pop("warehouse_id"), patient_contact_id=patient_contact.id,
        lines=[pharmacy_schemas.DispensationLineRequest(product_id=product.id, quantity=quantity)],
        **kwargs,
    )


@pytest.mark.asyncio
async def test_dispensation_fefo_picks_earliest_expiry_first(db, company, warehouse, product, patient_contact, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-LATE", expiry_date=date.today() + timedelta(days=365), quantity=Decimal(50))
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-EARLY", expiry_date=date.today() + timedelta(days=30), quantity=Decimal(50))

    order = await DispensationService.create(
        db, company_id=company.id, dispensed_by=pharmacist.id,
        payload=_dispense_payload(
            patient_contact, product, Decimal(10), warehouse_id=warehouse.id,
            allergy_check_notes="Sin alergias conocidas",
        ),
    )
    assert len(order.lines) == 1
    consumed_lot_id = order.lines[0].lot_id

    lots = (await db.execute(text("SELECT id, lot_number FROM lots WHERE id = :lid"), {"lid": consumed_lot_id})).one()
    assert lots.lot_number == "LOT-EARLY"


@pytest.mark.asyncio
async def test_dispensation_splits_across_lots_when_one_is_not_enough(db, company, warehouse, product, patient_contact, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-A", expiry_date=date.today() + timedelta(days=10), quantity=Decimal(5))
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-B", expiry_date=date.today() + timedelta(days=60), quantity=Decimal(50))

    order = await DispensationService.create(
        db, company_id=company.id, dispensed_by=pharmacist.id,
        payload=_dispense_payload(
            patient_contact, product, Decimal(8), warehouse_id=warehouse.id,
            allergy_check_notes="Sin alergias conocidas",
        ),
    )
    assert len(order.lines) == 2
    total = sum(l.quantity for l in order.lines)
    assert total == Decimal(8)
    assert order.lines[0].quantity == Decimal(5)  # LOT-A agotado primero (vence antes)
    assert order.lines[1].quantity == Decimal(3)


@pytest.mark.asyncio
async def test_dispensation_insufficient_stock_raises_conflict(db, company, warehouse, product, patient_contact, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-X", expiry_date=date.today() + timedelta(days=10), quantity=Decimal(2))
    with pytest.raises(ConflictError):
        await DispensationService.create(
            db, company_id=company.id, dispensed_by=pharmacist.id,
            payload=_dispense_payload(
                patient_contact, product, Decimal(10), warehouse_id=warehouse.id,
                allergy_check_notes="Sin alergias conocidas",
            ),
        )


@pytest.mark.asyncio
async def test_dispensation_requires_allergy_notes_without_medical_active(db, company, warehouse, product, patient_contact, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-Y", expiry_date=date.today() + timedelta(days=10), quantity=Decimal(10))
    with pytest.raises(ValidationError):
        await DispensationService.create(
            db, company_id=company.id, dispensed_by=pharmacist.id,
            payload=_dispense_payload(patient_contact, product, Decimal(1), warehouse_id=warehouse.id),
        )


@pytest.mark.asyncio
async def test_dispensation_prescription_requires_medical_active(db, company, warehouse, product, patient_contact, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-Z", expiry_date=date.today() + timedelta(days=10), quantity=Decimal(10))
    with pytest.raises(ValidationError):
        await DispensationService.create(
            db, company_id=company.id, dispensed_by=pharmacist.id,
            payload=_dispense_payload(
                patient_contact, product, Decimal(1), warehouse_id=warehouse.id,
                prescription_id=999999,
            ),
        )


@pytest.mark.asyncio
async def test_dispensation_pos_walk_in_sale_with_payment(db, company, warehouse, product, patient_contact, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-POS", expiry_date=date.today() + timedelta(days=10), quantity=Decimal(10))
    order = await DispensationService.create(
        db, company_id=company.id, dispensed_by=pharmacist.id,
        payload=_dispense_payload(
            patient_contact, product, Decimal(2), warehouse_id=warehouse.id,
            allergy_check_notes="Sin alergias conocidas", walk_in_reference="Venta de mostrador sin receta",
            payment_method="efectivo", amount_charged=Decimal("150.00"),
        ),
    )
    assert order.prescription_id is None
    assert order.payment_method == "efectivo"
    assert order.document_number.startswith("DISP-")


@pytest.mark.asyncio
async def test_dispensation_controlled_substance_logs_entry(db, company, warehouse, product, patient_contact, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-CTRL", expiry_date=date.today() + timedelta(days=10), quantity=Decimal(10))
    await ControlledSubstanceService.mark(db, company_id=company.id, product_id=product.id, created_by=pharmacist.id)

    order = await DispensationService.create(
        db, company_id=company.id, dispensed_by=pharmacist.id,
        payload=_dispense_payload(
            patient_contact, product, Decimal(3), warehouse_id=warehouse.id,
            allergy_check_notes="Sin alergias conocidas",
        ),
    )
    log_entries = await ControlledSubstanceLogService.list(db, company_id=company.id)
    matching = [e for e in log_entries if e.dispensation_line_id == order.lines[0].id]
    assert len(matching) == 1
    assert matching[0].quantity == Decimal(3)
    assert matching[0].patient_contact_id == patient_contact.id


@pytest.mark.asyncio
async def test_dispensation_non_controlled_product_does_not_log(db, company, warehouse, product, patient_contact, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-NC", expiry_date=date.today() + timedelta(days=10), quantity=Decimal(10))
    order = await DispensationService.create(
        db, company_id=company.id, dispensed_by=pharmacist.id,
        payload=_dispense_payload(
            patient_contact, product, Decimal(2), warehouse_id=warehouse.id,
            allergy_check_notes="Sin alergias conocidas",
        ),
    )
    log_entries = await ControlledSubstanceLogService.list(db, company_id=company.id)
    assert all(e.dispensation_line_id != order.lines[0].id for e in log_entries)


@pytest.mark.asyncio
async def test_dispensation_void_does_not_restore_stock(db, company, warehouse, product, patient_contact, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-VOID", expiry_date=date.today() + timedelta(days=10), quantity=Decimal(10))
    order = await DispensationService.create(
        db, company_id=company.id, dispensed_by=pharmacist.id,
        payload=_dispense_payload(
            patient_contact, product, Decimal(4), warehouse_id=warehouse.id,
            allergy_check_notes="Sin alergias conocidas",
        ),
    )
    levels_before = await StockService.get_levels(db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
    total_before = sum(l.quantity for l in levels_before)

    voided = await DispensationService.void(
        db, company_id=company.id, order_id=order.id,
        payload=pharmacy_schemas.DispensationVoid(void_reason="Error de registro"), actor_id=pharmacist.id,
    )
    assert voided.status == "voided"

    levels_after = await StockService.get_levels(db, company_id=company.id, product_id=product.id, warehouse_id=warehouse.id)
    total_after = sum(l.quantity for l in levels_after)
    assert total_after == total_before  # NO se restituyó stock (DED-50)

    with pytest.raises(ConflictError):
        await DispensationService.void(
            db, company_id=company.id, order_id=order.id,
            payload=pharmacy_schemas.DispensationVoid(void_reason="Doble anulación"), actor_id=pharmacist.id,
        )


@pytest.mark.asyncio
async def test_dispensation_get_requires_existing_order(db, company):
    with pytest.raises(NotFoundError):
        await DispensationService.get(db, company_id=company.id, order_id=999999)


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_dispensation_read():
    async with AsyncSessionLocal() as db_a, AsyncSessionLocal() as db_b:
        unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
        company_a = core_models.Company(name=f"Co A {unique_a}", tax_id=unique_a)
        company_b = core_models.Company(name=f"Co B {unique_b}", tax_id=unique_b)
        db_a.add(company_a)
        db_b.add(company_b)
        await db_a.flush()
        await db_b.flush()
        await db_a.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
        await db_b.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
        await db_a.commit()
        await db_b.commit()

        warehouse_a = await WarehouseService.create(db_a, company_id=company_a.id, payload=inventory_schemas.WarehouseCreate(name="Bodega A"))
        product_a = await ProductService.create(
            db_a, company_id=company_a.id,
            payload=inventory_schemas.ProductCreate(sku="MEDA-1", name="Producto A", product_type=inventory_schemas.ProductTypeEnum.consumible, tracks_lots=True),
            created_by=None,
        )
        patient_a = await ContactService.create_contact(
            db_a, company_id=company_a.id, payload=contacts_schemas.ContactCreate(name="Cliente A", is_customer=True), created_by=None,
        )
        pharmacist_a = await UserService.create_user(
            db_a, company_id=company_a.id,
            payload=core_schemas.UserCreate(email=f"pharm.a.{unique_a}@test.hn", full_name="Farm A", password="SuperSegura123"),
            created_by=None,
        )
        await _seed_lot(db_a, company_a, product_a, warehouse_a, lot_number="LOT-A", expiry_date=date.today() + timedelta(days=10), quantity=Decimal(10))
        order = await DispensationService.create(
            db_a, company_id=company_a.id, dispensed_by=pharmacist_a.id,
            payload=_dispense_payload(
                patient_a, product_a, Decimal(1), warehouse_id=warehouse_a.id,
                allergy_check_notes="Sin alergias conocidas",
            ),
        )

        with pytest.raises(NotFoundError):
            await DispensationService.get(db_b, company_id=company_b.id, order_id=order.id)

        await db_a.rollback()
        await db_b.rollback()
