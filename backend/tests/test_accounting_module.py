"""
Tests de integración del módulo accounting — contra PostgreSQL real.

HALLAZGO REAL de la regresión QA externa (sep-2026):
catalogo_casos_regresion_erp_crm_v1.md afirma "Ya existe
tests/test_accounting_module.py de una sesión anterior — correrlo
primero". Confirmado por búsqueda exhaustiva en el repo real (clonado de
GitHub, no un ZIP de sesión de chat vieja): este archivo NO existía en
ningún lado. El catálogo estaba desactualizado/incorrecto en este punto
— se documenta en STATE.md sección del módulo 6 y se escribe el archivo
que faltaba, desde cero, contra el código real (no contra lo que el
catálogo asumía que ya estaba probado).

Mismo patrón que el resto de la suite: llama a la capa de servicio
directamente, contra Postgres real, no HTTP/mocks.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.accounting import schemas, models as accounting_models
from app.accounting.services import (
    AccountService,
    CreditControlService,
    CreditDebitNoteService,
    DocumentAccountMappingService,
    InvoiceService,
    JournalService,
    PaymentService,
    TaxRateService,
)
from app.contacts import schemas as contacts_schemas
from app.contacts.services import ContactService
from app.core import models as core_models
from app.database import AsyncSessionLocal
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
async def customer(db, company):
    return await ContactService.create_contact(
        db, company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Cliente Test", is_customer=True),
        created_by=None,
    )


@pytest_asyncio.fixture
async def vendor(db, company):
    return await ContactService.create_contact(
        db, company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Proveedor Test", is_vendor=True),
        created_by=None,
    )


@pytest_asyncio.fixture
async def tax_rate(db, company):
    return await TaxRateService.create(
        db, company_id=company.id, payload=schemas.TaxRateCreate(name="ISV 15%", rate=Decimal(15))
    )


async def _account(db, company_id, account_type: schemas.AccountTypeEnum, code: str):
    return await AccountService.create(
        db, company_id=company_id,
        payload=schemas.AccountCreate(code=code, name=code, account_type=account_type),
    )


async def _setup_full_mapping(db, company_id):
    """Plan de cuentas mínimo + mapeo para TODOS los document_type reales
    (factura venta/compra, las 4 notas, pago recibido/hecho) — evita
    repetir esto en cada test."""
    accounts = {
        "receivable": await _account(db, company_id, schemas.AccountTypeEnum.receivable, "1-RECV"),
        "payable": await _account(db, company_id, schemas.AccountTypeEnum.payable, "2-PAY"),
        "income": await _account(db, company_id, schemas.AccountTypeEnum.income, "4-INC"),
        "tax": await _account(db, company_id, schemas.AccountTypeEnum.tax, "2-TAX"),
        "cash_bank": await _account(db, company_id, schemas.AccountTypeEnum.cash_bank, "1-CASH"),
        "adjustment": await _account(db, company_id, schemas.AccountTypeEnum.adjustment, "5-ADJ"),
    }
    roles_by_doc = {
        "sales_invoice": ["receivable", "income", "tax"],
        "purchase_invoice": ["adjustment", "tax", "payable"],
        "sales_credit_note": ["income", "tax", "receivable"],
        "sales_debit_note": ["receivable", "income", "tax"],
        "purchase_credit_note": ["payable", "adjustment", "tax"],
        "purchase_debit_note": ["adjustment", "tax", "payable"],
        "payment_received": ["cash_bank", "receivable"],
        "payment_made": ["payable", "cash_bank"],
    }
    for doc_type, roles in roles_by_doc.items():
        for role in roles:
            await DocumentAccountMappingService.upsert(
                db, company_id=company_id,
                payload=schemas.DocumentAccountMappingCreate(
                    document_type=doc_type, role=role, account_id=accounts[role].id
                ),
            )
    return accounts


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sale_invoice_full_cycle_balanced_entry_and_balance_due(db, company, customer, tax_rate):
    await _setup_full_mapping(db, company.id)

    invoice = await InvoiceService.create_draft(
        db, company_id=company.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
            lines=[schemas.InvoiceLineCreate(description="Servicio", quantity=Decimal(1), unit_price=Decimal(1500), tax_rate_id=tax_rate.id)],
        ),
        created_by=None,
    )
    assert invoice.subtotal == Decimal("1500.00")
    assert invoice.tax_amount == Decimal("225.00")
    assert invoice.total == Decimal("1725.00")
    assert invoice.balance_due == Decimal("1725.00")

    posted = await InvoiceService.post(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)
    assert posted.status == "posted"

    result = await db.execute(
        text("SELECT SUM(debit), SUM(credit) FROM journal_lines WHERE journal_entry_id = :jid"),
        {"jid": posted.journal_entry_id},
    )
    total_debit, total_credit = result.first()
    assert total_debit == total_credit == Decimal("1725.00")


@pytest.mark.asyncio
async def test_purchase_invoice_full_cycle(db, company, vendor):
    await _setup_full_mapping(db, company.id)

    invoice = await InvoiceService.create_draft(
        db, company_id=company.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.purchase, contact_id=vendor.id, issue_date=date.today(),
            lines=[schemas.InvoiceLineCreate(description="Compra", quantity=Decimal(2), unit_price=Decimal(500))],
        ),
        created_by=None,
    )
    posted = await InvoiceService.post(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)
    assert posted.status == "posted"
    assert posted.balance_due == Decimal("1000.00")


@pytest.mark.parametrize(
    "direction,note_type,expected_document_type",
    [
        (schemas.DirectionEnum.sale, schemas.NoteTypeEnum.credit, "sales_credit_note"),
        (schemas.DirectionEnum.sale, schemas.NoteTypeEnum.debit, "sales_debit_note"),
        (schemas.DirectionEnum.purchase, schemas.NoteTypeEnum.credit, "purchase_credit_note"),
        (schemas.DirectionEnum.purchase, schemas.NoteTypeEnum.debit, "purchase_debit_note"),
    ],
)
@pytest.mark.asyncio
async def test_credit_debit_note_document_type_never_singular_sale(
    db, company, customer, vendor, direction, note_type, expected_document_type
):
    """Catálogo módulo 6: las 4 combinaciones nota×dirección — confirmar
    específicamente el document_type generado. Bug real ya encontrado y
    corregido (ver STATE.md, CreditDebitNoteService.post): una
    construcción ingenua daba 'sale_credit_note' (singular, inválido) en
    vez de 'sales_credit_note'. Verificado antes solo vía test de
    integración de FRONTEND — este es el primer test de BACKEND directo
    para las 4 combinaciones."""
    await _setup_full_mapping(db, company.id)
    contact = customer if direction == schemas.DirectionEnum.sale else vendor

    note = await CreditDebitNoteService.create_draft(
        db, company_id=company.id,
        payload=schemas.CreditDebitNoteCreate(
            note_type=note_type, direction=direction, contact_id=contact.id, reason="Ajuste",
            issue_date=date.today(),
            lines=[schemas.CreditDebitNoteLineCreate(description="Ajuste", quantity=Decimal(1), unit_price=Decimal(100))],
        ),
        created_by=None,
    )
    posted = await CreditDebitNoteService.post(db, company_id=company.id, note_id=note.id, actor_id=None)

    result = await db.execute(text("SELECT document_type FROM journal_entries WHERE id = :jid"), {"jid": posted.journal_entry_id})
    assert result.scalar_one() == expected_document_type


@pytest.mark.asyncio
async def test_payment_allocation_updates_balance_due_and_status(db, company, customer, tax_rate):
    await _setup_full_mapping(db, company.id)
    invoice = await InvoiceService.create_draft(
        db, company_id=company.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
            lines=[schemas.InvoiceLineCreate(description="Servicio", quantity=Decimal(1), unit_price=Decimal(1000))],
        ),
        created_by=None,
    )
    invoice = await InvoiceService.post(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)

    # Pago parcial.
    payment1 = await PaymentService.create_draft(
        db, company_id=company.id,
        payload=schemas.PaymentCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, payment_date=date.today(),
            method=schemas.PaymentMethodEnum.cash, amount=Decimal(400),
            allocations=[schemas.PaymentAllocationCreate(invoice_id=invoice.id, amount_applied=Decimal(400))],
        ),
        created_by=None,
    )
    await PaymentService.post(db, company_id=company.id, payment_id=payment1.id, actor_id=None)
    invoice = await InvoiceService.get(db, company_id=company.id, invoice_id=invoice.id)
    assert invoice.balance_due == Decimal("600.00")
    assert invoice.status == "partially_paid"

    # Pago que salda el resto.
    payment2 = await PaymentService.create_draft(
        db, company_id=company.id,
        payload=schemas.PaymentCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, payment_date=date.today(),
            method=schemas.PaymentMethodEnum.cash, amount=Decimal(600),
            allocations=[schemas.PaymentAllocationCreate(invoice_id=invoice.id, amount_applied=Decimal(600))],
        ),
        created_by=None,
    )
    await PaymentService.post(db, company_id=company.id, payment_id=payment2.id, actor_id=None)
    invoice = await InvoiceService.get(db, company_id=company.id, invoice_id=invoice.id)
    assert invoice.balance_due == Decimal("0.00")
    assert invoice.status == "paid"


# ---------------------------------------------------------------------------
# Casos límite y validación
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_journal_post_entry_unbalanced_lines_rejected(db, company):
    accounts = {
        "receivable": await _account(db, company.id, schemas.AccountTypeEnum.receivable, "1-RECV"),
        "income": await _account(db, company.id, schemas.AccountTypeEnum.income, "4-INC"),
    }
    await DocumentAccountMappingService.upsert(
        db, company_id=company.id,
        payload=schemas.DocumentAccountMappingCreate(document_type="sales_invoice", role="receivable", account_id=accounts["receivable"].id),
    )
    await DocumentAccountMappingService.upsert(
        db, company_id=company.id,
        payload=schemas.DocumentAccountMappingCreate(document_type="sales_invoice", role="income", account_id=accounts["income"].id),
    )
    with pytest.raises(ValidationError):
        await JournalService.post_entry(
            db, company_id=company.id, entry_date=date.today(), document_type="sales_invoice", document_id=999,
            description="Desbalanceado a propósito",
            lines=[("receivable", "debit", Decimal(100)), ("income", "credit", Decimal(99))],
            created_by=None,
        )


@pytest.mark.asyncio
async def test_post_without_account_mapping_rejected_clearly_no_partial_entry(db, company, customer):
    """Catálogo módulo 6: documento sin mapeo de cuenta configurado →
    rechazado con mensaje claro, NUNCA un asiento parcial. No se
    configura NINGÚN DocumentAccountMapping."""
    invoice = await InvoiceService.create_draft(
        db, company_id=company.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
            lines=[schemas.InvoiceLineCreate(description="Servicio", quantity=Decimal(1), unit_price=Decimal(100))],
        ),
        created_by=None,
    )
    with pytest.raises(ValidationError):
        await InvoiceService.post(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)

    # Sin asiento parcial: la factura sigue en draft, sin journal_entry_id,
    # y no hay NINGUNA fila en journal_entries para este documento.
    refreshed = await InvoiceService.get(db, company_id=company.id, invoice_id=invoice.id)
    assert refreshed.status == "draft"
    assert refreshed.journal_entry_id is None
    result = await db.execute(
        text("SELECT count(*) FROM journal_entries WHERE document_type = 'sales_invoice' AND document_id = :did"),
        {"did": invoice.id},
    )
    assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_payment_exceeding_balance_checked_at_post_time_not_create_time(db, company, customer):
    """Catálogo módulo 6: dos pagos válidos por separado al CREARSE (cada
    uno individualmente no excede el saldo), pero el segundo debe fallar
    al POSTEARSE si el primero ya saldó la factura — el chequeo real es
    contra el saldo AL MOMENTO DE post(), bajo lock, no contra el saldo
    al momento de create()."""
    await _setup_full_mapping(db, company.id)
    invoice = await InvoiceService.create_draft(
        db, company_id=company.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
            lines=[schemas.InvoiceLineCreate(description="Servicio", quantity=Decimal(1), unit_price=Decimal(1000))],
        ),
        created_by=None,
    )
    invoice = await InvoiceService.post(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)

    # Ambos pagos son válidos al CREARSE: cada uno, aislado, no excede
    # los 1000 de saldo.
    payment_a = await PaymentService.create_draft(
        db, company_id=company.id,
        payload=schemas.PaymentCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, payment_date=date.today(),
            method=schemas.PaymentMethodEnum.cash, amount=Decimal(700),
            allocations=[schemas.PaymentAllocationCreate(invoice_id=invoice.id, amount_applied=Decimal(700))],
        ),
        created_by=None,
    )
    payment_b = await PaymentService.create_draft(
        db, company_id=company.id,
        payload=schemas.PaymentCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, payment_date=date.today(),
            method=schemas.PaymentMethodEnum.cash, amount=Decimal(700),
            allocations=[schemas.PaymentAllocationCreate(invoice_id=invoice.id, amount_applied=Decimal(700))],
        ),
        created_by=None,
    )

    # Postear el primero: 1000 - 700 = 300 de saldo.
    await PaymentService.post(db, company_id=company.id, payment_id=payment_a.id, actor_id=None)

    # El segundo (también "válido" al crearse) ahora excede el saldo real
    # (300) al intentar postearse.
    with pytest.raises(ValidationError):
        await PaymentService.post(db, company_id=company.id, payment_id=payment_b.id, actor_id=None)


@pytest.mark.asyncio
async def test_posted_invoice_cannot_be_cancelled_directly(db, company, customer):
    await _setup_full_mapping(db, company.id)
    invoice = await InvoiceService.create_draft(
        db, company_id=company.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
            lines=[schemas.InvoiceLineCreate(description="Servicio", quantity=Decimal(1), unit_price=Decimal(100))],
        ),
        created_by=None,
    )
    invoice = await InvoiceService.post(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)

    with pytest.raises(ConflictError):
        await InvoiceService.cancel(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)

    # Una factura draft sí se puede cancelar directo.
    other = await InvoiceService.create_draft(
        db, company_id=company.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
            lines=[schemas.InvoiceLineCreate(description="Otra", quantity=Decimal(1), unit_price=Decimal(50))],
        ),
        created_by=None,
    )
    cancelled = await InvoiceService.cancel(db, company_id=company.id, invoice_id=other.id, actor_id=None)
    assert cancelled.status == "cancelled"


# ---------------------------------------------------------------------------
# Motor de Contención Financiera: condiciones independientes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_credit_control_overdue_and_exceeded_are_independent_conditions(db, company, customer):
    """Catálogo módulo 6: deuda vencida Y crédito excedido son DOS
    condiciones independientes, cada una debe bloquear por sí sola —
    probar cada una aislada, no solo combinadas."""
    await _setup_full_mapping(db, company.id)

    # Condición 1 SOLA: crédito excedido, sin nada vencido (due_date futura).
    await ContactService.update_credit_limit(db, company_id=company.id, contact_id=customer.id, credit_limit=Decimal(100), updated_by=None)
    inv1 = await InvoiceService.create_draft(
        db, company_id=company.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
            due_date=date(2099, 1, 1),  # bien a futuro — nada vencido
            lines=[schemas.InvoiceLineCreate(description="Servicio", quantity=Decimal(1), unit_price=Decimal(500))],
        ),
        created_by=None,
    )
    await InvoiceService.post(db, company_id=company.id, invoice_id=inv1.id, actor_id=None)

    status = await CreditControlService.get_credit_status(db, company_id=company.id, contact_id=customer.id)
    assert status.credit_exceeded is True
    assert status.has_overdue_invoices is False
    assert status.is_blocked is True  # basta con UNA condición

    with pytest.raises(ConflictError):
        await CreditControlService.assert_customer_not_blocked(db, company_id=company.id, contact_id=customer.id)


@pytest.mark.asyncio
async def test_credit_control_overdue_alone_blocks_even_under_limit(db, company, customer):
    """Condición 2 SOLA: factura vencida con saldo pendiente, pero MUY
    por debajo del límite de crédito — debe bloquear igual, el límite no
    la salva."""
    await _setup_full_mapping(db, company.id)
    await ContactService.update_credit_limit(db, company_id=company.id, contact_id=customer.id, credit_limit=Decimal(999999), updated_by=None)

    invoice = await InvoiceService.create_draft(
        db, company_id=company.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date(2020, 1, 1),
            due_date=date(2020, 2, 1),  # muy vencida
            lines=[schemas.InvoiceLineCreate(description="Servicio", quantity=Decimal(1), unit_price=Decimal(10))],
        ),
        created_by=None,
    )
    await InvoiceService.post(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)

    status = await CreditControlService.get_credit_status(db, company_id=company.id, contact_id=customer.id)
    assert status.has_overdue_invoices is True
    assert status.credit_exceeded is False  # muy por debajo del límite
    assert status.is_blocked is True  # vencida sola alcanza

    with pytest.raises(ConflictError):
        await CreditControlService.assert_customer_not_blocked(db, company_id=company.id, contact_id=customer.id)


# ---------------------------------------------------------------------------
# RLS
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_invoice_read(db):
    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    company_a = core_models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = core_models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    contact_a = await ContactService.create_contact(
        db, company_id=company_a.id, payload=contacts_schemas.ContactCreate(name="Cliente A", is_customer=True), created_by=None
    )
    await _setup_full_mapping(db, company_a.id)
    invoice = await InvoiceService.create_draft(
        db, company_id=company_a.id,
        payload=schemas.InvoiceCreate(
            direction=schemas.DirectionEnum.sale, contact_id=contact_a.id, issue_date=date.today(),
            lines=[schemas.InvoiceLineCreate(description="X", quantity=Decimal(1), unit_price=Decimal(100))],
        ),
        created_by=None,
    )
    await db.commit()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    with pytest.raises(NotFoundError):
        await InvoiceService.get(db, company_id=company_b.id, invoice_id=invoice.id)

    result = await db.execute(text("SELECT count(*) FROM invoices WHERE id = :iid"), {"iid": invoice.id})
    assert result.scalar_one() == 0
