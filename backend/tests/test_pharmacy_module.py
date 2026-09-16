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
from app.pharmacy.services import (
    ControlledSubstanceLogService,
    ControlledSubstanceService,
    DispensationService,
    DrugInteractionService,
    InsuranceClaimService,
    InsuranceProviderService,
    MtmSessionService,
    PatientInsurancePolicyService,
    ProductActiveIngredientService,
    ReorderPointService,
    ReorderSuggestionService,
)
from app.shared.exceptions import ConflictError, NotFoundError, PackageNotLicensedError, ValidationError
from app.accounting import models as accounting_models
from app.accounting.services import InvoiceService


async def _setup_sales_invoice_account_mappings(db, company):
    """Mismo patrón que tests/test_medical_module.py, tests/test_reports_module.py
    y tests/test_ecommerce_module.py — no existe seed automático de plan de
    cuentas (spec DED-10), se crea explícitamente antes de contabilizar.
    Incluye también el mapeo de `payment_received` (cash_bank/receivable)
    porque los tests de este módulo ejercen el pago, no solo la factura."""
    accounts = {}
    for role, name in [("receivable", "Cuentas por Cobrar"), ("income", "Ingresos"), ("tax", "Impuestos por Pagar"), ("cash_bank", "Banco")]:
        account = accounting_models.Account(
            company_id=company.id, code=f"TEST-{role}", name=name, account_type=role,
        )
        db.add(account)
        await db.flush()
        accounts[role] = account
        db.add(accounting_models.DocumentAccountMapping(
            company_id=company.id, document_type="sales_invoice", role=role, account_id=account.id,
        ))
    for role in ("cash_bank", "receivable"):
        db.add(accounting_models.DocumentAccountMapping(
            company_id=company.id, document_type="payment_received", role=role, account_id=accounts[role].id,
        ))
    await db.commit()
    return accounts


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


@pytest_asyncio.fixture
async def vendor(db, company):
    unique = uuid.uuid4().hex[:6]
    return await ContactService.create_contact(
        db, company_id=company.id,
        payload=contacts_schemas.ContactCreate(name=f"Droguería Test {unique}", is_vendor=True),
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


# ---------------------------------------------------------------------------
# Módulo 21 — MTM / Consulta Farmacéutica
# ---------------------------------------------------------------------------
async def _activate_packages(db, company, *packages, status=None):
    """Mismo helper que `tests/test_medical_module.py::_activate_packages`."""
    status = status or core_models.PackageStatusEnum.active
    for pkg in packages:
        db.add(core_models.CompanyPackage(company_id=company.id, package=pkg, status=status))
    await db.commit()


def _mtm_payload(patient_contact, *, fee_amount=Decimal("300.00")):
    return pharmacy_schemas.MtmSessionCreate(
        patient_contact_id=patient_contact.id, session_date=date.today(),
        medication_review="Paciente en tratamiento con 4 medicamentos crónicos, sin duplicidades detectadas.",
        adherence_notes="Refiere olvidar la dosis nocturna con frecuencia.",
        adverse_effects_notes=None, recommendations="Usar pastillero semanal.",
        fee_amount=fee_amount,
    )


@pytest.mark.asyncio
async def test_mtm_session_create_starts_open(db, company, patient_contact, pharmacist):
    session = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact), pharmacist_user_id=pharmacist.id
    )
    assert session.status == "open"
    assert session.closed_at is None
    assert session.fee_amount == Decimal("300.00")


@pytest.mark.asyncio
async def test_mtm_session_create_rejects_unknown_patient(db, company, pharmacist):
    payload = pharmacy_schemas.MtmSessionCreate(
        patient_contact_id=999999, session_date=date.today(),
        medication_review="Revisión de rutina.", fee_amount=Decimal("100.00"),
    )
    with pytest.raises(NotFoundError):
        await MtmSessionService.create(db, company_id=company.id, payload=payload, pharmacist_user_id=pharmacist.id)


@pytest.mark.asyncio
async def test_mtm_session_cancel_before_close(db, company, patient_contact, pharmacist):
    session = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact), pharmacist_user_id=pharmacist.id
    )
    cancelled = await MtmSessionService.cancel(
        db, company_id=company.id, session_id=session.id,
        payload=pharmacy_schemas.MtmSessionCancel(cancel_reason="Paciente no se presentó"), actor_id=pharmacist.id,
    )
    assert cancelled.status == "cancelled"
    assert cancelled.cancel_reason == "Paciente no se presentó"


