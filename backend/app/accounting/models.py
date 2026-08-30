"""
Módulo 6 — accounting (spec sección 8.1, subset [core] — retagueado en
v10.1, ver changelog): Plan de Cuentas mínimo, Motor de Asientos (spec 7.1),
Facturación de Venta y Proveedor, Gestión de Impuestos, Gestión de Pagos y
Cobros, Notas de Crédito/Débito, Motor de Contención Financiera.

[extendido] fuera de este cierre: Plan de Cuentas completo (jerárquico,
cuentas analíticas, centros de costo), Libro Diario y Mayor (UI de consulta
— el motor de asientos SÍ escribe los asientos igual, esto es solo la
navegación), Conciliación Bancaria, Activos Fijos, Presupuestos, Tipos de
Cambio y Revaluación Multi-moneda.

Convenciones aplicadas (spec sección 5, igual que purchasing/sales):
- Documento transaccional: estados explícitos, NO soft delete.
- Dinero: Numeric(18,2), nunca float. currency_code en el header donde
  aplica multi-moneda de un documento (no en journal_entries/lines, que
  asumen la moneda funcional de la compañía — Tipos de Cambio/Revaluación
  es [extendido]).
- Numeración atómica vía DocumentNumberingService (core) — mismo servicio
  que ya usan purchasing y sales, sin reinventar.
- version: bloqueo optimista en documentos con mutación concurrente
  esperada (Invoice.balance_due se reduce con cada pago aplicado; Payment
  puede recibir/perder asignaciones).

DECISIONES DEDUCIBLE/AMBIGUO de este módulo (ver STATE.md sección 4 para el
registro formal — resumen acá para que el modelo sea legible sin cruzar
documentos):

- DED-09: Plan de Cuentas mínimo modelado como catálogo plano de "roles"
  fijos (receivable/payable/income/tax/cash_bank/adjustment), NO jerárquico
  — el plan completo con cuentas analíticas/centros de costo es
  [extendido, requiere Administrativo] y no se construye acá. Una compañía
  puede tener varias cuentas del mismo rol (ej. dos bancos); `is_default`
  marca cuál usa el mapeo de documentos si no hay override explícito.
- DED-10: "Mapeo documento → cuentas contables" (spec 7.1) modelado como
  tabla explícita `document_account_mappings(company_id, document_type,
  role, account_id)`. Un solo documento puede necesitar más de un rol (ej.
  factura de venta: receivable + income + tax en la misma transacción) —
  por eso "role" identifica la función dentro de ESE tipo de documento, no
  un tipo de cuenta compartido genéricamente.
- DED-11: El plan mínimo (spec 8.1) no incluye cuentas de "gastos" ni
  "inventario" (solo cuentas por cobrar/pagar, ingresos, impuestos,
  caja/banco, ajuste). Factura de proveedor (`purchase_invoice`) usa
  `adjustment` como contrapartida de `payable` en el mínimo — se
  reconfigura sin tocar el motor el día que el cliente compre Plan de
  Cuentas completo. Documentado, no asumido silenciosamente.
- DED-12/AMBIGUO: Motor de Contención Financiera — "deuda vencida" definida
  como factura de venta (`invoices.direction='sale'`) con `due_date` en el
  pasado y `balance_due > 0`; "crédito excedido" definido como suma de
  `balance_due` de facturas de venta `posted`/`partially_paid` mayor que
  `contacts.credit_limit` (si no es NULL). El cálculo de crédito excedido
  NO incluye órdenes de venta confirmadas aún no facturadas — sin
  confirmar con Roberto si debería. Ver `credit_limit` agregado a
  `Contact` (hallazgo retroactivo, mismo patrón que `reserved_quantity`
  retroactivo a `inventory` desde `sales`).
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums Python (solo para tipado/legibilidad — la validación real vive en
# los CHECK constraints de String, mismo patrón que purchasing/sales, NO
# tipo ENUM nativo de Postgres, para no pagar el costo de ALTER TYPE en
# migraciones futuras que agreguen un valor).
# ---------------------------------------------------------------------------


class AccountTypeEnum(str, enum.Enum):
    receivable = "receivable"      # cuentas por cobrar
    payable = "payable"            # cuentas por pagar
    income = "income"              # ingresos
    tax = "tax"                    # impuestos
    cash_bank = "cash_bank"        # caja/banco básico
    adjustment = "adjustment"      # cuenta de ajuste


ACCOUNT_TYPES = tuple(t.value for t in AccountTypeEnum)


class DocumentTypeEnum(str, enum.Enum):
    sales_invoice = "sales_invoice"
    purchase_invoice = "purchase_invoice"
    sales_credit_note = "sales_credit_note"
    sales_debit_note = "sales_debit_note"
    purchase_credit_note = "purchase_credit_note"
    purchase_debit_note = "purchase_debit_note"
    payment_received = "payment_received"
    payment_made = "payment_made"


DOCUMENT_TYPES = tuple(t.value for t in DocumentTypeEnum)


class DirectionEnum(str, enum.Enum):
    sale = "sale"
    purchase = "purchase"


class InvoiceStatusEnum(str, enum.Enum):
    draft = "draft"
    posted = "posted"
    partially_paid = "partially_paid"
    paid = "paid"
    cancelled = "cancelled"


class NoteTypeEnum(str, enum.Enum):
    credit = "credit"
    debit = "debit"


class NoteStatusEnum(str, enum.Enum):
    draft = "draft"
    posted = "posted"
    cancelled = "cancelled"


class PaymentMethodEnum(str, enum.Enum):
    cash = "cash"
    bank_transfer = "bank_transfer"
    card = "card"
    check = "check"
    other = "other"


class PaymentStatusEnum(str, enum.Enum):
    draft = "draft"
    posted = "posted"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# Plan de Cuentas mínimo
# ---------------------------------------------------------------------------


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)

    is_default: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(f"account_type IN {ACCOUNT_TYPES}", name="ck_accounts_account_type"),
        UniqueConstraint("company_id", "code", name="uq_accounts_company_code"),
    )


# ---------------------------------------------------------------------------
# Mapeo documento → cuentas (spec 7.1) — DED-10
# ---------------------------------------------------------------------------


class DocumentAccountMapping(Base):
    __tablename__ = "document_account_mappings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(f"document_type IN {DOCUMENT_TYPES}", name="ck_doc_account_mappings_document_type"),
        CheckConstraint(f"role IN {ACCOUNT_TYPES}", name="ck_doc_account_mappings_role"),
        UniqueConstraint("company_id", "document_type", "role", name="uq_doc_account_mappings_company_type_role"),
    )


# ---------------------------------------------------------------------------
# Motor de Asientos (spec 7.1) — append-only, balance forzado a nivel DB
# ---------------------------------------------------------------------------


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Referencia polimórfica al documento origen (invoices/credit_debit_notes/
    # payments) — sin FK porque cruza tablas; la integridad la garantiza el
    # servicio que crea entry+documento origen en la misma transacción
    # (Estrategia de diseño transaccional, ver services.py Fase 2).
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)

    total_debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(f"document_type IN {DOCUMENT_TYPES}", name="ck_journal_entries_document_type"),
        # Invariante de balance (spec 7.1: "todo asiento debe balancear")
        # forzado a nivel de base, no solo en el servicio — defensa en
        # profundidad, mismo criterio que reserved_quantity<=quantity en
        # inventory.
        CheckConstraint("total_debit = total_credit", name="ck_journal_entries_balanced"),
        CheckConstraint("total_debit >= 0 AND total_credit >= 0", name="ck_journal_entries_nonneg"),
    )

    lines: Mapped[list["JournalLine"]] = relationship(back_populates="journal_entry", lazy="selectin")


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    journal_entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"), nullable=False, index=True)

    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_journal_lines_nonneg"),
        # Una línea es débito O crédito, nunca ambas ni ninguna.
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="ck_journal_lines_debit_xor_credit",
        ),
    )

    journal_entry: Mapped["JournalEntry"] = relationship(back_populates="lines", lazy="selectin")


# ---------------------------------------------------------------------------
# Gestión de Impuestos
# ---------------------------------------------------------------------------


class TaxRate(Base):
    __tablename__ = "tax_rates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Porcentaje, ej. 15.00 = ISV 15% (Honduras) — NO fracción decimal, para
    # que la UI muestre el número tal cual sin conversión.
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_default: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("rate >= 0 AND rate <= 100", name="ck_tax_rates_rate_range"),
        UniqueConstraint("company_id", "name", name="uq_tax_rates_company_name"),
    )


# ---------------------------------------------------------------------------
# Facturación de Venta y Proveedor
# ---------------------------------------------------------------------------


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    number: Mapped[str] = mapped_column(String(50), nullable=False)  # FV-2026-000001 / FC-2026-000001
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # sale | purchase
    contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")

    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    balance_due: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    # Documento origen opcional (sales_order/purchase_order) — sin FK, cruza
    # módulos, mismo patrón que journal_entries.document_id.
    source_document_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    journal_entry_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id"), nullable=True
    )

    # version: bloqueo optimista — balance_due se reduce con cada pago
    # aplicado (PaymentAllocation), mutación concurrente esperada igual
    # que quantity_received en purchasing.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("direction IN ('sale', 'purchase')", name="ck_invoices_direction"),
        CheckConstraint(
            "status IN ('draft', 'posted', 'partially_paid', 'paid', 'cancelled')",
            name="ck_invoices_status",
        ),
        CheckConstraint("subtotal >= 0 AND tax_amount >= 0 AND total >= 0", name="ck_invoices_amounts_nonneg"),
        CheckConstraint("balance_due >= 0 AND balance_due <= total", name="ck_invoices_balance_due_range"),
        UniqueConstraint("company_id", "number", name="uq_invoices_company_number"),
    )

    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", lazy="selectin", cascade="all, delete-orphan"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    invoice_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )

    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, server_default="1")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_rate_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tax_rates.id"), nullable=True)

    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_invoice_lines_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_lines_unit_price_nonneg"),
        CheckConstraint(
            "line_subtotal >= 0 AND line_tax >= 0 AND line_total >= 0", name="ck_invoice_lines_amounts_nonneg"
        ),
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="lines", lazy="selectin")


# ---------------------------------------------------------------------------
# Notas de Crédito y Débito
# ---------------------------------------------------------------------------


class CreditDebitNote(Base):
    __tablename__ = "credit_debit_notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    number: Mapped[str] = mapped_column(String(50), nullable=False)  # NC-2026-000001 / ND-2026-000001
    note_type: Mapped[str] = mapped_column(String(10), nullable=False)  # credit | debit
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # sale | purchase
    contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    # Factura que corrige — opcional: una nota de débito puede existir sin
    # factura origen (ej. cargo adicional), spec no exige el vínculo en
    # todos los casos.
    invoice_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("invoices.id"), nullable=True)

    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)

    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")

    journal_entry_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("note_type IN ('credit', 'debit')", name="ck_credit_debit_notes_note_type"),
        CheckConstraint("direction IN ('sale', 'purchase')", name="ck_credit_debit_notes_direction"),
        CheckConstraint("status IN ('draft', 'posted', 'cancelled')", name="ck_credit_debit_notes_status"),
        CheckConstraint("subtotal >= 0 AND tax_amount >= 0 AND total >= 0", name="ck_credit_debit_notes_amounts_nonneg"),
        UniqueConstraint("company_id", "number", name="uq_credit_debit_notes_company_number"),
    )

    lines: Mapped[list["CreditDebitNoteLine"]] = relationship(
        back_populates="note", lazy="selectin", cascade="all, delete-orphan"
    )


class CreditDebitNoteLine(Base):
    __tablename__ = "credit_debit_note_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    note_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("credit_debit_notes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, server_default="1")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    tax_rate_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tax_rates.id"), nullable=True)

    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    line_tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, server_default="0")
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_cdn_lines_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_cdn_lines_unit_price_nonneg"),
        CheckConstraint(
            "line_subtotal >= 0 AND line_tax >= 0 AND line_total >= 0", name="ck_cdn_lines_amounts_nonneg"
        ),
    )

    note: Mapped["CreditDebitNote"] = relationship(back_populates="lines", lazy="selectin")


# ---------------------------------------------------------------------------
# Gestión de Pagos y Cobros
# ---------------------------------------------------------------------------


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    number: Mapped[str] = mapped_column(String(50), nullable=False)  # REC-2026-000001 / PAG-2026-000001
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # sale (cobro) | purchase (pago)
    contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)

    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    journal_entry_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("journal_entries.id"), nullable=True
    )
    # version: bloqueo optimista — un pago puede recibir/perder asignaciones
    # (PaymentAllocation) concurrentemente.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("direction IN ('sale', 'purchase')", name="ck_payments_direction"),
        CheckConstraint(
            "method IN ('cash', 'bank_transfer', 'card', 'check', 'other')", name="ck_payments_method"
        ),
        CheckConstraint("status IN ('draft', 'posted', 'cancelled')", name="ck_payments_status"),
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        UniqueConstraint("company_id", "number", name="uq_payments_company_number"),
    )

    allocations: Mapped[list["PaymentAllocation"]] = relationship(
        back_populates="payment", lazy="selectin", cascade="all, delete-orphan"
    )


class PaymentAllocation(Base):
    """Un pago puede aplicarse a una o varias facturas (spec: Gestión de
    Pagos y Cobros [core] — pago parcial o de múltiples facturas)."""

    __tablename__ = "payment_allocations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    payment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("invoices.id"), nullable=False, index=True)

    amount_applied: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount_applied > 0", name="ck_payment_allocations_amount_positive"),
    )

    payment: Mapped["Payment"] = relationship(back_populates="allocations", lazy="selectin")
