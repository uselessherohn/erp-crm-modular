"""
tests/property/test_sales_order_state_machine.py — fuzzing de secuencias de
transiciones de estado de SalesOrder, contra Postgres real.

A diferencia de test_accounting_compute_lines_properties.py (que fuzzea
VALORES de entrada a una función pura), esto fuzzea SECUENCIAS DE ACCIONES
contra un objeto con estado real en la base — Hypothesis genera listas
aleatorias de {confirm, start_preparation, ship parcial, ship total,
invoice, cancel} y las ejecuta una por una contra el MISMO SalesOrder real.

La propiedad que se verifica en cada paso, no solo al final: para
CUALQUIER secuencia (incluyendo secuencias inválidas — confirmar dos veces,
facturar antes de enviar, cancelar algo ya facturado):
1. Una transición válida (según el estado ESPERADO que este test lleva por
   su cuenta) siempre tiene éxito y deja el status real de la orden
   exactamente en el estado esperado.
2. Una transición inválida SIEMPRE se rechaza con ConflictError — nunca
   tiene éxito silenciosamente, nunca crashea con un error distinto.
3. Invariante de cantidades: `quantity_shipped` de cada línea nunca supera
   `quantity` (la cantidad ordenada) — sin importar cuántos `ship`
   parciales se hayan intentado.

Esto es fuzzing real de la máquina de estados — no confía en que los tests
manuales (test_sales_module.py) hayan pensado en todas las secuencias
"raras" (cancelar-luego-confirmar, enviar-luego-cancelar, etc.); Hypothesis
las genera y las prueba todas.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app import models_registry  # noqa: F401 — registra todos los modelos antes de tocar cualquier FK
from app.contacts import schemas as contacts_schemas
from app.contacts.services import ContactService
from app.database import AsyncSessionLocal
from app.inventory import schemas as inv_schemas
from app.inventory.services import ProductService, StockService, WarehouseService
from app.sales import schemas as sales_schemas
from app.sales.services import SalesOrderService
from app.shared.exceptions import ConflictError


class Action(StrEnum):
    confirm = "confirm"
    start_preparation = "start_preparation"
    ship_partial = "ship_partial"
    ship_full = "ship_full"
    invoice = "invoice"
    cancel = "cancel"


ORDERED_QUANTITY = Decimal(10)

# Qué estados (según el modelo mental de ESTE test, no el de la app —
# eso es justamente lo que se verifica) permiten cada acción.
VALID_FROM_STATE: dict[Action, set[str]] = {
    Action.confirm: {"draft"},
    Action.start_preparation: {"confirmed"},
    Action.ship_partial: {"confirmed", "en_preparacion"},
    Action.ship_full: {"confirmed", "en_preparacion"},
    Action.invoice: {"enviado"},
    Action.cancel: {"draft", "confirmed", "en_preparacion"},
}


@pytest_asyncio.fixture
async def company_id() -> int:
    from app.core import models as core_models

    async with AsyncSessionLocal() as db:
        from app.core.models import Company

        company = Company(name=f"Fuzz SalesOrder {uuid.uuid4().hex[:8]}")
        db.add(company)
        await db.flush()
        cid = company.id
        await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(cid)})
        db.add(core_models.CompanyPackage(company_id=cid, package="administrative", status="active"))
        await db.commit()
    return cid


async def _make_fresh_order(company_id: int) -> int:
    """Una SalesOrder nueva en 'draft', con una línea de ORDERED_QUANTITY
    unidades y stock físico de sobra — para que ningún `ship` falle por
    falta de stock (eso ya lo cubre 11_concurrency_load.py; acá el foco
    es la máquina de estados, no el inventario)."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})
        warehouse = await WarehouseService.create(
            db, company_id=company_id, payload=inv_schemas.WarehouseCreate(name=f"Bodega Fuzz {uuid.uuid4().hex[:8]}")
        )
        product = await ProductService.create(
            db, company_id=company_id, created_by=None,
            payload=inv_schemas.ProductCreate(
                sku=f"SKU-FUZZ-{uuid.uuid4().hex[:8]}", name="Producto Fuzz",
                product_type=inv_schemas.ProductTypeEnum.facturable,
            ),
        )
        customer = await ContactService.create_contact(
            db, company_id=company_id, created_by=None,
            payload=contacts_schemas.ContactCreate(name="Cliente Fuzz", is_customer=True),
        )
        await StockService.record_movement(
            db, company_id=company_id, created_by=None,
            payload=inv_schemas.StockMovementCreate(
                product_id=product.id, warehouse_id=warehouse.id, movement_type=inv_schemas.MovementTypeEnum.entrada,
                quantity=ORDERED_QUANTITY * 10, reference="Stock de sobra — fuzz de máquina de estados",
            ),
        )
        order = await SalesOrderService.create_draft(
            db, company_id=company_id, created_by=None,
            payload=sales_schemas.SalesOrderCreate(
                customer_id=customer.id, warehouse_id=warehouse.id,
                lines=[sales_schemas.SalesOrderLineCreate(product_id=product.id, quantity=ORDERED_QUANTITY, unit_price=100)],
            ),
        )
        await db.commit()
        return order.id