@pytest.mark.asyncio
async def test_mtm_session_cancel_twice_conflicts(db, company, patient_contact, pharmacist):
    session = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact), pharmacist_user_id=pharmacist.id
    )
    await MtmSessionService.cancel(
        db, company_id=company.id, session_id=session.id,
        payload=pharmacy_schemas.MtmSessionCancel(cancel_reason="No asistió"), actor_id=pharmacist.id,
    )
    with pytest.raises(ConflictError):
        await MtmSessionService.cancel(
            db, company_id=company.id, session_id=session.id,
            payload=pharmacy_schemas.MtmSessionCancel(cancel_reason="Otra vez"), actor_id=pharmacist.id,
        )


@pytest.mark.asyncio
async def test_mtm_session_close_without_administrative_issues_simple_receipt(db, company, patient_contact, pharmacist):
    session = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact), pharmacist_user_id=pharmacist.id
    )
    billing = await MtmSessionService.close(
        db, company_id=company.id, session_id=session.id,
        payload=pharmacy_schemas.MtmSessionClose(issue_date=date.today()), actor_id=pharmacist.id,
    )
    assert billing.billing_mode == "simple_receipt"
    assert billing.receipt_number is not None
    assert billing.invoice_id is None
    assert billing.amount == Decimal("300.00")

    refreshed = await MtmSessionService.get(db, company_id=company.id, session_id=session.id)
    assert refreshed.status == "closed"
    assert refreshed.closed_at is not None


@pytest.mark.asyncio
async def test_mtm_session_close_with_administrative_posts_real_invoice(db, company, patient_contact, pharmacist):
    await _activate_packages(db, company, "administrative")
    # Mismo bug real ya encontrado y corregido en test_ecommerce_module.py/
    # test_reports_module.py (sesión de verificación externa, sep-2026):
    # sin este mapeo, InvoiceService.post -> JournalService.post_entry
    # falla con ValidationError("No hay cuenta configurada..."), no
    # relacionado con MTM en sí — cualquier flujo que contabilice una
    # factura real necesita este setup primero.
    await _setup_sales_invoice_account_mappings(db, company)

    session = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact), pharmacist_user_id=pharmacist.id
    )
    billing = await MtmSessionService.close(
        db, company_id=company.id, session_id=session.id,
        payload=pharmacy_schemas.MtmSessionClose(issue_date=date.today()), actor_id=pharmacist.id,
    )
    assert billing.billing_mode == "accounting_invoice"
    assert billing.invoice_id is not None
    assert billing.receipt_number is None


@pytest.mark.asyncio
async def test_mtm_session_close_twice_conflicts(db, company, patient_contact, pharmacist):
    session = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact), pharmacist_user_id=pharmacist.id
    )
    await MtmSessionService.close(
        db, company_id=company.id, session_id=session.id,
        payload=pharmacy_schemas.MtmSessionClose(issue_date=date.today()), actor_id=pharmacist.id,
    )
    with pytest.raises(ConflictError):
        await MtmSessionService.close(
            db, company_id=company.id, session_id=session.id,
            payload=pharmacy_schemas.MtmSessionClose(issue_date=date.today()), actor_id=pharmacist.id,
        )


@pytest.mark.asyncio
async def test_mtm_session_cancel_after_close_conflicts(db, company, patient_contact, pharmacist):
    session = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact), pharmacist_user_id=pharmacist.id
    )
    await MtmSessionService.close(
        db, company_id=company.id, session_id=session.id,
        payload=pharmacy_schemas.MtmSessionClose(issue_date=date.today()), actor_id=pharmacist.id,
    )
    with pytest.raises(ConflictError):
        await MtmSessionService.cancel(
            db, company_id=company.id, session_id=session.id,
            payload=pharmacy_schemas.MtmSessionCancel(cancel_reason="Tarde"), actor_id=pharmacist.id,
        )


