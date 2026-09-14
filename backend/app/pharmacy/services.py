"""
Servicios de pharmacy. Ver docstring de `models.py` para las decisiones
DEDUCIBLE (DED-45 a DED-50).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts.models import Contact
from app.core.services import AuditService, DocumentNumberingService
from app.inventory import models as inventory_models
from app.inventory.services import StockService
from app.pharmacy import models, schemas
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


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
            lines=[schemas.DispensationLineRead.model_validate(l) for l in lines],
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
