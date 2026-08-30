from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting import schemas
from app.accounting.services import (
    AccountService,
    CreditControlService,
    CreditDebitNoteService,
    DocumentAccountMappingService,
    InvoiceService,
    PaymentService,
    TaxRateService,
)
from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_permission
from app.core.models import User
from app.core.services import IdempotencyService

router = APIRouter(prefix="/accounting", tags=["accounting"])


# ---------------------------------------------------------------------------
# Plan de Cuentas
# ---------------------------------------------------------------------------
@router.post("/accounts", response_model=schemas.AccountRead, status_code=201)
async def create_account(
    payload: schemas.AccountCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:account:create")),
) -> schemas.AccountRead:
    account = await AccountService.create(db, company_id=company_id, payload=payload)
    return schemas.AccountRead.model_validate(account)


@router.get("/accounts", response_model=list[schemas.AccountRead])
async def list_accounts(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:account:list")),
) -> list[schemas.AccountRead]:
    return [schemas.AccountRead.model_validate(a) for a in await AccountService.list(db, company_id=company_id)]


# ---------------------------------------------------------------------------
# Mapeo documento → cuentas
# ---------------------------------------------------------------------------
@router.post("/document-account-mappings", response_model=schemas.DocumentAccountMappingRead, status_code=201)
async def upsert_document_account_mapping(
    payload: schemas.DocumentAccountMappingCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:document_account_mapping:upsert")),
) -> schemas.DocumentAccountMappingRead:
    mapping = await DocumentAccountMappingService.upsert(db, company_id=company_id, payload=payload)
    return schemas.DocumentAccountMappingRead.model_validate(mapping)


@router.get("/document-account-mappings", response_model=list[schemas.DocumentAccountMappingRead])
async def list_document_account_mappings(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:document_account_mapping:list")),
) -> list[schemas.DocumentAccountMappingRead]:
    return [
        schemas.DocumentAccountMappingRead.model_validate(m)
        for m in await DocumentAccountMappingService.list(db, company_id=company_id)
    ]


# ---------------------------------------------------------------------------
# Gestión de Impuestos
# ---------------------------------------------------------------------------
@router.post("/tax-rates", response_model=schemas.TaxRateRead, status_code=201)
async def create_tax_rate(
    payload: schemas.TaxRateCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:tax_rate:create")),
) -> schemas.TaxRateRead:
    tax_rate = await TaxRateService.create(db, company_id=company_id, payload=payload)
    return schemas.TaxRateRead.model_validate(tax_rate)


@router.get("/tax-rates", response_model=list[schemas.TaxRateRead])
async def list_tax_rates(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:tax_rate:list")),
) -> list[schemas.TaxRateRead]:
    return [schemas.TaxRateRead.model_validate(t) for t in await TaxRateService.list(db, company_id=company_id)]


# ---------------------------------------------------------------------------
# Facturación de Venta y Proveedor
# ---------------------------------------------------------------------------
@router.post("/invoices", response_model=schemas.InvoiceRead, status_code=201)
async def create_invoice(
    payload: schemas.InvoiceCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("accounting:invoice:create")),
) -> schemas.InvoiceRead:
    async def _command() -> schemas.InvoiceRead:
        invoice = await InvoiceService.create_draft(db, company_id=company_id, payload=payload, created_by=actor.id)
        return schemas.InvoiceRead.model_validate(invoice)

    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint="POST /accounting/invoices",
        payload_dict=payload.model_dump(mode="json"),
        domain="accounting",
        success_status_code=201,
        command=_command,
    )


@router.get("/invoices", response_model=list[schemas.InvoiceRead])
async def list_invoices(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:invoice:list")),
) -> list[schemas.InvoiceRead]:
    return [schemas.InvoiceRead.model_validate(i) for i in await InvoiceService.list(db, company_id=company_id)]


@router.get("/invoices/{invoice_id}", response_model=schemas.InvoiceRead)
async def get_invoice(
    invoice_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:invoice:read")),
) -> schemas.InvoiceRead:
    return schemas.InvoiceRead.model_validate(await InvoiceService.get(db, company_id=company_id, invoice_id=invoice_id))


@router.post("/invoices/{invoice_id}/post", response_model=schemas.InvoiceRead)
async def post_invoice(
    invoice_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("accounting:invoice:post")),
) -> schemas.InvoiceRead:
    async def _command() -> schemas.InvoiceRead:
        invoice = await InvoiceService.post(db, company_id=company_id, invoice_id=invoice_id, actor_id=actor.id)
        return schemas.InvoiceRead.model_validate(invoice)

    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint=f"POST /accounting/invoices/{invoice_id}/post",
        payload_dict={"invoice_id": invoice_id},
        domain="accounting",
        success_status_code=200,
        command=_command,
    )


@router.post("/invoices/{invoice_id}/cancel", response_model=schemas.InvoiceRead)
async def cancel_invoice(
    invoice_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("accounting:invoice:cancel")),
) -> schemas.InvoiceRead:
    async def _command() -> schemas.InvoiceRead:
        invoice = await InvoiceService.cancel(db, company_id=company_id, invoice_id=invoice_id, actor_id=actor.id)
        return schemas.InvoiceRead.model_validate(invoice)

    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint=f"POST /accounting/invoices/{invoice_id}/cancel",
        payload_dict={"invoice_id": invoice_id},
        domain="accounting",
        success_status_code=200,
        command=_command,
    )