@pytest.mark.asyncio
async def test_mtm_billing_cancel_voids_receipt_without_reverting_session(db, company, patient_contact, pharmacist):
    session = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact), pharmacist_user_id=pharmacist.id
    )
    billing = await MtmSessionService.close(
        db, company_id=company.id, session_id=session.id,
        payload=pharmacy_schemas.MtmSessionClose(issue_date=date.today()), actor_id=pharmacist.id,
    )
    cancelled_billing = await MtmSessionService.cancel_billing(
        db, company_id=company.id, billing_record_id=billing.id,
        payload=pharmacy_schemas.MtmSessionCancel(cancel_reason="Error de monto"), actor_id=pharmacist.id,
    )
    assert cancelled_billing.status == "cancelled"

    refreshed_session = await MtmSessionService.get(db, company_id=company.id, session_id=session.id)
    assert refreshed_session.status == "closed", "Anular el comprobante no revierte el estado de la sesión"


@pytest.mark.asyncio
async def test_get_billing_for_session_none_before_close(db, company, patient_contact, pharmacist):
    session = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact), pharmacist_user_id=pharmacist.id
    )
    billing = await MtmSessionService.get_billing_for_session(db, company_id=company.id, session_id=session.id)
    assert billing is None


@pytest.mark.asyncio
async def test_list_mtm_sessions_for_patient(db, company, patient_contact, pharmacist):
    s1 = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact, fee_amount=Decimal("150.00")), pharmacist_user_id=pharmacist.id
    )
    s2 = await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(patient_contact, fee_amount=Decimal("200.00")), pharmacist_user_id=pharmacist.id
    )
    other_patient = await ContactService.create_contact(
        db, company_id=company.id, payload=contacts_schemas.ContactCreate(name="Otro Cliente", is_customer=True), created_by=None,
    )
    await MtmSessionService.create(
        db, company_id=company.id, payload=_mtm_payload(other_patient), pharmacist_user_id=pharmacist.id
    )

    sessions = await MtmSessionService.list_for_patient(db, company_id=company.id, patient_contact_id=patient_contact.id)
    ids = {s.id for s in sessions}
    assert ids == {s1.id, s2.id}


# ---------------------------------------------------------------------------
# Módulo 20 — Reposición a Droguerías
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reorder_point_upsert_creates_then_updates_same_row(db, company, product, warehouse):
    first = await ReorderPointService.upsert(
        db, company_id=company.id,
        payload=pharmacy_schemas.ReorderPointUpsert(product_id=product.id, warehouse_id=warehouse.id, reorder_point=Decimal("10"), reorder_quantity=Decimal("50")),
        actor_id=None,
    )
    second = await ReorderPointService.upsert(
        db, company_id=company.id,
        payload=pharmacy_schemas.ReorderPointUpsert(product_id=product.id, warehouse_id=warehouse.id, reorder_point=Decimal("20"), reorder_quantity=Decimal("100")),
        actor_id=None,
    )
    assert second.id == first.id, "Debe actualizar la misma fila (unique product+warehouse), no duplicar"
    assert second.reorder_point == Decimal("20")
    assert second.reorder_quantity == Decimal("100")


@pytest.mark.asyncio
async def test_reorder_point_upsert_validates_preferred_vendor_is_vendor(db, company, product, warehouse, patient_contact):
    with pytest.raises(ValidationError):
        await ReorderPointService.upsert(
            db, company_id=company.id,
            payload=pharmacy_schemas.ReorderPointUpsert(
                product_id=product.id, warehouse_id=warehouse.id, reorder_point=Decimal("10"),
                reorder_quantity=Decimal("50"), preferred_vendor_id=patient_contact.id,
            ),
            actor_id=None,
        )


@pytest.mark.asyncio
async def test_reorder_suggestion_appears_when_stock_at_or_below_point(db, company, product, warehouse):
    await _seed_lot(db, company, product, warehouse, lot_number="L1", expiry_date=date.today() + timedelta(days=365), quantity=Decimal("5"))
    await ReorderPointService.upsert(
        db, company_id=company.id,
        payload=pharmacy_schemas.ReorderPointUpsert(product_id=product.id, warehouse_id=warehouse.id, reorder_point=Decimal("10"), reorder_quantity=Decimal("50")),
        actor_id=None,
    )

    suggestions = await ReorderSuggestionService.list_suggestions(db, company_id=company.id, warehouse_id=warehouse.id)
    assert len(suggestions) == 1
    assert suggestions[0].product_id == product.id
    assert suggestions[0].available_quantity == Decimal("5")
    assert suggestions[0].below_by == Decimal("5")


