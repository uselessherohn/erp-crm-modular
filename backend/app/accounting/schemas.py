from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AccountTypeEnum(str, Enum):
    receivable = "receivable"
    payable = "payable"
    income = "income"
    tax = "tax"
    cash_bank = "cash_bank"
    adjustment = "adjustment"


class DocumentTypeEnum(str, Enum):
    sales_invoice = "sales_invoice"
    purchase_invoice = "purchase_invoice"
    sales_credit_note = "sales_credit_note"
    sales_debit_note = "sales_debit_note"
    purchase_credit_note = "purchase_credit_note"
    purchase_debit_note = "purchase_debit_note"
    payment_received = "payment_received"
    payment_made = "payment_made"


class DirectionEnum(str, Enum):
    sale = "sale"
    purchase = "purchase"


class InvoiceStatusEnum(str, Enum):
    draft = "draft"
    posted = "posted"
    partially_paid = "partially_paid"
    paid = "paid"
    cancelled = "cancelled"


class NoteTypeEnum(str, Enum):
    credit = "credit"
    debit = "debit"


class NoteStatusEnum(str, Enum):
    draft = "draft"
    posted = "posted"
    cancelled = "cancelled"


class PaymentMethodEnum(str, Enum):
    cash = "cash"
    bank_transfer = "bank_transfer"
    card = "card"
    check = "check"
    other = "other"


class PaymentStatusEnum(str, Enum):
    draft = "draft"
    posted = "posted"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# Plan de Cuentas
# ---------------------------------------------------------------------------


class AccountCreate(BaseModel):
    code: str = Field(..., max_length=30)
    name: str = Field(..., max_length=200)
    account_type: AccountTypeEnum
    is_default: bool = False


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    code: str
    name: str
    account_type: AccountTypeEnum
    is_default: bool
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Mapeo documento → cuentas
# ---------------------------------------------------------------------------


class DocumentAccountMappingCreate(BaseModel):
    document_type: DocumentTypeEnum
    role: AccountTypeEnum
    account_id: int


class DocumentAccountMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    document_type: DocumentTypeEnum
    role: AccountTypeEnum
    account_id: int


# ---------------------------------------------------------------------------
# Motor de Asientos (solo lectura — se generan vía JournalService, nunca
# vía endpoint directo de creación, spec 7.1)
# ---------------------------------------------------------------------------


class JournalLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    debit: Decimal
    credit: Decimal
    description: str | None


class JournalEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    entry_date: date
    document_type: DocumentTypeEnum
    document_id: int
    description: str
    total_debit: Decimal
    total_credit: Decimal
    created_at: datetime
    lines: list[JournalLineRead]


# ---------------------------------------------------------------------------
# Gestión de Impuestos
# ---------------------------------------------------------------------------


class TaxRateCreate(BaseModel):
    name: str = Field(..., max_length=100)
    rate: Decimal = Field(..., ge=0, le=100)
    is_default: bool = False


class TaxRateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    name: str
    rate: Decimal
    is_default: bool
    is_active: bool


# ---------------------------------------------------------------------------
# Facturación de Venta y Proveedor
# ---------------------------------------------------------------------------


class InvoiceLineCreate(BaseModel):
    description: str = Field(..., max_length=300)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(..., ge=0)
    tax_rate_id: int | None = None


class InvoiceCreate(BaseModel):
    direction: DirectionEnum
    contact_id: int
    currency_code: str = Field(default="HNL", max_length=3)
    issue_date: date
    due_date: date | None = None
    source_document_type: str | None = Field(None, max_length=30)
    source_document_id: int | None = None
    lines: list[InvoiceLineCreate] = Field(..., min_length=1)


class InvoiceLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate_id: int | None
    line_subtotal: Decimal
    line_tax: Decimal
    line_total: Decimal


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    number: str
    direction: DirectionEnum
    contact_id: int
    status: InvoiceStatusEnum
    currency_code: str
    issue_date: date
    due_date: date | None
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    balance_due: Decimal
    source_document_type: str | None
    source_document_id: int | None
    journal_entry_id: int | None
    version: int
    created_at: datetime
    lines: list[InvoiceLineRead]


# ---------------------------------------------------------------------------
# Notas de Crédito y Débito
# ---------------------------------------------------------------------------


class CreditDebitNoteLineCreate(BaseModel):
    description: str = Field(..., max_length=300)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(..., ge=0)
    tax_rate_id: int | None = None


class CreditDebitNoteCreate(BaseModel):
    note_type: NoteTypeEnum
    direction: DirectionEnum
    contact_id: int
    invoice_id: int | None = None
    reason: str = Field(..., max_length=500)
    issue_date: date
    lines: list[CreditDebitNoteLineCreate] = Field(..., min_length=1)


class CreditDebitNoteLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate_id: int | None
    line_subtotal: Decimal
    line_tax: Decimal
    line_total: Decimal


class CreditDebitNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    number: str
    note_type: NoteTypeEnum
    direction: DirectionEnum
    contact_id: int
    invoice_id: int | None
    reason: str
    status: NoteStatusEnum
    issue_date: date
    subtotal: Decimal
    tax_amount: Decimal
    total: Decimal
    journal_entry_id: int | None
    version: int
    created_at: datetime
    lines: list[CreditDebitNoteLineRead]


# ---------------------------------------------------------------------------
# Gestión de Pagos y Cobros
# ---------------------------------------------------------------------------


class PaymentAllocationCreate(BaseModel):
    invoice_id: int
    amount_applied: Decimal = Field(..., gt=0)


class PaymentCreate(BaseModel):
    direction: DirectionEnum
    contact_id: int
    payment_date: date
    method: PaymentMethodEnum
    amount: Decimal = Field(..., gt=0)
    reference: str | None = Field(None, max_length=200)
    allocations: list[PaymentAllocationCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def allocations_do_not_exceed_amount(self) -> "PaymentCreate":
        total_allocated = sum((a.amount_applied for a in self.allocations), Decimal("0"))
        if total_allocated > self.amount:
            raise ValueError("La suma de las asignaciones no puede superar el monto del pago")
        return self


class PaymentAllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_id: int
    amount_applied: Decimal


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    number: str
    direction: DirectionEnum
    contact_id: int
    payment_date: date
    method: PaymentMethodEnum
    amount: Decimal
    reference: str | None
    status: PaymentStatusEnum
    journal_entry_id: int | None
    version: int
    created_at: datetime
    allocations: list[PaymentAllocationRead]


# ---------------------------------------------------------------------------
# Motor de Contención Financiera — solo lectura (spec 8.1, DED-12)
# ---------------------------------------------------------------------------


class CreditStatusRead(BaseModel):
    """Resultado de la evaluación de contención financiera para un
    contacto — usado por `sales` (Fase 2, hook en confirm()) y expuesto
    también como endpoint de consulta directa."""

    contact_id: int
    is_blocked: bool
    has_overdue_invoices: bool
    credit_limit: Decimal | None
    outstanding_balance: Decimal
    credit_exceeded: bool
