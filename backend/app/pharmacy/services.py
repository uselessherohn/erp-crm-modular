"""
Servicios de pharmacy. Ver docstring de `models.py` para las decisiones
DEDUCIBLE (DED-45 a DED-50).
"""
from __future__ import annotations

import abc
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy import func as sa_func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts.models import Contact
from app.contacts.services import ContactService
from app.core.services import AuditService, DocumentNumberingService
from app.inventory import models as inventory_models
from app.inventory.services import ProductService, StockService, WarehouseService
from app.pharmacy import models, schemas
from app.shared.exceptions import ConflictError, NotFoundError, PackageNotLicensedError, ValidationError


class ControlledSubstanceService:
    @staticmethod
    async def mark(db: AsyncSession, *, company_id: int, product_id: int, created_by: int | None) -> models.ControlledSubstanceProduct:
        stmt = (
            pg_insert(models.ControlledSubstanceProduct)
            .values(company_id=company_id, product_id=product_id, created_by=created_by)
            .on_conflict_do_nothing(index_elements=["company_id", "product_id"])
        )
        await db.execute(stmt)
        await db.commit()
        result = await db.execute(
            select(models.ControlledSubstanceProduct).where(
                models.ControlledSubstanceProduct.company_id == company_id,
                models.ControlledSubstanceProduct.product_id == product_id,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def unmark(db: AsyncSession, *, company_id: int, product_id: int) -> None:
        result = await db.execute(
            select(models.ControlledSubstanceProduct).where(
                models.ControlledSubstanceProduct.company_id == company_id,
                models.ControlledSubstanceProduct.product_id == product_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            await db.delete(row)
            await db.commit()

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.ControlledSubstanceProduct]:
        result = await db.execute(
            select(models.ControlledSubstanceProduct).where(models.ControlledSubstanceProduct.company_id == company_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def is_controlled(db: AsyncSession, *, company_id: int, product_id: int) -> bool:
        result = await db.execute(
            select(models.ControlledSubstanceProduct.id).where(
                models.ControlledSubstanceProduct.company_id == company_id,
                models.ControlledSubstanceProduct.product_id == product_id,
            )
        )
        return result.scalar_one_or_none() is not None


async def _pick_fefo_lots(
    db: AsyncSession, *, company_id: int, product_id: int, warehouse_id: int, quantity_needed: Decimal
) -> list[tuple[int | None, Decimal]]:
    """DED-45 — FEFO: consume primero el lote con `expiry_date` más
    próximo (NULLS LAST: un lote sin fecha de vencimiento se trata como
    "vence más lejos", se consume al final). Devuelve una lista de
    (lot_id, cantidad_a_tomar_de_ese_lote) que en conjunto suman
    `quantity_needed`, o lanza `ConflictError` si el disponible total no
    alcanza — sin tocar `StockLevel` todavía (eso lo hace el llamador vía
    `StockService.ship` por cada lote, dentro de la misma transacción)."""
    result = await db.execute(
        select(
            inventory_models.StockLevel.lot_id,
            (inventory_models.StockLevel.quantity - inventory_models.StockLevel.reserved_quantity).label("available"),
            inventory_models.Lot.expiry_date,
        )
        .outerjoin(inventory_models.Lot, inventory_models.Lot.id == inventory_models.StockLevel.lot_id)
        .where(
            inventory_models.StockLevel.company_id == company_id,
            inventory_models.StockLevel.product_id == product_id,
            inventory_models.StockLevel.warehouse_id == warehouse_id,
        )
        .order_by(inventory_models.Lot.expiry_date.asc().nulls_last())
    )
    rows = result.all()

    picks: list[tuple[int | None, Decimal]] = []
    remaining = quantity_needed
    for lot_id, available, _expiry in rows:
        if remaining <= 0:
            break
        if available is None or available <= 0:
            continue
        take = min(available, remaining)
        picks.append((lot_id, take))
        remaining -= take

    if remaining > 0:
        raise ConflictError(
            f"Stock disponible insuficiente para dispensar producto {product_id} en el almacén "
            f"{warehouse_id}: faltan {remaining} unidades"
        )
    return picks


class DispensationService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.DispensationOrderCreate, dispensed_by: int
    ) -> schemas.DispensationOrderRead:
        from app.core.dependencies import get_active_packages

        patient = (
            await db.execute(select(Contact).where(Contact.company_id == company_id, Contact.id == payload.patient_contact_id))
        ).scalar_one_or_none()
        if patient is None:
            raise NotFoundError(f"Contacto {payload.patient_contact_id} no encontrado")

        active_packages = await get_active_packages(company_id, db)

        # DED-47: Verificación Clínica.
        if payload.prescription_id is not None and "medical" not in active_packages:
            raise ValidationError("prescription_id requiere el paquete 'medical' activo — use walk_in_reference")

        allergy_notes = payload.allergy_check_notes
        # DED-47/48: el chequeo contra el expediente médico solo aplica si
        # el contacto ES un paciente de medical (is_patient=true) — un
        # cliente de mostrador de farmacia no tiene por qué serlo (DED-48),
        # y `ClinicalRecordService` exige ese flag. Con `medical` activo
        # pero el contacto sin `is_patient`, se cae al formulario mínimo
        # igual que si `medical` no estuviera activo.
        if "medical" in active_packages and patient.is_patient:
            from app.medical.schemas import ClinicalRecordEntryTypeEnum
            from app.medical.services import ClinicalRecordService

            entries = await ClinicalRecordService.list_for_patient(
                db, company_id=company_id, patient_contact_id=payload.patient_contact_id, actor_user_id=dispensed_by
            )
            allergies = [e for e in entries if e.entry_type == ClinicalRecordEntryTypeEnum.allergy]
            allergy_check_source = models.AllergyCheckSourceEnum.medical_record.value
            allergy_notes = "; ".join(a.content for a in allergies) if allergies else allergy_notes
        else:
            if not payload.allergy_check_notes:
                raise ValidationError(
                    "Sin expediente médico disponible para este contacto, allergy_check_notes es obligatorio "
                    "(formulario mínimo de alergias, spec 8.3)"
                )
            allergy_check_source = models.AllergyCheckSourceEnum.form.value

        document_number = await DocumentNumberingService.next_number(
            db, company_id=company_id, doc_type="pharmacy_dispensation", prefix="DISP", year=date.today().year
        )

        order = models.DispensationOrder(
            company_id=company_id, warehouse_id=payload.warehouse_id, patient_contact_id=payload.patient_contact_id,
            dispensed_by=dispensed_by, document_number=document_number,
            prescription_id=payload.prescription_id, walk_in_reference=payload.walk_in_reference,
            allergy_check_source=allergy_check_source, allergy_check_notes=allergy_notes,
            payment_method=payload.payment_method, amount_charged=payload.amount_charged,
        )
        db.add(order)
        await db.flush()

        for line_request in payload.lines:
            picks = await _pick_fefo_lots(
                db, company_id=company_id, product_id=line_request.product_id, warehouse_id=payload.warehouse_id,
                quantity_needed=line_request.quantity,
            )
            is_controlled = await ControlledSubstanceService.is_controlled(
                db, company_id=company_id, product_id=line_request.product_id
            )
            for lot_id, take_quantity in picks:
                await StockService.ship(
                    db, company_id=company_id, product_id=line_request.product_id, warehouse_id=payload.warehouse_id,
                    lot_id=lot_id, quantity=take_quantity,
                )
                dispensation_line = models.DispensationLine(
                    company_id=company_id, dispensation_order_id=order.id,
                    product_id=line_request.product_id, lot_id=lot_id, quantity=take_quantity,
                )
                db.add(dispensation_line)
                await db.flush()

                if is_controlled:
                    db.add(models.ControlledSubstanceLogEntry(
                        company_id=company_id, dispensation_line_id=dispensation_line.id,
                        product_id=line_request.product_id, patient_contact_id=payload.patient_contact_id,
                        dispensed_by=dispensed_by, quantity=take_quantity,
                    ))

        await AuditService.log_event(
            db, company_id=company_id, event="pharmacy.dispensation.create", entity_type="dispensation_order",
            entity_id=order.id, user_id=dispensed_by,
        )
        await db.commit()
        return await DispensationService.get(db, company_id=company_id, order_id=order.id)

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, order_id: int) -> schemas.DispensationOrderRead:
        result = await db.execute(
            select(models.DispensationOrder).where(
                models.DispensationOrder.company_id == company_id, models.DispensationOrder.id == order_id
            )
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise NotFoundError(f"Dispensación {order_id} no encontrada")

        lines_result = await db.execute(
            select(models.DispensationLine)
            .where(models.DispensationLine.dispensation_order_id == order.id)
            .order_by(models.DispensationLine.id)
        )
        lines = list(lines_result.scalars().all())

        return schemas.DispensationOrderRead(
            id=order.id, company_id=order.company_id, warehouse_id=order.warehouse_id,
            patient_contact_id=order.patient_contact_id, dispensed_by=order.dispensed_by,
            document_number=order.document_number, prescription_id=order.prescription_id,
            walk_in_reference=order.walk_in_reference, allergy_check_source=order.allergy_check_source,
            allergy_check_notes=order.allergy_check_notes, payment_method=order.payment_method,
            amount_charged=order.amount_charged, status=order.status, voided_at=order.voided_at,
            void_reason=order.void_reason, dispensed_at=order.dispensed_at,
            lines=[schemas.DispensationLineRead.model_validate(line) for line in lines],
        )

    @staticmethod
    async def list_for_patient(db: AsyncSession, *, company_id: int, patient_contact_id: int) -> list[schemas.DispensationOrderRead]:
        result = await db.execute(
            select(models.DispensationOrder.id)
            .where(models.DispensationOrder.company_id == company_id, models.DispensationOrder.patient_contact_id == patient_contact_id)
            .order_by(models.DispensationOrder.dispensed_at.desc())
        )
        ids = [row[0] for row in result.all()]
        return [await DispensationService.get(db, company_id=company_id, order_id=oid) for oid in ids]

    @staticmethod
    async def void(
        db: AsyncSession, *, company_id: int, order_id: int, payload: schemas.DispensationVoid, actor_id: int
    ) -> schemas.DispensationOrderRead:
        """DED-50: anular NO revierte el descuento de inventario."""
        result = await db.execute(
            select(models.DispensationOrder)
            .where(models.DispensationOrder.company_id == company_id, models.DispensationOrder.id == order_id)
            .with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise NotFoundError(f"Dispensación {order_id} no encontrada")
        if order.status == "voided":
            raise ConflictError("Esta dispensación ya fue anulada")

        from sqlalchemy import func as sa_func

        order.status = "voided"
        order.voided_at = sa_func.now()
        order.void_reason = payload.void_reason

        await AuditService.log_event(
            db, company_id=company_id, event="pharmacy.dispensation.void", entity_type="dispensation_order",
            entity_id=order.id, user_id=actor_id,
        )
        await db.commit()
        return await DispensationService.get(db, company_id=company_id, order_id=order_id)


class ControlledSubstanceLogService:
    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.ControlledSubstanceLogEntry]:
        """Reporte exportable para autoridad sanitaria (spec 8.3) — Fase 1
        expone el listado crudo; export a CSV/PDF queda para `reports`
        (módulo 24, transversal) o una extensión posterior de este mismo
        módulo, no duplicado acá."""
        result = await db.execute(
            select(models.ControlledSubstanceLogEntry)
            .where(models.ControlledSubstanceLogEntry.company_id == company_id)
            .order_by(models.ControlledSubstanceLogEntry.created_at.desc())
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Módulo 21 — MTM / Consulta Farmacéutica. Ver DED-62/63/64 en models.py.
# ---------------------------------------------------------------------------
class MtmSessionService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.MtmSessionCreate, pharmacist_user_id: int
    ) -> models.MtmSession:
        patient = (
            await db.execute(select(Contact).where(Contact.company_id == company_id, Contact.id == payload.patient_contact_id))
        ).scalar_one_or_none()
        if patient is None:
            raise NotFoundError(f"Contacto {payload.patient_contact_id} no encontrado")

        session = models.MtmSession(
            company_id=company_id, patient_contact_id=payload.patient_contact_id,
            pharmacist_user_id=pharmacist_user_id, session_date=payload.session_date,
            medication_review=payload.medication_review, adherence_notes=payload.adherence_notes,
            adverse_effects_notes=payload.adverse_effects_notes, recommendations=payload.recommendations,
            fee_amount=payload.fee_amount, currency_code=payload.currency_code, created_by=pharmacist_user_id,
        )
        db.add(session)
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="pharmacy.mtm_session.create", entity_type="mtm_session",
            entity_id=session.id, user_id=pharmacist_user_id,
        )
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, session_id: int) -> models.MtmSession:
        result = await db.execute(
            select(models.MtmSession).where(models.MtmSession.company_id == company_id, models.MtmSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise NotFoundError(f"Sesión de MTM {session_id} no encontrada")
        return session

    @staticmethod
    async def list_for_patient(db: AsyncSession, *, company_id: int, patient_contact_id: int) -> list[models.MtmSession]:
        result = await db.execute(
            select(models.MtmSession)
            .where(models.MtmSession.company_id == company_id, models.MtmSession.patient_contact_id == patient_contact_id)
            .order_by(models.MtmSession.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def cancel(
        db: AsyncSession, *, company_id: int, session_id: int, payload: schemas.MtmSessionCancel, actor_id: int
    ) -> models.MtmSession:
        """Cancela una sesión ANTES de cerrarla (nunca llegó a generar
        comprobante) — distinto de anular un comprobante ya emitido, que
        es `cancel_billing` más abajo sobre `MtmBillingRecord`."""
        result = await db.execute(
            select(models.MtmSession)
            .where(models.MtmSession.company_id == company_id, models.MtmSession.id == session_id)
            .with_for_update()
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise NotFoundError(f"Sesión de MTM {session_id} no encontrada")
        if session.status != "open":
            raise ConflictError(f"Solo se puede cancelar una sesión 'open' (estado actual: {session.status})")

        from sqlalchemy import func as sa_func

        session.status = "cancelled"
        session.cancelled_at = sa_func.now()
        session.cancel_reason = payload.cancel_reason

        await AuditService.log_event(
            db, company_id=company_id, event="pharmacy.mtm_session.cancel", entity_type="mtm_session",
            entity_id=session.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def close(
        db: AsyncSession, *, company_id: int, session_id: int, payload: schemas.MtmSessionClose, actor_id: int
    ) -> models.MtmBillingRecord:
        """Cierra la sesión Y genera el comprobante en la misma operación
        (DED-62 — "Sesión de asesoría cerrada" es el disparador literal
        de spec 9, no una acción de facturación separada). Mismo modo
        dual que `medical.MedicalBillingService.create` (DED-63)."""
        from app.core.dependencies import get_active_packages

        result = await db.execute(
            select(models.MtmSession)
            .where(models.MtmSession.company_id == company_id, models.MtmSession.id == session_id)
            .with_for_update()
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise NotFoundError(f"Sesión de MTM {session_id} no encontrada")
        if session.status != "open":
            raise ConflictError(f"Solo se puede cerrar una sesión 'open' (estado actual: {session.status})")

        active_packages = await get_active_packages(company_id, db)

        invoice_id = None
        receipt_number = None

        if "administrative" in active_packages:
            from app.accounting import schemas as accounting_schemas
            from app.accounting.services import InvoiceService

            invoice = await InvoiceService.create_draft(
                db, company_id=company_id,
                payload=accounting_schemas.InvoiceCreate(
                    direction=accounting_schemas.DirectionEnum.sale,
                    contact_id=session.patient_contact_id,
                    currency_code=session.currency_code,
                    issue_date=payload.issue_date,
                    source_document_type="pharmacy_mtm_session",
                    source_document_id=session.id,
                    lines=[accounting_schemas.InvoiceLineCreate(
                        description="Consulta farmacéutica (MTM)", quantity=Decimal(1),
                        unit_price=session.fee_amount, tax_rate_id=payload.tax_rate_id,
                    )],
                ),
                created_by=actor_id,
            )
            invoice = await InvoiceService.post(db, company_id=company_id, invoice_id=invoice.id, actor_id=actor_id)
            invoice_id = invoice.id
            billing_mode = "accounting_invoice"
        else:
            receipt_number = await DocumentNumberingService.next_number(
                db, company_id=company_id, doc_type="pharmacy_mtm_receipt", prefix="MTM",
                year=payload.issue_date.year,
            )
            billing_mode = "simple_receipt"

        billing_record = models.MtmBillingRecord(
            company_id=company_id, session_id=session.id, billing_mode=billing_mode,
            amount=session.fee_amount, currency_code=session.currency_code, issue_date=payload.issue_date,
            invoice_id=invoice_id, receipt_number=receipt_number,
        )
        db.add(billing_record)

        from sqlalchemy import func as sa_func

        session.status = "closed"
        session.closed_at = sa_func.now()

        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="pharmacy.mtm_session.close", entity_type="mtm_session",
            entity_id=session.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(billing_record)
        return billing_record

    @staticmethod
    async def get_billing_for_session(
        db: AsyncSession, *, company_id: int, session_id: int
    ) -> models.MtmBillingRecord | None:
        result = await db.execute(
            select(models.MtmBillingRecord).where(
                models.MtmBillingRecord.company_id == company_id,
                models.MtmBillingRecord.session_id == session_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def cancel_billing(
        db: AsyncSession, *, company_id: int, billing_record_id: int, payload: schemas.MtmSessionCancel, actor_id: int
    ) -> models.MtmBillingRecord:
        """Anula un comprobante YA emitido (post-cierre) — el
        `MtmSession` vinculado queda `closed` (el contenido clínico de
        la sesión no se revierte); mismo criterio que
        `medical.MedicalBillingService.cancel`."""
        result = await db.execute(
            select(models.MtmBillingRecord)
            .where(models.MtmBillingRecord.company_id == company_id, models.MtmBillingRecord.id == billing_record_id)
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundError(f"Comprobante de MTM {billing_record_id} no encontrado")
        if record.status == "cancelled":
            raise ConflictError("Este comprobante ya fue anulado")

        from sqlalchemy import func as sa_func

        record.status = "cancelled"
        record.cancelled_at = sa_func.now()
        record.cancel_reason = payload.cancel_reason

        await AuditService.log_event(
            db, company_id=company_id, event="pharmacy.mtm_billing.cancel", entity_type="mtm_billing_record",
            entity_id=record.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(record)
        return record


# ---------------------------------------------------------------------------
# Módulo 20 — Reposición a Droguerías. Ver DED-65/66/67 en models.py.
# ---------------------------------------------------------------------------
class ReorderPointService:
    @staticmethod
    async def upsert(
        db: AsyncSession, *, company_id: int, payload: schemas.ReorderPointUpsert, actor_id: int | None
    ) -> models.PharmacyReorderPoint:
        await ProductService.get(db, company_id=company_id, product_id=payload.product_id)
        await WarehouseService.get(db, company_id=company_id, warehouse_id=payload.warehouse_id)
        if payload.preferred_vendor_id is not None:
            from app.contacts.services import ContactService

            vendor = await ContactService.get_contact(db, company_id=company_id, contact_id=payload.preferred_vendor_id)
            if not vendor.is_vendor:
                raise ValidationError(f"El contacto '{vendor.name}' no tiene el flag is_vendor activo")

        result = await db.execute(
            select(models.PharmacyReorderPoint).where(
                models.PharmacyReorderPoint.company_id == company_id,
                models.PharmacyReorderPoint.product_id == payload.product_id,
                models.PharmacyReorderPoint.warehouse_id == payload.warehouse_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.reorder_point = payload.reorder_point
            existing.reorder_quantity = payload.reorder_quantity
            existing.preferred_vendor_id = payload.preferred_vendor_id
            point = existing
        else:
            point = models.PharmacyReorderPoint(
                company_id=company_id, product_id=payload.product_id, warehouse_id=payload.warehouse_id,
                reorder_point=payload.reorder_point, reorder_quantity=payload.reorder_quantity,
                preferred_vendor_id=payload.preferred_vendor_id, created_by=actor_id,
            )
            db.add(point)
        await db.commit()
        await db.refresh(point)
        return point

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int, warehouse_id: int | None = None) -> list[models.PharmacyReorderPoint]:
        stmt = select(models.PharmacyReorderPoint).where(models.PharmacyReorderPoint.company_id == company_id)
        if warehouse_id is not None:
            stmt = stmt.where(models.PharmacyReorderPoint.warehouse_id == warehouse_id)
        result = await db.execute(stmt.order_by(models.PharmacyReorderPoint.id))
        return list(result.scalars().all())

    @staticmethod
    async def delete(db: AsyncSession, *, company_id: int, reorder_point_id: int) -> None:
        result = await db.execute(
            select(models.PharmacyReorderPoint).where(
                models.PharmacyReorderPoint.company_id == company_id, models.PharmacyReorderPoint.id == reorder_point_id
            )
        )
        point = result.scalar_one_or_none()
        if point is None:
            raise NotFoundError(f"Punto de pedido {reorder_point_id} no encontrado")
        await db.delete(point)
        await db.commit()


class ReorderSuggestionService:
    @staticmethod
    async def list_suggestions(db: AsyncSession, *, company_id: int, warehouse_id: int) -> list[schemas.ReorderSuggestionRead]:
        """Compara `PharmacyReorderPoint` contra el stock disponible real
        (`StockLevel`, sumado a través de todos los lotes — spec 8.1 FEFO
        no importa acá, solo el total disponible). Calculado al vuelo,
        nunca persistido (DED-65)."""
        points = await ReorderPointService.list(db, company_id=company_id, warehouse_id=warehouse_id)
        if not points:
            return []

        product_ids = [p.product_id for p in points]
        result = await db.execute(
            select(
                inventory_models.StockLevel.product_id,
                func.sum(inventory_models.StockLevel.quantity - inventory_models.StockLevel.reserved_quantity).label("available"),
            )
            .where(
                inventory_models.StockLevel.company_id == company_id,
                inventory_models.StockLevel.warehouse_id == warehouse_id,
                inventory_models.StockLevel.product_id.in_(product_ids),
            )
            .group_by(inventory_models.StockLevel.product_id)
        )
        available_by_product = {row.product_id: row.available for row in result.all()}

        suggestions: list[schemas.ReorderSuggestionRead] = []
        for point in points:
            available = available_by_product.get(point.product_id, Decimal(0))
            if available <= point.reorder_point:
                suggestions.append(schemas.ReorderSuggestionRead(
                    product_id=point.product_id, warehouse_id=point.warehouse_id,
                    available_quantity=available, reorder_point=point.reorder_point,
                    reorder_quantity=point.reorder_quantity, below_by=point.reorder_point - available,
                    preferred_vendor_id=point.preferred_vendor_id,
                ))
        return suggestions

    @staticmethod
    async def generate_purchase_order(
        db: AsyncSession, *, company_id: int, payload: schemas.ReorderPurchaseOrderGenerate, actor_id: int | None
    ):
        """Requiere `administrative` completo (spec 8.3: "opcionalmente
        generando una PO en `purchasing` si el Administrativo completo
        está presente"). Sin él, la spec dice explícitamente que la
        sugerencia "queda como lista exportable sin flujo de aprobación"
        — no hay a qué PO generar, así que esta acción simplemente no
        está disponible (DED-66)."""
        from app.core.dependencies import get_active_packages

        active_packages = await get_active_packages(company_id, db)
        if "administrative" not in active_packages:
            raise PackageNotLicensedError(
                "Generar una orden de compra desde reposición requiere el paquete Administrativo completo — "
                "sin él, la sugerencia queda como lista exportable (spec 8.3)"
            )

        from app.purchasing import schemas as purchasing_schemas
        from app.purchasing.services import PurchaseOrderService

        po = await PurchaseOrderService.create_draft(
            db, company_id=company_id,
            payload=purchasing_schemas.PurchaseOrderCreate(
                vendor_id=payload.vendor_id, warehouse_id=payload.warehouse_id,
                currency_code=payload.currency_code, expected_date=payload.expected_date,
                reference="Generada desde sugerencia de reposición (módulo 20)",
                lines=[
                    purchasing_schemas.PurchaseOrderLineCreate(
                        product_id=line.product_id, quantity_ordered=line.quantity, unit_cost=line.unit_cost,
                    )
                    for line in payload.lines
                ],
            ),
            created_by=actor_id,
        )

        await AuditService.log_event(
            db, company_id=company_id, event="pharmacy.reorder.generate_po", entity_type="purchase_order",
            entity_id=po.id, user_id=actor_id,
        )
        await db.commit()
        return po


# ---------------------------------------------------------------------------------
# Módulo 17 — Interacciones [extendido]. Ver DED-58 a DED-61 en models.py.
# ---------------------------------------------------------------------------------------------


def _normalize_ingredient(name: str) -> str:
    return " ".join(name.strip().lower().split())


class ProductActiveIngredientService:
    @staticmethod
    async def set(
        db: AsyncSession, *, company_id: int, payload: schemas.ProductActiveIngredientSet, created_by: int | None,
    ) -> models.ProductActiveIngredient:
        normalized = _normalize_ingredient(payload.active_ingredient)
        stmt = (
            pg_insert(models.ProductActiveIngredient)
            .values(company_id=company_id, product_id=payload.product_id, active_ingredient=normalized, created_by=created_by)
            .on_conflict_do_update(
                index_elements=["company_id", "product_id"],
                set_={"active_ingredient": normalized},
            )
        )
        await db.execute(stmt)
        await db.commit()
        result = await db.execute(
            select(models.ProductActiveIngredient).where(
                models.ProductActiveIngredient.company_id == company_id,
                models.ProductActiveIngredient.product_id == payload.product_id,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.ProductActiveIngredient]:
        result = await db.execute(
            select(models.ProductActiveIngredient).where(models.ProductActiveIngredient.company_id == company_id)
        )
        return list(result.scalars().all())


class DrugInteractionProvider(abc.ABC):
    @abc.abstractmethod
    async def check_pairs(self, db: AsyncSession, *, ingredient_pairs: list[tuple[str, str]]) -> list[models.DrugInteractionReferenceEntry]:
        """Recibe pares ya normalizados y ordenados alfabéticamente
        (ingredient_a < ingredient_b) y devuelve las entradas del catálogo
        que matchean."""
        raise NotImplementedError


class DevStubDrugInteractionProvider(DrugInteractionProvider):
    """Implementación de desarrollo (DED-58) — el sandbox de este proyecto
    no tiene salida de red hacia RxNorm/DrugBank. Consulta el catálogo de
    referencia local (`DrugInteractionReferenceEntry`, seed pequeño a
    mano). Producción inyecta un cliente real de la API externa detrás de
    la misma interfaz — el resto del servicio no cambia."""

    async def check_pairs(self, db: AsyncSession, *, ingredient_pairs: list[tuple[str, str]]) -> list[models.DrugInteractionReferenceEntry]:
        if not ingredient_pairs:
            return []
        from sqlalchemy import tuple_

        result = await db.execute(
            select(models.DrugInteractionReferenceEntry).where(
                tuple_(
                    models.DrugInteractionReferenceEntry.ingredient_a,
                    models.DrugInteractionReferenceEntry.ingredient_b,
                ).in_(ingredient_pairs)
            )
        )
        return list(result.scalars().all())


_default_drug_interaction_provider: DrugInteractionProvider = DevStubDrugInteractionProvider()


class DrugInteractionService:
    @staticmethod
    async def check(
        db: AsyncSession, *, company_id: int, payload: schemas.InteractionCheckRequest,
        provider: DrugInteractionProvider | None = None,
    ) -> schemas.InteractionCheckResult:
        active_provider = provider or _default_drug_interaction_provider

        result = await db.execute(
            select(models.ProductActiveIngredient).where(
                models.ProductActiveIngredient.company_id == company_id,
                models.ProductActiveIngredient.product_id.in_(payload.product_ids),
            )
        )
        mapped = list(result.scalars().all())
        ingredient_by_product = {row.product_id: row.active_ingredient for row in mapped}
        unchecked = [pid for pid in payload.product_ids if pid not in ingredient_by_product]

        # Todas las combinaciones únicas de productos con ingrediente
        # mapeado — DED-59: un producto sin mapeo simplemente no genera
        # pares, no rompe el chequeo del resto.
        checked_products = list(ingredient_by_product.items())
        pair_lookup: dict[tuple[str, str], list[tuple[int, int]]] = {}
        for i in range(len(checked_products)):
            for j in range(i + 1, len(checked_products)):
                product_a, ingredient_a = checked_products[i]
                product_b, ingredient_b = checked_products[j]
                if ingredient_a == ingredient_b:
                    continue
                key = (ingredient_a, ingredient_b) if ingredient_a < ingredient_b else (ingredient_b, ingredient_a)
                product_pair = (product_a, product_b) if ingredient_a < ingredient_b else (product_b, product_a)
                pair_lookup.setdefault(key, []).append(product_pair)

        entries = await active_provider.check_pairs(db, ingredient_pairs=list(pair_lookup.keys()))

        warnings: list[schemas.InteractionWarning] = []
        for entry in entries:
            for product_id_a, product_id_b in pair_lookup.get((entry.ingredient_a, entry.ingredient_b), []):
                warnings.append(
                    schemas.InteractionWarning(
                        product_id_a=product_id_a, product_id_b=product_id_b,
                        ingredient_a=entry.ingredient_a, ingredient_b=entry.ingredient_b,
                        severity=entry.severity, description=entry.description,
                    )
                )

        return schemas.InteractionCheckResult(warnings=warnings, unchecked_product_ids=unchecked)


# ---------------------------------------------------------------------------------------------
# Módulo 18 — Aseguradoras [extendido]. Ver DED-62 a DED-64 en models.py.
# ---------------------------------------------------------------------------------------------
class InsuranceProviderService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.InsuranceProviderCreate,
    ) -> models.InsuranceProvider:
        contact = await ContactService.get_contact(db, company_id=company_id, contact_id=payload.contact_id)
        if not contact.is_customer:
            raise ValidationError(
                f"El contacto '{contact.name}' debe tener is_customer=true para poder facturarle "
                "reclamos (el motor de accounting lo exige)"
            )
        provider = models.InsuranceProvider(
            company_id=company_id, contact_id=payload.contact_id,
            default_coverage_percentage=payload.default_coverage_percentage,
        )
        db.add(provider)
        await db.commit()
        await db.refresh(provider)
        return provider

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.InsuranceProvider]:
        result = await db.execute(select(models.InsuranceProvider).where(models.InsuranceProvider.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, provider_id: int) -> models.InsuranceProvider:
        result = await db.execute(
            select(models.InsuranceProvider).where(
                models.InsuranceProvider.company_id == company_id, models.InsuranceProvider.id == provider_id,
            )
        )
        provider = result.scalar_one_or_none()
        if provider is None:
            raise NotFoundError(f"Aseguradora {provider_id} no encontrada")
        return provider


class PatientInsurancePolicyService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.PatientInsurancePolicyCreate,
    ) -> models.PatientInsurancePolicy:
        await InsuranceProviderService.get(db, company_id=company_id, provider_id=payload.insurance_provider_id)
        policy = models.PatientInsurancePolicy(
            company_id=company_id, patient_contact_id=payload.patient_contact_id,
            insurance_provider_id=payload.insurance_provider_id, policy_number=payload.policy_number,
            coverage_percentage=payload.coverage_percentage,
        )
        db.add(policy)
        await db.commit()
        await db.refresh(policy)
        return policy

    @staticmethod
    async def list_for_patient(db: AsyncSession, *, company_id: int, patient_contact_id: int) -> list[models.PatientInsurancePolicy]:
        result = await db.execute(
            select(models.PatientInsurancePolicy).where(
                models.PatientInsurancePolicy.company_id == company_id,
                models.PatientInsurancePolicy.patient_contact_id == patient_contact_id,
            )
        )
        return list(result.scalars().all())


class InsuranceClaimService:
    @staticmethod
    async def _get_locked(db: AsyncSession, *, company_id: int, claim_id: int) -> models.InsuranceClaim:
        result = await db.execute(
            select(models.InsuranceClaim)
            .where(models.InsuranceClaim.company_id == company_id, models.InsuranceClaim.id == claim_id)
            .with_for_update()
        )
        claim = result.scalar_one_or_none()
        if claim is None:
            raise NotFoundError(f"Reclamo {claim_id} no encontrado")
        return claim

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, claim_id: int) -> models.InsuranceClaim:
        result = await db.execute(
            select(models.InsuranceClaim).where(
                models.InsuranceClaim.company_id == company_id, models.InsuranceClaim.id == claim_id,
            )
        )
        claim = result.scalar_one_or_none()
        if claim is None:
            raise NotFoundError(f"Reclamo {claim_id} no encontrado")
        return claim

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.InsuranceClaim]:
        result = await db.execute(
            select(models.InsuranceClaim)
            .where(models.InsuranceClaim.company_id == company_id)
            .order_by(models.InsuranceClaim.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.InsuranceClaimCreate,
    ) -> models.InsuranceClaim:
        order = await DispensationService.get(db, company_id=company_id, order_id=payload.dispensation_order_id)
        if order.status == "voided":
            raise ValidationError("No se puede crear un reclamo para una dispensación anulada")
        provider = await InsuranceProviderService.get(db, company_id=company_id, provider_id=payload.insurance_provider_id)

        claim_number = await DocumentNumberingService.next_number(
            db, company_id=company_id, doc_type="pharmacy_insurance_claim", prefix="REC", year=date.today().year,
        )
        claim = models.InsuranceClaim(
            company_id=company_id, dispensation_order_id=order.id, insurance_provider_id=provider.id,
            patient_contact_id=order.patient_contact_id, claim_number=claim_number,
            amount_total=payload.amount_total, amount_patient_copay=payload.amount_patient_copay,
            amount_claimed_insurer=payload.amount_claimed_insurer,
        )
        db.add(claim)
        await db.commit()
        await db.refresh(claim)
        return claim

    @staticmethod
    async def submit(db: AsyncSession, *, company_id: int, claim_id: int) -> models.InsuranceClaim:
        claim = await InsuranceClaimService._get_locked(db, company_id=company_id, claim_id=claim_id)
        if claim.status != "pending":
            raise ConflictError(f"Solo se puede enviar un reclamo en 'pending' (actual: '{claim.status}')")
        claim.status = "submitted"
        claim.submitted_at = sa_func.now()
        await db.commit()
        await db.refresh(claim)
        return claim

    @staticmethod
    async def reject(
        db: AsyncSession, *, company_id: int, claim_id: int, payload: schemas.InsuranceClaimReject,
    ) -> models.InsuranceClaim:
        claim = await InsuranceClaimService._get_locked(db, company_id=company_id, claim_id=claim_id)
        if claim.status not in ("pending", "submitted"):
            raise ConflictError(
                f"Solo se puede rechazar un reclamo en 'pending'/'submitted' (actual: '{claim.status}') "
                "— un reclamo ya aprobado ya generó una factura real, no se puede rechazar sin un flujo "
                "de devolución (mismo criterio que TODO-42 de dispensación, fuera de alcance de este cierre)"
            )
        claim.status = "rejected"
        claim.rejected_at = sa_func.now()
        claim.rejection_reason = payload.rejection_reason
        await db.commit()
        await db.refresh(claim)
        return claim

    @staticmethod
    async def approve(db: AsyncSession, *, company_id: int, claim_id: int, actor_id: int | None) -> models.InsuranceClaim:
        from app.core.dependencies import get_active_packages

        claim = await InsuranceClaimService._get_locked(db, company_id=company_id, claim_id=claim_id)
        if claim.status != "submitted":
            raise ConflictError(f"Solo se puede aprobar un reclamo en 'submitted' (actual: '{claim.status}')")

        order = await DispensationService.get(db, company_id=company_id, order_id=claim.dispensation_order_id)
        provider = await InsuranceProviderService.get(db, company_id=company_id, provider_id=claim.insurance_provider_id)
        active_packages = await get_active_packages(company_id, db)

        if "administrative" in active_packages:
            # DED-40/42 (medical billing): 'administrative' activo -> se
            # reutiliza el motor real de accounting, no se duplica lógica.
            from app.accounting import schemas as accounting_schemas
            from app.accounting.services import InvoiceService

            invoice = await InvoiceService.create_draft(
                db, company_id=company_id,
                payload=accounting_schemas.InvoiceCreate(
                    direction=accounting_schemas.DirectionEnum.sale,
                    contact_id=provider.contact_id,
                    currency_code="HNL",
                    issue_date=date.today(),
                    source_document_type="pharmacy_insurance_claim",
                    source_document_id=claim.id,
                    lines=[accounting_schemas.InvoiceLineCreate(
                        description=f"Reclamo de seguro {claim.claim_number} — dispensación {order.document_number}",
                        quantity=Decimal(1), unit_price=claim.amount_claimed_insurer,
                    )],
                ),
                created_by=actor_id,
            )
            invoice = await InvoiceService.post(db, company_id=company_id, invoice_id=invoice.id, actor_id=actor_id)
            claim.invoice_id = invoice.id
            claim.billing_mode = "accounting_invoice"
        else:
            claim.billing_mode = "claim_only"

        claim.status = "approved"
        claim.approved_at = sa_func.now()
        await db.commit()
        await db.refresh(claim)
        return claim

    @staticmethod
    async def pay(
        db: AsyncSession, *, company_id: int, claim_id: int, payload: schemas.InsuranceClaimPay, actor_id: int | None,
    ) -> models.InsuranceClaim:
        claim = await InsuranceClaimService._get_locked(db, company_id=company_id, claim_id=claim_id)
        if claim.status != "approved":
            raise ConflictError(f"Solo se puede liquidar un reclamo en 'approved' (actual: '{claim.status}')")

        amount_paid = payload.amount_paid or claim.amount_claimed_insurer

        if claim.billing_mode == "accounting_invoice":
            from app.accounting import schemas as accounting_schemas
            from app.accounting.services import PaymentService

            provider = await InsuranceProviderService.get(db, company_id=company_id, provider_id=claim.insurance_provider_id)
            payment = await PaymentService.create_draft(
                db, company_id=company_id,
                payload=accounting_schemas.PaymentCreate(
                    direction=accounting_schemas.DirectionEnum.sale,
                    contact_id=provider.contact_id,
                    payment_date=date.today(),
                    method=accounting_schemas.PaymentMethodEnum.bank_transfer,
                    amount=amount_paid,
                    reference=f"Pago aseguradora — {claim.claim_number}",
                    allocations=[accounting_schemas.PaymentAllocationCreate(invoice_id=claim.invoice_id, amount_applied=amount_paid)],
                ),
                created_by=actor_id,
            )
            payment = await PaymentService.post(db, company_id=company_id, payment_id=payment.id, actor_id=actor_id)
            claim.payment_id = payment.id

        claim.status = "paid"
        claim.paid_at = sa_func.now()
        await db.commit()
        await db.refresh(claim)
        return claim