@pytest.mark.asyncio
async def test_reorder_suggestion_absent_when_stock_above_point(db, company, product, warehouse):
    await _seed_lot(db, company, product, warehouse, lot_number="L1", expiry_date=date.today() + timedelta(days=365), quantity=Decimal("100"))
    await ReorderPointService.upsert(
        db, company_id=company.id,
        payload=pharmacy_schemas.ReorderPointUpsert(product_id=product.id, warehouse_id=warehouse.id, reorder_point=Decimal("10"), reorder_quantity=Decimal("50")),
        actor_id=None,
    )

    suggestions = await ReorderSuggestionService.list_suggestions(db, company_id=company.id, warehouse_id=warehouse.id)
    assert suggestions == []


@pytest.mark.asyncio
async def test_reorder_suggestion_without_any_stock_row_counts_as_zero(db, company, product, warehouse):
    """Producto con punto de pedido configurado pero SIN ningún
    StockMovement todavía (nunca se compró) — debe aparecer como
    sugerencia con 0 disponible, no fallar ni quedar fuera del cálculo."""
    await ReorderPointService.upsert(
        db, company_id=company.id,
        payload=pharmacy_schemas.ReorderPointUpsert(product_id=product.id, warehouse_id=warehouse.id, reorder_point=Decimal("10"), reorder_quantity=Decimal("50")),
        actor_id=None,
    )
    suggestions = await ReorderSuggestionService.list_suggestions(db, company_id=company.id, warehouse_id=warehouse.id)
    assert len(suggestions) == 1
    assert suggestions[0].available_quantity == Decimal("0")


@pytest.mark.asyncio
async def test_generate_purchase_order_requires_administrative(db, company, product, warehouse, vendor):
    with pytest.raises(PackageNotLicensedError):
        await ReorderSuggestionService.generate_purchase_order(
            db, company_id=company.id,
            payload=pharmacy_schemas.ReorderPurchaseOrderGenerate(
                warehouse_id=warehouse.id, vendor_id=vendor.id,
                lines=[pharmacy_schemas.ReorderPurchaseOrderLineInput(product_id=product.id, quantity=Decimal("50"), unit_cost=Decimal("3.50"))],
            ),
            actor_id=None,
        )


@pytest.mark.asyncio
async def test_generate_purchase_order_with_administrative_creates_real_po(db, company, product, warehouse, vendor):
    await _activate_packages(db, company, "administrative")

    po = await ReorderSuggestionService.generate_purchase_order(
        db, company_id=company.id,
        payload=pharmacy_schemas.ReorderPurchaseOrderGenerate(
            warehouse_id=warehouse.id, vendor_id=vendor.id,
            lines=[pharmacy_schemas.ReorderPurchaseOrderLineInput(product_id=product.id, quantity=Decimal("50"), unit_cost=Decimal("3.50"))],
        ),
        actor_id=None,
    )
    assert po.status == "draft"
    assert po.vendor_id == vendor.id
    assert len(po.lines) == 1
    assert po.lines[0].quantity_ordered == Decimal("50")


@pytest.mark.asyncio
async def test_reorder_point_delete_removes_it_from_suggestions(db, company, product, warehouse):
    point = await ReorderPointService.upsert(
        db, company_id=company.id,
        payload=pharmacy_schemas.ReorderPointUpsert(product_id=product.id, warehouse_id=warehouse.id, reorder_point=Decimal("10"), reorder_quantity=Decimal("50")),
        actor_id=None,
    )
    await ReorderPointService.delete(db, company_id=company.id, reorder_point_id=point.id)

    suggestions = await ReorderSuggestionService.list_suggestions(db, company_id=company.id, warehouse_id=warehouse.id)
    assert suggestions == []


@pytest.mark.asyncio
async def test_reorder_point_delete_unknown_raises_not_found(db, company):
    with pytest.raises(NotFoundError):
        await ReorderPointService.delete(db, company_id=company.id, reorder_point_id=999999)


# ---------------------------------------------------------------------------------
# Módulo 17 — Interacciones [extendido]. Ver DED-58 a DED-61 en models.py.
# ---------------------------------------------------------------------------------------------
@pytest_asyncio.fixture
async def product_b(db, company):
    unique = uuid.uuid4().hex[:6]
    return await ProductService.create(
        db, company_id=company.id,
        payload=inventory_schemas.ProductCreate(
            sku=f"MED-{unique}", name="Warfarina 5mg", product_type=inventory_schemas.ProductTypeEnum.consumible, tracks_lots=False,
        ),
        created_by=None,
    )


