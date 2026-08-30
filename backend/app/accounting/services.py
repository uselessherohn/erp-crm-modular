"""
Servicios de accounting — Fase 2.

Motor de Asientos (spec 7.1): `JournalService.post_entry()` es genérico —
resuelve cuentas vía `DocumentAccountMapping` (DED-10), nunca hardcodea un
account_id. Cada servicio de documento (`InvoiceService`,
`CreditDebitNoteService`, `PaymentService`) construye la lista de
(role, side, amount) según su propia semántica contable y delega el
balanceo/persistencia a `JournalService`.

Máquinas de estado (todas con SELECT ... FOR UPDATE, mismo patrón que
purchasing/sales):
- Invoice: draft -> posted (genera asiento) -> partially_paid -> paid
  (ambas alcanzadas solo por PaymentService.post, nunca por comando
  directo) / draft -> cancelled. DEDUCIBLE: una factura `posted` NO se
  cancela directo — se revierte con una nota de crédito/débito (spec no
  lo dice explícito, pero permitir cancelar una factura ya asentada
  dejaría el asiento contable huérfano; mismo criterio que
  purchasing/sales con documentos ya físicos).
- CreditDebitNote: draft -> posted (genera asiento) / draft -> cancelled.
- Payment: draft -> posted (aplica allocations sobre facturas + genera
  asiento) / draft -> cancelled.

Motor de Contención Financiera (DED-12): `CreditControlService`, sin
estado propio — lee `Invoice`/`Contact.credit_limit` en caliente.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting import models, schemas
from app.contacts.services import ContactService
from app.core.services import AuditService, DocumentNumberingService
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError

TWO_PLACES = Decimal("0.01")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES)


# ---------------------------------------------------------------------------
# Plan de Cuentas
# ---------------------------------------------------------------------------


class AccountService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.AccountCreate) -> models.Account:
        if payload.is_default:
            await AccountService._unset_previous_default(
                db, company_id=company_id, account_type=payload.account_type.value
            )
        account = models.Account(
            company_id=company_id,
            code=payload.code,
            name=payload.name,
            account_type=payload.account_type.value,
            is_default=payload.is_default,
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
        return account

    @staticmethod
    async def _unset_previous_default(db: AsyncSession, *, company_id: int, account_type: str) -> None:
        result = await db.execute(
            select(models.Account).where(
                models.Account.company_id == company_id,
                models.Account.account_type == account_type,
                models.Account.is_default.is_(True),
            )
        )
        for existing in result.scalars().all():
            existing.is_default = False

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, account_id: int) -> models.Account:
        result = await db.execute(
            select(models.Account).where(models.Account.company_id == company_id, models.Account.id == account_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise NotFoundError(f"Cuenta contable {account_id} no encontrada")
        return account

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Account]:
        result = await db.execute(select(models.Account).where(models.Account.company_id == company_id))
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Mapeo documento → cuentas (DED-10)
# ---------------------------------------------------------------------------


class DocumentAccountMappingService:
    @staticmethod
    async def upsert(
        db: AsyncSession, *, company_id: int, payload: schemas.DocumentAccountMappingCreate
    ) -> models.DocumentAccountMapping:
        account = await AccountService.get(db, company_id=company_id, account_id=payload.account_id)
        if account.account_type != payload.role.value:
            raise ValidationError(
                f"La cuenta '{account.name}' es de tipo '{account.account_type}', "
                f"no puede usarse para el rol '{payload.role.value}'"
            )
        result = await db.execute(
            select(models.DocumentAccountMapping).where(
                models.DocumentAccountMapping.company_id == company_id,
                models.DocumentAccountMapping.document_type == payload.document_type.value,
                models.DocumentAccountMapping.role == payload.role.value,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.account_id = payload.account_id
            mapping = existing
        else:
            mapping = models.DocumentAccountMapping(
                company_id=company_id,
                document_type=payload.document_type.value,
                role=payload.role.value,
                account_id=payload.account_id,
            )
            db.add(mapping)
        await db.commit()
        await db.refresh(mapping)
        return mapping

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.DocumentAccountMapping]:
        result = await db.execute(
            select(models.DocumentAccountMapping).where(models.DocumentAccountMapping.company_id == company_id)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Motor de Asientos
# ---------------------------------------------------------------------------


class JournalService:
    @staticmethod
    async def _resolve_account_id(db: AsyncSession, *, company_id: int, document_type: str, role: str) -> int:
        result = await db.execute(
            select(models.DocumentAccountMapping).where(
                models.DocumentAccountMapping.company_id == company_id,
                models.DocumentAccountMapping.document_type == document_type,
                models.DocumentAccountMapping.role == role,
            )
        )
        mapping = result.scalar_one_or_none()
        if mapping is None:
            raise ValidationError(
                f"No hay cuenta configurada para el rol '{role}' del documento '{document_type}' "
                "— configure document_account_mappings antes de contabilizar"
            )
        return mapping.account_id

    @staticmethod
    async def post_entry(
        db: AsyncSession,
        *,
        company_id: int,
        entry_date: date,
        document_type: str,
        document_id: int,
        description: str,
        lines: list[tuple[str, str, Decimal]],  # (role, "debit"|"credit", amount)
        created_by: int | None,
    ) -> models.JournalEntry:
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        resolved: list[tuple[int, Decimal, Decimal]] = []
        for role, side, amount in lines:
            if amount <= 0:
                # Líneas de monto cero (ej. tax_amount=0 en una factura sin
                # impuesto) se omiten — no tiene sentido una línea $0 en el
                # asiento, y rompería el CHECK debit_xor_credit.
                continue
            account_id = await JournalService._resolve_account_id(
                db, company_id=company_id, document_type=document_type, role=role
            )
            if side == "debit":
                resolved.append((account_id, amount, Decimal("0")))
                total_debit += amount
            elif side == "credit":
                resolved.append((account_id, Decimal("0"), amount))
                total_credit += amount
            else:
                raise ValidationError(f"Lado de asiento inválido: '{side}' (debe ser 'debit' o 'credit')")

        if total_debit != total_credit:
            raise ValidationError(
                f"Asiento desbalanceado para {document_type} #{document_id}: "
                f"debe={total_debit} haber={total_credit}"
            )
        if not resolved:
            raise ValidationError(f"No hay líneas de asiento para {document_type} #{document_id}")

        entry = models.JournalEntry(
            company_id=company_id,
            entry_date=entry_date,
            document_type=document_type,
            document_id=document_id,
            description=description,
            total_debit=total_debit,
            total_credit=total_credit,
            created_by=created_by,
        )
        db.add(entry)
        await db.flush()
        for account_id, debit, credit in resolved:
            db.add(
                models.JournalLine(
                    company_id=company_id,
                    journal_entry_id=entry.id,
                    account_id=account_id,
                    debit=debit,
                    credit=credit,
                )
            )
        await db.flush()
        return entry


# ---------------------------------------------------------------------------
# Gestión de Impuestos
# ---------------------------------------------------------------------------


class TaxRateService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.TaxRateCreate) -> models.TaxRate:
        if payload.is_default:
            result = await db.execute(
                select(models.TaxRate).where(
                    models.TaxRate.company_id == company_id, models.TaxRate.is_default.is_(True)
                )
            )
            for existing in result.scalars().all():
                existing.is_default = False
        tax_rate = models.TaxRate(
            company_id=company_id, name=payload.name, rate=payload.rate, is_default=payload.is_default
        )
        db.add(tax_rate)
        await db.commit()
        await db.refresh(tax_rate)
        return tax_rate

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, tax_rate_id: int) -> models.TaxRate:
        result = await db.execute(
            select(models.TaxRate).where(
                models.TaxRate.company_id == company_id, models.TaxRate.id == tax_rate_id
            )
        )
        tax_rate = result.scalar_one_or_none()
        if tax_rate is None:
            raise NotFoundError(f"Tasa de impuesto {tax_rate_id} no encontrada")
        return tax_rate

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.TaxRate]:
        result = await db.execute(select(models.TaxRate).where(models.TaxRate.company_id == company_id))
        return list(result.scalars().all())


async def _compute_lines(
    db: AsyncSession, *, company_id: int, raw_lines: list
) -> tuple[Decimal, Decimal, Decimal, list[dict]]:
    """Común a Invoice y CreditDebitNote — calcula subtotal/tax/total por
    línea y agregado. Devuelve (subtotal, tax_amount, total, line_dicts)."""
    subtotal = Decimal("0")
    tax_amount = Decimal("0")
    line_dicts = []
    for line in raw_lines:
        rate = Decimal("0")
        if line.tax_rate_id is not None:
            tax_rate = await TaxRateService.get(db, company_id=company_id, tax_rate_id=line.tax_rate_id)
            rate = tax_rate.rate
        line_subtotal = _round2(line.quantity * line.unit_price)
        line_tax = _round2(line_subtotal * rate / Decimal("100"))
        line_total = line_subtotal + line_tax
        subtotal += line_subtotal
        tax_amount += line_tax
        line_dicts.append(
            {
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "tax_rate_id": line.tax_rate_id,
                "line_subtotal": line_subtotal,
                "line_tax": line_tax,
                "line_total": line_total,
            }
        )
    total = subtotal + tax_amount
    return subtotal, tax_amount, total, line_dicts


# ---------------------------------------------------------------------------
# Facturación de Venta y Proveedor
# ---------------------------------------------------------------------------


class InvoiceService:
    @staticmethod
    async def create_draft(
        db: AsyncSession, *, company_id: int, payload: schemas.InvoiceCreate, created_by: int | None
    ) -> models.Invoice:
        contact = await ContactService.get_contact(db, company_id=company_id, contact_id=payload.contact_id)
        if payload.direction.value == "sale" and not contact.is_customer:
            raise ValidationError(f"El contacto '{contact.name}' no tiene el flag is_customer activo")
        if payload.direction.value == "purchase" and not contact.is_vendor:
            raise ValidationError(f"El contacto '{contact.name}' no tiene el flag is_vendor activo")

        subtotal, tax_amount, total, line_dicts = await _compute_lines(
            db, company_id=company_id, raw_lines=payload.lines
        )

        prefix = "FV" if payload.direction.value == "sale" else "FC"
        number = await DocumentNumberingService.next_number(
            db,
            company_id=company_id,
            doc_type=f"invoice_{payload.direction.value}",
            prefix=prefix,
            year=datetime.now(timezone.utc).year,
        )
        invoice = models.Invoice(
            company_id=company_id,
            number=number,
            direction=payload.direction.value,
            contact_id=payload.contact_id,
            currency_code=payload.currency_code,
            issue_date=payload.issue_date,
            due_date=payload.due_date,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total=total,
            balance_due=total,
            source_document_type=payload.source_document_type,
            source_document_id=payload.source_document_id,
            created_by=created_by,
        )
        db.add(invoice)
        await db.flush()
        for ld in line_dicts:
            db.add(models.InvoiceLine(company_id=company_id, invoice_id=invoice.id, **ld))
        await AuditService.log_event(
            db, company_id=company_id, event="invoice.created", entity_type="invoice", entity_id=invoice.id,
            user_id=created_by,
        )
        await db.commit()
        await db.refresh(invoice)
        return invoice

    @staticmethod
    async def _get_locked(db: AsyncSession, *, company_id: int, invoice_id: int) -> models.Invoice:
        result = await db.execute(
            select(models.Invoice)
            .where(models.Invoice.company_id == company_id, models.Invoice.id == invoice_id)
            .with_for_update()
        )
        invoice = result.scalar_one_or_none()
        if invoice is None:
            raise NotFoundError(f"Factura {invoice_id} no encontrada")
        return invoice

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, invoice_id: int) -> models.Invoice:
        result = await db.execute(
            select(models.Invoice).where(models.Invoice.company_id == company_id, models.Invoice.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()
        if invoice is None:
            raise NotFoundError(f"Factura {invoice_id} no encontrada")
        return invoice

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Invoice]:
        result = await db.execute(select(models.Invoice).where(models.Invoice.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def post(db: AsyncSession, *, company_id: int, invoice_id: int, actor_id: int | None) -> models.Invoice:
        invoice = await InvoiceService._get_locked(db, company_id=company_id, invoice_id=invoice_id)
        if invoice.status != "draft":
            raise ConflictError(f"Solo se puede contabilizar una factura en 'draft' (actual: '{invoice.status}')")

        if invoice.direction == "sale":
            document_type = "sales_invoice"
            lines = [
                ("receivable", "debit", invoice.total),
                ("income", "credit", invoice.subtotal),
                ("tax", "credit", invoice.tax_amount),
            ]
        else:
            # DED-11: sin cuenta de gastos/inventario en el plan mínimo —
            # 'adjustment' es la contrapartida de 'payable'.
            document_type = "purchase_invoice"
            lines = [
                ("adjustment", "debit", invoice.subtotal),
                ("tax", "debit", invoice.tax_amount),
                ("payable", "credit", invoice.total),
            ]

        entry = await JournalService.post_entry(
            db,
            company_id=company_id,
            entry_date=invoice.issue_date,
            document_type=document_type,
            document_id=invoice.id,
            description=f"Factura {invoice.number}",
            lines=lines,
            created_by=actor_id,
        )
        invoice.status = "posted"
        invoice.journal_entry_id = entry.id
        invoice.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="invoice.posted", entity_type="invoice", entity_id=invoice.id,
            user_id=actor_id,
        )
        await db.commit()
        await db.refresh(invoice)
        return invoice

    @staticmethod
    async def cancel(db: AsyncSession, *, company_id: int, invoice_id: int, actor_id: int | None) -> models.Invoice:
        invoice = await InvoiceService._get_locked(db, company_id=company_id, invoice_id=invoice_id)
        if invoice.status != "draft":
            raise ConflictError(
                f"No se puede cancelar una factura '{invoice.status}' — una factura contabilizada "
                "se revierte con una nota de crédito/débito, no se cancela directo"
            )
        invoice.status = "cancelled"
        invoice.version += 1
        await db.commit()
        await db.refresh(invoice)
        return invoice


# ---------------------------------------------------------------------------
# Notas de Crédito y Débito
# ---------------------------------------------------------------------------


class CreditDebitNoteService:
    @staticmethod
    async def create_draft(
        db: AsyncSession, *, company_id: int, payload: schemas.CreditDebitNoteCreate, created_by: int | None
    ) -> models.CreditDebitNote:
        contact = await ContactService.get_contact(db, company_id=company_id, contact_id=payload.contact_id)
        if payload.direction.value == "sale" and not contact.is_customer:
            raise ValidationError(f"El contacto '{contact.name}' no tiene el flag is_customer activo")
        if payload.direction.value == "purchase" and not contact.is_vendor:
            raise ValidationError(f"El contacto '{contact.name}' no tiene el flag is_vendor activo")
        if payload.invoice_id is not None:
            invoice = await InvoiceService.get(db, company_id=company_id, invoice_id=payload.invoice_id)
            if invoice.direction != payload.direction.value:
                raise ValidationError("La factura referenciada no coincide con la dirección de la nota")
            if invoice.contact_id != payload.contact_id:
                raise ValidationError("La factura referenciada pertenece a otro contacto")

        subtotal, tax_amount, total, line_dicts = await _compute_lines(
            db, company_id=company_id, raw_lines=payload.lines
        )

        prefix = "NC" if payload.note_type.value == "credit" else "ND"
        number = await DocumentNumberingService.next_number(
            db,
            company_id=company_id,
            doc_type=f"note_{payload.note_type.value}_{payload.direction.value}",
            prefix=prefix,
            year=datetime.now(timezone.utc).year,
        )
        note = models.CreditDebitNote(
            company_id=company_id,
            number=number,
            note_type=payload.note_type.value,
            direction=payload.direction.value,
            contact_id=payload.contact_id,
            invoice_id=payload.invoice_id,
            reason=payload.reason,
            issue_date=payload.issue_date,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total=total,
            created_by=created_by,
        )
        db.add(note)
        await db.flush()
        for ld in line_dicts:
            db.add(models.CreditDebitNoteLine(company_id=company_id, note_id=note.id, **ld))
        await AuditService.log_event(
            db, company_id=company_id, event="credit_debit_note.created", entity_type="credit_debit_note",
            entity_id=note.id, user_id=created_by,
        )
        await db.commit()
        await db.refresh(note)
        return note

    @staticmethod
    async def _get_locked(db: AsyncSession, *, company_id: int, note_id: int) -> models.CreditDebitNote:
        result = await db.execute(
            select(models.CreditDebitNote)
            .where(models.CreditDebitNote.company_id == company_id, models.CreditDebitNote.id == note_id)
            .with_for_update()
        )
        note = result.scalar_one_or_none()
        if note is None:
            raise NotFoundError(f"Nota {note_id} no encontrada")
        return note

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, note_id: int) -> models.CreditDebitNote:
        result = await db.execute(
            select(models.CreditDebitNote).where(
                models.CreditDebitNote.company_id == company_id, models.CreditDebitNote.id == note_id
            )
        )
        note = result.scalar_one_or_none()
        if note is None:
            raise NotFoundError(f"Nota {note_id} no encontrada")
        return note

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.CreditDebitNote]:
        result = await db.execute(
            select(models.CreditDebitNote).where(models.CreditDebitNote.company_id == company_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def post(db: AsyncSession, *, company_id: int, note_id: int, actor_id: int | None) -> models.CreditDebitNote:
        note = await CreditDebitNoteService._get_locked(db, company_id=company_id, note_id=note_id)
        if note.status != "draft":
            raise ConflictError(f"Solo se puede contabilizar una nota en 'draft' (actual: '{note.status}')")

        # DocumentTypeEnum usa "sales_" (plural) para venta pero "purchase_"
        # (singular) para proveedor — mismo patrón asimétrico que
        # sales_invoice/purchase_invoice. Bug real encontrado en Fase 4: una
        # construcción ingenua f"{note.direction}_{suffix}" produce
        # "sale_credit_note" (con 'e', inválido) en vez de
        # "sales_credit_note" — corregido con el mapeo explícito.
        direction_prefix = "sales" if note.direction == "sale" else "purchase"
        suffix = "credit_note" if note.note_type == "credit" else "debit_note"
        document_type = f"{direction_prefix}_{suffix}"

        if note.direction == "sale" and note.note_type == "credit":
            # Reversa de sales_invoice: reduce lo que el cliente debe.
            lines = [
                ("income", "debit", note.subtotal),
                ("tax", "debit", note.tax_amount),
                ("receivable", "credit", note.total),
            ]
        elif note.direction == "sale" and note.note_type == "debit":
            # Cargo adicional al cliente: mismo patrón que sales_invoice.
            lines = [
                ("receivable", "debit", note.total),
                ("income", "credit", note.subtotal),
                ("tax", "credit", note.tax_amount),
            ]
        elif note.direction == "purchase" and note.note_type == "credit":
            # Reversa de purchase_invoice: reduce lo que le debemos al proveedor.
            lines = [
                ("payable", "debit", note.total),
                ("adjustment", "credit", note.subtotal),
                ("tax", "credit", note.tax_amount),
            ]
        else:  # purchase debit note: cargo adicional del proveedor
            lines = [
                ("adjustment", "debit", note.subtotal),
                ("tax", "debit", note.tax_amount),
                ("payable", "credit", note.total),
            ]

        entry = await JournalService.post_entry(
            db,
            company_id=company_id,
            entry_date=note.issue_date,
            document_type=document_type,
            document_id=note.id,
            description=f"Nota {note.number}",
            lines=lines,
            created_by=actor_id,
        )
        note.status = "posted"
        note.journal_entry_id = entry.id
        note.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="credit_debit_note.posted", entity_type="credit_debit_note",
            entity_id=note.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(note)
        return note

    @staticmethod
    async def cancel(db: AsyncSession, *, company_id: int, note_id: int, actor_id: int | None) -> models.CreditDebitNote:
        note = await CreditDebitNoteService._get_locked(db, company_id=company_id, note_id=note_id)
        if note.status != "draft":
            raise ConflictError(f"No se puede cancelar una nota '{note.status}'")
        note.status = "cancelled"
        note.version += 1
        await db.commit()
        await db.refresh(note)
        return note


# ---------------------------------------------------------------------------
# Gestión de Pagos y Cobros
# ---------------------------------------------------------------------------


class PaymentService:
    @staticmethod
    async def create_draft(
        db: AsyncSession, *, company_id: int, payload: schemas.PaymentCreate, created_by: int | None
    ) -> models.Payment:
        contact = await ContactService.get_contact(db, company_id=company_id, contact_id=payload.contact_id)
        if payload.direction.value == "sale" and not contact.is_customer:
            raise ValidationError(f"El contacto '{contact.name}' no tiene el flag is_customer activo")
        if payload.direction.value == "purchase" and not contact.is_vendor:
            raise ValidationError(f"El contacto '{contact.name}' no tiene el flag is_vendor activo")

        # Validación temprana contra la factura real (la validación de
        # Pydantic solo checa la suma contra el monto declarado, no contra
        # el saldo real de cada factura — eso se re-valida también en
        # post(), bajo lock, porque el saldo puede cambiar entre create y
        # post).
        for alloc in payload.allocations:
            invoice = await InvoiceService.get(db, company_id=company_id, invoice_id=alloc.invoice_id)
            if invoice.direction != payload.direction.value:
                raise ValidationError(f"La factura {invoice.number} no coincide con la dirección del pago")
            if invoice.contact_id != payload.contact_id:
                raise ValidationError(f"La factura {invoice.number} pertenece a otro contacto")

        prefix = "REC" if payload.direction.value == "sale" else "PAG"
        number = await DocumentNumberingService.next_number(
            db,
            company_id=company_id,
            doc_type=f"payment_{payload.direction.value}",
            prefix=prefix,
            year=datetime.now(timezone.utc).year,
        )
        payment = models.Payment(
            company_id=company_id,
            number=number,
            direction=payload.direction.value,
            contact_id=payload.contact_id,
            payment_date=payload.payment_date,
            method=payload.method.value,
            amount=payload.amount,
            reference=payload.reference,
            created_by=created_by,
        )
        db.add(payment)
        await db.flush()
        for alloc in payload.allocations:
            db.add(
                models.PaymentAllocation(
                    company_id=company_id, payment_id=payment.id, invoice_id=alloc.invoice_id,
                    amount_applied=alloc.amount_applied,
                )
            )
        await AuditService.log_event(
            db, company_id=company_id, event="payment.created", entity_type="payment", entity_id=payment.id,
            user_id=created_by,
        )
        await db.commit()
        await db.refresh(payment)
        return payment

    @staticmethod
    async def _get_locked(db: AsyncSession, *, company_id: int, payment_id: int) -> models.Payment:
        result = await db.execute(
            select(models.Payment)
            .where(models.Payment.company_id == company_id, models.Payment.id == payment_id)
            .with_for_update()
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            raise NotFoundError(f"Pago {payment_id} no encontrado")
        return payment

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, payment_id: int) -> models.Payment:
        result = await db.execute(
            select(models.Payment).where(models.Payment.company_id == company_id, models.Payment.id == payment_id)
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            raise NotFoundError(f"Pago {payment_id} no encontrado")
        return payment

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Payment]:
        result = await db.execute(select(models.Payment).where(models.Payment.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def post(db: AsyncSession, *, company_id: int, payment_id: int, actor_id: int | None) -> models.Payment:
        payment = await PaymentService._get_locked(db, company_id=company_id, payment_id=payment_id)
        if payment.status != "draft":
            raise ConflictError(f"Solo se puede contabilizar un pago en 'draft' (actual: '{payment.status}')")

        # Lock de facturas en orden ascendente de id — mismo criterio que
        # cualquier lock multi-fila del proyecto, previene deadlock entre
        # pagos concurrentes que tocan las mismas facturas en distinto orden.
        for alloc in sorted(payment.allocations, key=lambda a: a.invoice_id):
            invoice = await InvoiceService._get_locked(db, company_id=company_id, invoice_id=alloc.invoice_id)
            if invoice.status not in ("posted", "partially_paid"):
                raise ConflictError(
                    f"La factura {invoice.number} no está en estado facturable (actual: '{invoice.status}')"
                )
            if alloc.amount_applied > invoice.balance_due:
                raise ValidationError(
                    f"La asignación ({alloc.amount_applied}) excede el saldo pendiente "
                    f"de la factura {invoice.number} ({invoice.balance_due})"
                )
            invoice.balance_due = invoice.balance_due - alloc.amount_applied
            invoice.status = "paid" if invoice.balance_due == 0 else "partially_paid"
            invoice.version += 1

        document_type = "payment_received" if payment.direction == "sale" else "payment_made"
        if payment.direction == "sale":
            lines = [("cash_bank", "debit", payment.amount), ("receivable", "credit", payment.amount)]
        else:
            lines = [("payable", "debit", payment.amount), ("cash_bank", "credit", payment.amount)]

        entry = await JournalService.post_entry(
            db,
            company_id=company_id,
            entry_date=payment.payment_date,
            document_type=document_type,
            document_id=payment.id,
            description=f"Pago {payment.number}",
            lines=lines,
            created_by=actor_id,
        )
        payment.status = "posted"
        payment.journal_entry_id = entry.id
        payment.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="payment.posted", entity_type="payment", entity_id=payment.id,
            user_id=actor_id,
        )
        await db.commit()
        await db.refresh(payment)
        return payment

    @staticmethod
    async def cancel(db: AsyncSession, *, company_id: int, payment_id: int, actor_id: int | None) -> models.Payment:
        payment = await PaymentService._get_locked(db, company_id=company_id, payment_id=payment_id)
        if payment.status != "draft":
            raise ConflictError(f"No se puede cancelar un pago '{payment.status}'")
        payment.status = "cancelled"
        payment.version += 1
        await db.commit()
        await db.refresh(payment)
        return payment


# ---------------------------------------------------------------------------
# Motor de Contención Financiera (DED-12)
# ---------------------------------------------------------------------------


class CreditControlService:
    @staticmethod
    async def get_credit_status(db: AsyncSession, *, company_id: int, contact_id: int) -> schemas.CreditStatusRead:
        contact = await ContactService.get_contact(db, company_id=company_id, contact_id=contact_id)
        result = await db.execute(
            select(models.Invoice).where(
                models.Invoice.company_id == company_id,
                models.Invoice.direction == "sale",
                models.Invoice.contact_id == contact_id,
                models.Invoice.status.in_(("posted", "partially_paid")),
            )
        )
        invoices = list(result.scalars().all())
        outstanding = sum((inv.balance_due for inv in invoices), Decimal("0"))
        has_overdue = any(
            inv.due_date is not None and inv.due_date < date.today() and inv.balance_due > 0 for inv in invoices
        )
        credit_exceeded = contact.credit_limit is not None and outstanding > contact.credit_limit
        return schemas.CreditStatusRead(
            contact_id=contact_id,
            is_blocked=has_overdue or credit_exceeded,
            has_overdue_invoices=has_overdue,
            credit_limit=contact.credit_limit,
            outstanding_balance=outstanding,
            credit_exceeded=credit_exceeded,
        )

    @staticmethod
    async def assert_customer_not_blocked(db: AsyncSession, *, company_id: int, contact_id: int) -> None:
        """Invocado por `sales.SalesOrderService.confirm()` — solo si el
        paquete `accounting` está activo para la compañía (acoplamiento
        flojo intencional, spec: "si accounting no está activo... genera un
        comprobante simple sin asiento"). Ver hook en app/sales/services.py."""
        status = await CreditControlService.get_credit_status(db, company_id=company_id, contact_id=contact_id)
        if status.is_blocked:
            reasons = []
            if status.has_overdue_invoices:
                reasons.append("tiene facturas de venta vencidas con saldo pendiente")
            if status.credit_exceeded:
                reasons.append(
                    f"excede su límite de crédito (saldo {status.outstanding_balance} > límite {status.credit_limit})"
                )
            raise ConflictError(f"Cliente bloqueado por contención financiera: {'; '.join(reasons)}")