async def _apply_action(company_id: int, order_id: int, action: Action) -> tuple[bool, str | None]:
    """Ejecuta la acción contra la DB real. Devuelve (tuvo_éxito, nuevo_status_real)."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})
        try:
            if action is Action.confirm:
                order = await SalesOrderService.confirm(db, company_id=company_id, order_id=order_id, actor_id=None)
            elif action is Action.start_preparation:
                order = await SalesOrderService.start_preparation(db, company_id=company_id, order_id=order_id, actor_id=None)
            elif action is Action.ship_partial:
                order = await SalesOrderService.ship(
                    db, company_id=company_id, order_id=order_id, actor_id=None,
                    payload=await _ship_payload(db, company_id, order_id, quantity=Decimal(1)),
                )
            elif action is Action.ship_full:
                order = await SalesOrderService.ship(
                    db, company_id=company_id, order_id=order_id, actor_id=None,
                    payload=await _ship_payload(db, company_id, order_id, quantity=None),
                )
            elif action is Action.invoice:
                order = await SalesOrderService.invoice(db, company_id=company_id, order_id=order_id, actor_id=None)
            elif action is Action.cancel:
                order = await SalesOrderService.cancel(db, company_id=company_id, order_id=order_id, actor_id=None)
            else:  # pragma: no cover
                raise AssertionError(f"acción no manejada: {action}")
            return True, order.status
        except ConflictError:
            await db.rollback()
            real_status = await _read_real_status(db, company_id, order_id)
            return False, real_status


async def _ship_payload(db, company_id: int, order_id: int, *, quantity: Decimal | None) -> sales_schemas.ShipSalesOrder:
    order = await SalesOrderService.get(db, company_id=company_id, order_id=order_id)
    lines = []
    for line in order.lines:
        pending = line.quantity - line.quantity_shipped
        if pending <= 0:
            continue
        qty = pending if quantity is None else min(quantity, pending)
        lines.append(sales_schemas.ShipLineItem(line_id=line.id, quantity=qty))
    if not lines:
        # Nada pendiente (ej. la orden ya está 'enviado' del todo, o
        # 'cancelado'/'facturado' y por eso ni tiene sentido enviar más).
        # ShipSalesOrder exige al menos una línea (min_length=1) — se arma
        # un intento de todos modos sobre la primera línea, esperando que
        # el chequeo de ESTADO del servicio (no el de cantidad pendiente)
        # sea lo que lo rechace primero, ya que en este punto la acción ya
        # se predijo como inválida por VALID_FROM_STATE.
        first_line = order.lines[0]
        lines.append(sales_schemas.ShipLineItem(line_id=first_line.id, quantity=Decimal(1)))
    return sales_schemas.ShipSalesOrder(lines=lines)


async def _read_real_status(db, company_id: int, order_id: int) -> str:
    order = await SalesOrderService.get(db, company_id=company_id, order_id=order_id)
    return order.status


def _expected_next_state(current: str, action: Action, *, fully_shipped_after: bool) -> str | None:
    """None significa "esta acción debería ser rechazada desde este estado"."""
    if current not in VALID_FROM_STATE[action]:
        return None
    if action is Action.confirm:
        return "confirmed"
    if action is Action.start_preparation:
        return "en_preparacion"
    if action in (Action.ship_partial, Action.ship_full):
        return "enviado" if fully_shipped_after else "en_preparacion"
    if action is Action.invoice:
        return "facturado"
    if action is Action.cancel:
        return "cancelado"
    raise AssertionError(action)  # pragma: no cover


@pytest.mark.asyncio
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
@given(actions=st.lists(st.sampled_from(Action), min_size=1, max_size=8))
async def test_random_action_sequences_never_violate_invariants(company_id: int, actions: list[Action]):
    order_id = await _make_fresh_order(company_id)
    expected_state = "draft"
    shipped_so_far = Decimal(0)

    for action in actions:
        would_fully_ship = action in (Action.ship_partial, Action.ship_full) and (
            (shipped_so_far + (Decimal(1) if action is Action.ship_partial else (ORDERED_QUANTITY - shipped_so_far))) >= ORDERED_QUANTITY
        )
        expected_after = _expected_next_state(expected_state, action, fully_shipped_after=would_fully_ship)

        succeeded, real_status_after = await _apply_action(company_id, order_id, action)

        if expected_after is None:
            assert not succeeded, (
                f"Transición inválida NO rechazada: {action} desde '{expected_state}' — la app la aceptó "
                f"(nuevo status real: '{real_status_after}'). Secuencia completa: {actions}"
            )
            # Una transición rechazada nunca debería cambiar el estado real.
            assert real_status_after == expected_state, (
                f"{action} fue rechazada (ConflictError, correcto) pero el status real cambió de "
                f"'{expected_state}' a '{real_status_after}' de todos modos — un ConflictError NUNCA "
                f"debería dejar efectos parciales. Secuencia: {actions}"
            )
        else:
            assert succeeded, (
                f"Transición válida RECHAZADA: {action} desde '{expected_state}' se esperaba que llevara a "
                f"'{expected_after}', pero la app la rechazó. Secuencia completa: {actions}"
            )
            assert real_status_after == expected_after, (
                f"{action} desde '{expected_state}' tuvo éxito pero llevó a '{real_status_after}' "
                f"en vez de '{expected_after}'. Secuencia: {actions}"
            )
            expected_state = expected_after
            if action is Action.ship_partial:
                shipped_so_far = min(shipped_so_far + 1, ORDERED_QUANTITY)
            elif action is Action.ship_full:
                shipped_so_far = ORDERED_QUANTITY

    # Invariante final, además de las de cada paso: quantity_shipped nunca
    # superó quantity para ninguna línea, sin importar la secuencia.
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})
        order = await SalesOrderService.get(db, company_id=company_id, order_id=order_id)
        for line in order.lines:
            assert line.quantity_shipped <= line.quantity, (
                f"Línea {line.id}: quantity_shipped ({line.quantity_shipped}) > quantity "
                f"({line.quantity}) tras la secuencia {actions} — oversell real vía la máquina de estados."
            )