@pytest.mark.asyncio
async def test_interaction_check_finds_known_pair(db, company, product, product_b):
    """Amoxicilina (fixture `product`) + Metotrexato (fixture `product_b`) —
    par real y conocido en el seed (DED-58), severidad 'moderate'."""
    await ProductActiveIngredientService.set(
        db, company_id=company.id, created_by=None,
        payload=pharmacy_schemas.ProductActiveIngredientSet(product_id=product.id, active_ingredient="Amoxicillin"),
    )
    await ProductActiveIngredientService.set(
        db, company_id=company.id, created_by=None,
        payload=pharmacy_schemas.ProductActiveIngredientSet(product_id=product_b.id, active_ingredient="  METHOTREXATE "),
    )

    result = await DrugInteractionService.check(
        db, company_id=company.id,
        payload=pharmacy_schemas.InteractionCheckRequest(product_ids=[product.id, product_b.id]),
    )

    assert result.unchecked_product_ids == []
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.severity == pharmacy_schemas.InteractionSeverityEnum.moderate
    assert {warning.product_id_a, warning.product_id_b} == {product.id, product_b.id}
    assert "metotrexato" in warning.description.lower()


@pytest.mark.asyncio
async def test_interaction_check_no_warning_for_unrelated_pair(db, company, product, product_b):
    """Dos principios activos reales que NO están en el seed — sin
    warning, sin falso positivo."""
    await ProductActiveIngredientService.set(
        db, company_id=company.id, created_by=None,
        payload=pharmacy_schemas.ProductActiveIngredientSet(product_id=product.id, active_ingredient="paracetamol"),
    )
    await ProductActiveIngredientService.set(
        db, company_id=company.id, created_by=None,
        payload=pharmacy_schemas.ProductActiveIngredientSet(product_id=product_b.id, active_ingredient="loratadine"),
    )

    result = await DrugInteractionService.check(
        db, company_id=company.id,
        payload=pharmacy_schemas.InteractionCheckRequest(product_ids=[product.id, product_b.id]),
    )

    assert result.warnings == []
    assert result.unchecked_product_ids == []


@pytest.mark.asyncio
async def test_interaction_check_reports_unmapped_product(db, company, product, product_b):
    """Un producto sin principio activo mapeado (DED-59) aparece en
    `unchecked_product_ids`, no rompe el chequeo del resto."""
    await ProductActiveIngredientService.set(
        db, company_id=company.id, created_by=None,
        payload=pharmacy_schemas.ProductActiveIngredientSet(product_id=product.id, active_ingredient="ibuprofen"),
    )
    # product_b nunca se mapea.

    result = await DrugInteractionService.check(
        db, company_id=company.id,
        payload=pharmacy_schemas.InteractionCheckRequest(product_ids=[product.id, product_b.id]),
    )

    assert result.warnings == []
    assert result.unchecked_product_ids == [product_b.id]


@pytest.mark.asyncio
async def test_interaction_check_major_severity_and_description(db, company, product, product_b):
    """Un par 'major' real del seed (aspirina + warfarina) — confirma
    severidad alta y descripción no vacía."""
    await ProductActiveIngredientService.set(
        db, company_id=company.id, created_by=None,
        payload=pharmacy_schemas.ProductActiveIngredientSet(product_id=product.id, active_ingredient="aspirin"),
    )
    await ProductActiveIngredientService.set(
        db, company_id=company.id, created_by=None,
        payload=pharmacy_schemas.ProductActiveIngredientSet(product_id=product_b.id, active_ingredient="warfarin"),
    )

    result = await DrugInteractionService.check(
        db, company_id=company.id,
        payload=pharmacy_schemas.InteractionCheckRequest(product_ids=[product.id, product_b.id]),
    )

    assert len(result.warnings) == 1
    assert result.warnings[0].severity == pharmacy_schemas.InteractionSeverityEnum.major
    assert len(result.warnings[0].description) > 0