# ---------------------------------------------------------------------------
# Notas de Crédito y Débito
# ---------------------------------------------------------------------------
@router.post("/credit-debit-notes", response_model=schemas.CreditDebitNoteRead, status_code=201)
async def create_credit_debit_note(
    payload: schemas.CreditDebitNoteCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("accounting:credit_debit_note:create")),
) -> schemas.CreditDebitNoteRead:
    async def _command() -> schemas.CreditDebitNoteRead:
        note = await CreditDebitNoteService.create_draft(db, company_id=company_id, payload=payload, created_by=actor.id)
        return schemas.CreditDebitNoteRead.model_validate(note)

    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint="POST /accounting/credit-debit-notes",
        payload_dict=payload.model_dump(mode="json"),
        domain="accounting",
        success_status_code=201,
        command=_command,
    )


@router.get("/credit-debit-notes", response_model=list[schemas.CreditDebitNoteRead])
async def list_credit_debit_notes(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:credit_debit_note:list")),
) -> list[schemas.CreditDebitNoteRead]:
    return [
        schemas.CreditDebitNoteRead.model_validate(n)
        for n in await CreditDebitNoteService.list(db, company_id=company_id)
    ]


@router.get("/credit-debit-notes/{note_id}", response_model=schemas.CreditDebitNoteRead)
async def get_credit_debit_note(
    note_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:credit_debit_note:read")),
) -> schemas.CreditDebitNoteRead:
    return schemas.CreditDebitNoteRead.model_validate(
        await CreditDebitNoteService.get(db, company_id=company_id, note_id=note_id)
    )


@router.post("/credit-debit-notes/{note_id}/post", response_model=schemas.CreditDebitNoteRead)
async def post_credit_debit_note(
    note_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("accounting:credit_debit_note:post")),
) -> schemas.CreditDebitNoteRead:
    async def _command() -> schemas.CreditDebitNoteRead:
        note = await CreditDebitNoteService.post(db, company_id=company_id, note_id=note_id, actor_id=actor.id)
        return schemas.CreditDebitNoteRead.model_validate(note)

    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint=f"POST /accounting/credit-debit-notes/{note_id}/post",
        payload_dict={"note_id": note_id},
        domain="accounting",
        success_status_code=200,
        command=_command,
    )


@router.post("/credit-debit-notes/{note_id}/cancel", response_model=schemas.CreditDebitNoteRead)
async def cancel_credit_debit_note(
    note_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("accounting:credit_debit_note:cancel")),
) -> schemas.CreditDebitNoteRead:
    async def _command() -> schemas.CreditDebitNoteRead:
        note = await CreditDebitNoteService.cancel(db, company_id=company_id, note_id=note_id, actor_id=actor.id)
        return schemas.CreditDebitNoteRead.model_validate(note)

    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint=f"POST /accounting/credit-debit-notes/{note_id}/cancel",
        payload_dict={"note_id": note_id},
        domain="accounting",
        success_status_code=200,
        command=_command,
    )


# ---------------------------------------------------------------------------
# Gestión de Pagos y Cobros
# ---------------------------------------------------------------------------
@router.post("/payments", response_model=schemas.PaymentRead, status_code=201)
async def create_payment(
    payload: schemas.PaymentCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("accounting:payment:create")),
) -> schemas.PaymentRead:
    async def _command() -> schemas.PaymentRead:
        payment = await PaymentService.create_draft(db, company_id=company_id, payload=payload, created_by=actor.id)
        return schemas.PaymentRead.model_validate(payment)

    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint="POST /accounting/payments",
        payload_dict=payload.model_dump(mode="json"),
        domain="accounting",
        success_status_code=201,
        command=_command,
    )


@router.get("/payments", response_model=list[schemas.PaymentRead])
async def list_payments(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:payment:list")),
) -> list[schemas.PaymentRead]:
    return [schemas.PaymentRead.model_validate(p) for p in await PaymentService.list(db, company_id=company_id)]


@router.get("/payments/{payment_id}", response_model=schemas.PaymentRead)
async def get_payment(
    payment_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:payment:read")),
) -> schemas.PaymentRead:
    return schemas.PaymentRead.model_validate(await PaymentService.get(db, company_id=company_id, payment_id=payment_id))


@router.post("/payments/{payment_id}/post", response_model=schemas.PaymentRead)
async def post_payment(
    payment_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("accounting:payment:post")),
) -> schemas.PaymentRead:
    async def _command() -> schemas.PaymentRead:
        payment = await PaymentService.post(db, company_id=company_id, payment_id=payment_id, actor_id=actor.id)
        return schemas.PaymentRead.model_validate(payment)

    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint=f"POST /accounting/payments/{payment_id}/post",
        payload_dict={"payment_id": payment_id},
        domain="accounting",
        success_status_code=200,
        command=_command,
    )


@router.post("/payments/{payment_id}/cancel", response_model=schemas.PaymentRead)
async def cancel_payment(
    payment_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("accounting:payment:cancel")),
) -> schemas.PaymentRead:
    async def _command() -> schemas.PaymentRead:
        payment = await PaymentService.cancel(db, company_id=company_id, payment_id=payment_id, actor_id=actor.id)
        return schemas.PaymentRead.model_validate(payment)

    return await IdempotencyService.run_command(
        db,
        company_id=company_id,
        idempotency_key=idempotency_key,
        endpoint=f"POST /accounting/payments/{payment_id}/cancel",
        payload_dict={"payment_id": payment_id},
        domain="accounting",
        success_status_code=200,
        command=_command,
    )


# ---------------------------------------------------------------------------
# Motor de Contención Financiera
# ---------------------------------------------------------------------------
@router.get("/credit-status/{contact_id}", response_model=schemas.CreditStatusRead)
async def get_credit_status(
    contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("accounting:credit_status:read")),
) -> schemas.CreditStatusRead:
    return await CreditControlService.get_credit_status(db, company_id=company_id, contact_id=contact_id)
