"""
Tests de integración del módulo inventory — contra PostgreSQL real.
El test de concurrencia (test_concurrent_stock_deductions_never_go_negative)
es el más importante del módulo: usa sesiones/conexiones REALES separadas
en paralelo (asyncio.gather), no una sola sesión secuencial simulando
concurrencia — si no fuera así, el SELECT FOR UPDATE nunca se ejercitaría
de verdad.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core import models as core_models
from app.inventory import models, schemas
from app.inventory.services import CategoryService, ProductService, StockService, WarehouseService
from app.database import AsyncSessionLocal
from app.shared.exceptions import ConflictError, ValidationError


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
async def warehouse_a(db, company):
    w = await WarehouseService.create(db, company_id=company.id, payload=schemas.WarehouseCreate(name="Bodega A"))
    return w


@pytest_asyncio.fixture
async def warehouse_b(db, company):
    w = await WarehouseService.create(db, company_id=company.id, payload=schemas.WarehouseCreate(name="Bodega B"))
    return w


@pytest_asyncio.fixture
async def product(db, company):
    p = await ProductService.create(
        db,
        company_id=company.id,
        payload=schemas.ProductCreate(sku="TORN-001", name="Tornillo 1/4", product_type=schemas.ProductTypeEnum.facturable),
        created_by=None,
    )
    return p


@pytest_asyncio.fixture
async def product_with_lots(db, company):
    p = await ProductService.create(
        db,
        company_id=company.id,
        payload=schemas.ProductCreate(
            sku="MED-001", name="Amoxicilina 500mg", product_type=schemas.ProductTypeEnum.consumible, tracks_lots=True
        ),
        created_by=None,
    )
    return p


@pytest.mark.asyncio
async def test_entrada_increases_stock(db, company, warehouse_a, product):
    movement = await StockService.record_movement(
        db,
        company_id=company.id,
        payload=schemas.StockMovementCreate(
            product_id=product.id, warehouse_id=warehouse_a.id, movement_type=schemas.MovementTypeEnum.entrada, quantity=Decimal(100)
        ),
        created_by=None,
    )
    assert movement.quantity == Decimal(100)

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product.id)
    assert levels[0].quantity == Decimal(100)


@pytest.mark.asyncio
async def test_salida_exceeding_stock_raises_conflict(db, company, warehouse_a, product):
    await StockService.record_movement(
        db,
        company_id=company.id,
        payload=schemas.StockMovementCreate(
            product_id=product.id, warehouse_id=warehouse_a.id, movement_type=schemas.MovementTypeEnum.entrada, quantity=Decimal(10)
        ),
        created_by=None,
    )

    with pytest.raises(ConflictError, match="Stock insuficiente"):
        await StockService.record_movement(
            db,
            company_id=company.id,
            payload=schemas.StockMovementCreate(
                product_id=product.id, warehouse_id=warehouse_a.id, movement_type=schemas.MovementTypeEnum.salida, quantity=Decimal(50)
            ),
            created_by=None,
        )


@pytest.mark.asyncio
async def test_product_tracking_lots_requires_lot_number(db, company, warehouse_a, product_with_lots):
    with pytest.raises(ValidationError, match="requiere lot_number"):
        await StockService.record_movement(
            db,
            company_id=company.id,
            payload=schemas.StockMovementCreate(
                product_id=product_with_lots.id, warehouse_id=warehouse_a.id,
                movement_type=schemas.MovementTypeEnum.entrada, quantity=Decimal(50),
            ),
            created_by=None,
        )


@pytest.mark.asyncio
async def test_product_without_lots_rejects_lot_number(db, company, warehouse_a, product):
    with pytest.raises(ValidationError, match="no maneja lotes"):
        await StockService.record_movement(
            db,
            company_id=company.id,
            payload=schemas.StockMovementCreate(
                product_id=product.id, warehouse_id=warehouse_a.id,
                movement_type=schemas.MovementTypeEnum.entrada, quantity=Decimal(50), lot_number="L-001",
            ),
            created_by=None,
        )


@pytest.mark.asyncio
async def test_lot_tracking_creates_lot_and_separate_stock_level(db, company, warehouse_a, product_with_lots):
    await StockService.record_movement(
        db,
        company_id=company.id,
        payload=schemas.StockMovementCreate(
            product_id=product_with_lots.id, warehouse_id=warehouse_a.id,
            movement_type=schemas.MovementTypeEnum.entrada, quantity=Decimal(30), lot_number="LOT-A",
        ),
        created_by=None,
    )
    await StockService.record_movement(
        db,
        company_id=company.id,
        payload=schemas.StockMovementCreate(
            product_id=product_with_lots.id, warehouse_id=warehouse_a.id,
            movement_type=schemas.MovementTypeEnum.entrada, quantity=Decimal(20), lot_number="LOT-B",
        ),
        created_by=None,
    )

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product_with_lots.id)
    assert len(levels) == 2  # dos lotes = dos filas de saldo, no una sumada
    total = sum(lvl.quantity for lvl in levels)
    assert total == Decimal(50)


@pytest.mark.asyncio
async def test_transfer_moves_stock_between_warehouses(db, company, warehouse_a, warehouse_b, product):
    await StockService.record_movement(
        db,
        company_id=company.id,
        payload=schemas.StockMovementCreate(
            product_id=product.id, warehouse_id=warehouse_a.id, movement_type=schemas.MovementTypeEnum.entrada, quantity=Decimal(100)
        ),
        created_by=None,
    )

    movements = await StockService.transfer(
        db,
        company_id=company.id,
        payload=schemas.TransferCreate(
            product_id=product.id, source_warehouse_id=warehouse_a.id, destination_warehouse_id=warehouse_b.id, quantity=Decimal(40)
        ),
        created_by=None,
    )
    assert len(movements) == 2
    assert movements[0].correlation_id == movements[1].correlation_id  # mismo correlation_id, spec 8.1

    levels = await StockService.get_levels(db, company_id=company.id, product_id=product.id)
    by_warehouse = {lvl.warehouse_id: lvl.quantity for lvl in levels}
    assert by_warehouse[warehouse_a.id] == Decimal(60)
    assert by_warehouse[warehouse_b.id] == Decimal(40)


@pytest.mark.asyncio
async def test_transfer_insufficient_stock_rolls_back_completely(db, company, warehouse_a, warehouse_b, product):
    """Si la salida del origen falla, el destino NUNCA debe recibir nada —
    ambos movimientos son atómicos, no dos operaciones independientes."""
    # Se capturan los IDs ANTES del rollback: después de rollback() SQLAlchemy
    # expira todos los objetos de la sesión, y acceder a un atributo expirado
    # de forma síncrona bajo el driver async revienta con MissingGreenlet
    # (bug real de este test, encontrado al ejecutarlo, no del producto).
    company_id, product_id = company.id, product.id

    with pytest.raises(ConflictError):
        await StockService.transfer(
            db,
            company_id=company_id,
            payload=schemas.TransferCreate(
                product_id=product_id, source_warehouse_id=warehouse_a.id,
                destination_warehouse_id=warehouse_b.id, quantity=Decimal(999),
            ),
            created_by=None,
        )
    await db.rollback()
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})

    levels = await StockService.get_levels(db, company_id=company_id, product_id=product_id)
    assert all(lvl.quantity == 0 for lvl in levels) or len(levels) == 0


@pytest.mark.asyncio
async def test_concurrent_stock_deductions_never_go_negative(company, warehouse_a, product):
    """EL TEST MÁS IMPORTANTE DEL MÓDULO. 10 salidas concurrentes de 15
    unidades cada una contra un stock inicial de 100 (suficiente para 6,
    no para 10) — sesiones/conexiones de base de datos REALES y separadas
    en paralelo (no una sola sesión secuencial disfrazada de concurrencia).
    Si el patrón SELECT FOR UPDATE de StockService._apply_delta no
    funcionara, el saldo final terminaría negativo (lost update clásico)."""
    async with AsyncSessionLocal() as setup_db:
        await setup_db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company.id)})
        await StockService.record_movement(
            setup_db,
            company_id=company.id,
            payload=schemas.StockMovementCreate(
                product_id=product.id, warehouse_id=warehouse_a.id, movement_type=schemas.MovementTypeEnum.entrada, quantity=Decimal(100)
            ),
            created_by=None,
        )

    async def attempt_salida():
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company.id)})
            try:
                await StockService.record_movement(
                    session,
                    company_id=company.id,
                    payload=schemas.StockMovementCreate(
                        product_id=product.id, warehouse_id=warehouse_a.id,
                        movement_type=schemas.MovementTypeEnum.salida, quantity=Decimal(15),
                    ),
                    created_by=None,
                )
                return "ok"
            except ConflictError:
                await session.rollback()
                return "insufficient"

    results = await asyncio.gather(*[attempt_salida() for _ in range(10)])

    successes = results.count("ok")
    failures = results.count("insufficient")
    assert successes + failures == 10
    # Con 100 de stock y salidas de 15, caben exactamente 6 (90), la 7ma
    # fallaría (dejaría -5) — el número exacto de éxitos puede variar según
    # el orden de llegada del lock, pero NUNCA más de 6.
    assert successes <= 6, f"Se permitieron {successes} salidas — el stock debió quedar negativo, bug de concurrencia real"

    async with AsyncSessionLocal() as check_db:
        await check_db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company.id)})
        levels = await StockService.get_levels(check_db, company_id=company.id, product_id=product.id, warehouse_id=warehouse_a.id)
        final_quantity = levels[0].quantity
        assert final_quantity >= 0, f"Stock terminó negativo ({final_quantity}) — bug de concurrencia real"
        assert final_quantity == Decimal(100) - Decimal(15) * successes