@pytest.mark.asyncio
async def test_active_ingredient_set_is_idempotent_upsert(db, company, product):
    """Volver a mapear el mismo producto actualiza el ingrediente, no
    crea una segunda fila (uq_product_active_ingredients_company_product)."""
    await ProductActiveIngredientService.set(
        db, company_id=company.id, created_by=None,
        payload=pharmacy_schemas.ProductActiveIngredientSet(product_id=product.id, active_ingredient="aspirin"),
    )
    updated = await ProductActiveIngredientService.set(
        db, company_id=company.id, created_by=None,
        payload=pharmacy_schemas.ProductActiveIngredientSet(product_id=product.id, active_ingredient="ibuprofen"),
    )

    rows = await ProductActiveIngredientService.list(db, company_id=company.id)
    assert len(rows) == 1
    assert updated.active_ingredient == "ibuprofen"


# ---------------------------------------------------------------------------------------------
# Módulo 18 — Aseguradoras [extendido]. Ver DED-62 a DED-64 en models.py.
# ---------------------------------------------------------------------------------------------
@pytest_asyncio.fixture
async def insurer_contact(db, company):
    return await ContactService.create_contact(
        db, company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Aseguradora Test", is_customer=True),
        created_by=None,
    )


@pytest_asyncio.fixture
async def insurance_provider(db, company, insurer_contact):
    return await InsuranceProviderService.create(
        db, company_id=company.id,
        payload=pharmacy_schemas.InsuranceProviderCreate(contact_id=insurer_contact.id, default_coverage_percentage=Decimal("80")),
    )


async def _dispensed_order(db, company, patient_contact, product, warehouse, pharmacist):
    await _seed_lot(db, company, product, warehouse, lot_number="LOT-INS", expiry_date=date.today() + timedelta(days=30), quantity=Decimal(10))
    return await DispensationService.create(
        db, company_id=company.id, dispensed_by=pharmacist.id,
        payload=_dispense_payload(
            patient_contact, product, Decimal(1), warehouse_id=warehouse.id,
            allergy_check_notes="Sin alergias conocidas",
        ),
    )


@pytest.mark.asyncio
async def test_insurance_provider_requires_is_customer_contact(db, company):
    non_customer = await ContactService.create_contact(
        db, company_id=company.id, payload=contacts_schemas.ContactCreate(name="No Cliente", is_vendor=True), created_by=None,
    )
    with pytest.raises(ValidationError):
        await InsuranceProviderService.create(
            db, company_id=company.id,
            payload=pharmacy_schemas.InsuranceProviderCreate(contact_id=non_customer.id),
        )


@pytest.mark.asyncio
async def test_claim_full_lifecycle_claim_only_when_administrative_inactive(
    db, company, patient_contact, product, warehouse, pharmacist, insurance_provider,
):
    order = await _dispensed_order(db, company, patient_contact, product, warehouse, pharmacist)

    claim = await InsuranceClaimService.create(
        db, company_id=company.id,
        payload=pharmacy_schemas.InsuranceClaimCreate(
            dispensation_order_id=order.id, insurance_provider_id=insurance_provider.id,
            amount_total=Decimal("100.00"), amount_patient_copay=Decimal("20.00"), amount_claimed_insurer=Decimal("80.00"),
        ),
    )
    assert claim.status == "pending"

    claim = await InsuranceClaimService.submit(db, company_id=company.id, claim_id=claim.id)
    assert claim.status == "submitted"

    claim = await InsuranceClaimService.approve(db, company_id=company.id, claim_id=claim.id, actor_id=None)
    assert claim.status == "approved"
    assert claim.billing_mode == "claim_only"
    assert claim.invoice_id is None

    claim = await InsuranceClaimService.pay(
        db, company_id=company.id, claim_id=claim.id, payload=pharmacy_schemas.InsuranceClaimPay(), actor_id=None,
    )
    assert claim.status == "paid"
    assert claim.payment_id is None


@pytest.mark.asyncio
async def test_claim_creates_real_invoice_and_payment_when_administrative_active(
    db, company, patient_contact, product, warehouse, pharmacist, insurance_provider,
):
    db.add(core_models.CompanyPackage(company_id=company.id, package="administrative", status="active"))
    await db.commit()

    order = await _dispensed_order(db, company, patient_contact, product, warehouse, pharmacist)
    await _setup_sales_invoice_account_mappings(db, company)

    claim = await InsuranceClaimService.create(
        db, company_id=company.id,
        payload=pharmacy_schemas.InsuranceClaimCreate(
            dispensation_order_id=order.id, insurance_provider_id=insurance_provider.id,
            amount_total=Decimal("100.00"), amount_patient_copay=Decimal("20.00"), amount_claimed_insurer=Decimal("80.00"),
        ),
    )
    claim = await InsuranceClaimService.submit(db, company_id=company.id, claim_id=claim.id)
    claim = await InsuranceClaimService.approve(db, company_id=company.id, claim_id=claim.id, actor_id=None)

    assert claim.billing_mode == "accounting_invoice"
    assert claim.invoice_id is not None

    invoice = await InvoiceService.get(db, company_id=company.id, invoice_id=claim.invoice_id)
    assert invoice.status == "posted"
    assert invoice.total == Decimal("80.00")
    assert invoice.contact_id == insurance_provider.contact_id

    claim = await InsuranceClaimService.pay(
        db, company_id=company.id, claim_id=claim.id, payload=pharmacy_schemas.InsuranceClaimPay(), actor_id=None,
    )
    assert claim.status == "paid"
    assert claim.payment_id is not None

    invoice = await InvoiceService.get(db, company_id=company.id, invoice_id=claim.invoice_id)
    assert invoice.status == "paid"
    assert invoice.balance_due == Decimal("0.00")


@pytest.mark.asyncio
async def test_claim_amounts_must_sum_to_total(db, company, patient_contact, product, warehouse, pharmacist, insurance_provider):
    order = await _dispensed_order(db, company, patient_contact, product, warehouse, pharmacist)
    with pytest.raises(ValueError):
        pharmacy_schemas.InsuranceClaimCreate(
            dispensation_order_id=order.id, insurance_provider_id=insurance_provider.id,
            amount_total=Decimal("100.00"), amount_patient_copay=Decimal("20.00"), amount_claimed_insurer=Decimal("70.00"),
        )


@pytest.mark.asyncio
async def test_claim_reject_only_before_approval(
    db, company, patient_contact, product, warehouse, pharmacist, insurance_provider,
):
    order = await _dispensed_order(db, company, patient_contact, product, warehouse, pharmacist)
    claim = await InsuranceClaimService.create(
        db, company_id=company.id,
        payload=pharmacy_schemas.InsuranceClaimCreate(
            dispensation_order_id=order.id, insurance_provider_id=insurance_provider.id,
            amount_total=Decimal("50.00"), amount_patient_copay=Decimal("50.00"), amount_claimed_insurer=Decimal("0.00"),
        ),
    )
    claim = await InsuranceClaimService.reject(
        db, company_id=company.id, claim_id=claim.id, payload=pharmacy_schemas.InsuranceClaimReject(rejection_reason="Póliza vencida"),
    )
    assert claim.status == "rejected"
    assert claim.rejection_reason == "Póliza vencida"

    with pytest.raises(ConflictError):
        await InsuranceClaimService.submit(db, company_id=company.id, claim_id=claim.id)


@pytest.mark.asyncio
async def test_claim_cannot_be_created_for_voided_dispensation(
    db, company, patient_contact, product, warehouse, pharmacist, insurance_provider,
):
    order = await _dispensed_order(db, company, patient_contact, product, warehouse, pharmacist)
    await DispensationService.void(
        db, company_id=company.id, order_id=order.id, actor_id=None,
        payload=pharmacy_schemas.DispensationVoid(void_reason="Error de captura"),
    )

    with pytest.raises(ValidationError):
        await InsuranceClaimService.create(
            db, company_id=company.id,
            payload=pharmacy_schemas.InsuranceClaimCreate(
                dispensation_order_id=order.id, insurance_provider_id=insurance_provider.id,
                amount_total=Decimal("50.00"), amount_patient_copay=Decimal("50.00"), amount_claimed_insurer=Decimal("0.00"),
            ),
        )


@pytest.mark.asyncio
async def test_patient_insurance_policy_create_and_list(db, company, patient_contact, insurance_provider):
    policy = await PatientInsurancePolicyService.create(
        db, company_id=company.id,
        payload=pharmacy_schemas.PatientInsurancePolicyCreate(
            patient_contact_id=patient_contact.id, insurance_provider_id=insurance_provider.id,
            policy_number="POL-001", coverage_percentage=Decimal("80"),
        ),
    )
    assert policy.policy_number == "POL-001"

    policies = await PatientInsurancePolicyService.list_for_patient(db, company_id=company.id, patient_contact_id=patient_contact.id)
    assert len(policies) == 1
