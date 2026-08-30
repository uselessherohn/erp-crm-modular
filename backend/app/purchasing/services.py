"""
Servicios de purchasing. Máquina de estados: draft -> confirmed -> received
-> closed, con cancelled alcanzable desde draft o confirmed (spec 8.1).

Decisión DEDUCIBLE (no en spec literal, documentada en el cierre):
- El número (spec 5: numeración atómica) se genera al CREAR el draft, no
  al confirmar — trazabilidad completa incluso de drafts descartados, a
  costa de huecos en la secuencia si se cancela un draft. La alternativa
  (numerar solo al confirmar) evita huecos pero complica el modelo (un PO
  sin número hasta confirmar). Se eligió trazabilidad sobre continuidad.
- 'received' (recepción 100% completa) es un estado intermedio, no
  terminal — 'closed' es una acción administrativa separada y manual, sin
  lógica de negocio adicional todavía porque `accounting` no existe (no
  hay match de factura que journal-close automáticamente). Cuando se
  construya `accounting`, este 'closed' probablemente pase a disparar
  lógica adicional — TODO señalado en el cierre.

Todas las transiciones de estado usan SELECT ... FOR UPDATE sobre la fila
del PO (mismo patrón de "alta contención" que inventory) — dos usuarios
confirmando o recibiendo el mismo PO a la vez se serializan, no compiten.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts.services import ContactService
from app.core.services import AuditService, DocumentNumberingService
from app.inventory import schemas as inventory_schemas
from app.inventory.services import ProductService, StockService, WarehouseService
from app.purchasing import models, schemas
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


class PurchaseOrderService:
    @staticmethod
    async def create_draft(
        db: AsyncSession, *, company_id: int, payload: schemas.PurchaseOrderCreate, created_by: int | None
    ) -> models.PurchaseOrder:
        # Validaciones de existencia — fallan rápido con NotFoundError si
        # el vendor/warehouse/producto no existen en ESTA compañía (mismo
        # filtro anti-IDOR que el resto del sistema).
        vendor = await ContactService.get_contact(db, company_id=company_id, contact_id=payload.vendor_id)
        if not vendor.is_vendor:
            raise ValidationError(f"El contacto '{vendor.name}' no tiene el flag is_vendor activo")
        await WarehouseService.get(db, company_id=company_id, warehouse_id=payload.warehouse_id)
        for line in payload.lines:
            await ProductService.get(db, company_id=company_id, product_id=line.product_id)

        number = await DocumentNumberingService.next_number(
            db, company_id=company_id, doc_type="purchase_order", prefix="PO", year=datetime.now(timezone.utc).year
        )

        po = models.PurchaseOrder(
            company_id=company_id,
            number=number,
            vendor_id=payload.vendor_id,
            warehouse_id=payload.warehouse_id,
            currency_code=payload.currency_code,
            expected_date=payload.expected_date,
            reference=payload.reference,
            created_by=created_by,
        )
        db.add(po)
        await db.flush()

        for line in payload.lines:
            db.add(
                models.PurchaseOrderLine(
                    company_id=company_id,
                    purchase_order_id=po.id,
                    product_id=line.product_id,
                    quantity_ordered=line.quantity_ordered,
                    unit_cost=line.unit_cost,
                )
            )

        await AuditService.log_event(
            db, company_id=company_id, event="purchase_order.created", entity_type="purchase_order",
            entity_id=po.id, user_id=created_by,
        )
        await db.commit()
        await db.refresh(po)
        return po

    @staticmethod
    async def _get_locked(db: AsyncSession, *, company_id: int, po_id: int) -> models.PurchaseOrder:
        result = await db.execute(
            select(models.PurchaseOrder)
            .where(models.PurchaseOrder.company_id == company_id, models.PurchaseOrder.id == po_id)
            .with_for_update()
        )
        po = result.scalar_one_or_none()
        if po is None:
            raise NotFoundError(f"Orden de compra {po_id} no encontrada")
        return po

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, po_id: int) -> models.PurchaseOrder:
        result = await db.execute(
            select(models.PurchaseOrder).where(
                models.PurchaseOrder.company_id == company_id, models.PurchaseOrder.id == po_id
            )
        )
        po = result.scalar_one_or_none()
        if po is None:
            raise NotFoundError(f"Orden de compra {po_id} no encontrada")
        return po

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.PurchaseOrder]:
        result = await db.execute(select(models.PurchaseOrder).where(models.PurchaseOrder.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def confirm(db: AsyncSession, *, company_id: int, po_id: int, actor_id: int | None) -> models.PurchaseOrder:
        po = await PurchaseOrderService._get_locked(db, company_id=company_id, po_id=po_id)
        if po.status != "draft":
            raise ConflictError(f"Solo se puede confirmar un PO en 'draft' (actual: '{po.status}')")
        po.status = "confirmed"
        po.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="purchase_order.confirmed", entity_type="purchase_order",
            entity_id=po.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(po)
        return po

    @staticmethod
    async def cancel(db: AsyncSession, *, company_id: int, po_id: int, actor_id: int | None) -> models.PurchaseOrder:
        po = await PurchaseOrderService._get_locked(db, company_id=company_id, po_id=po_id)
        if po.status not in ("draft", "confirmed"):
            raise ConflictError(
                f"No se puede cancelar un PO en '{po.status}' — ya tiene recepciones registradas"
            )
        po.status = "cancelled"
        po.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="purchase_order.cancelled", entity_type="purchase_order",
            entity_id=po.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(po)
        return po

    @staticmethod
    async def receive(
        db: AsyncSession, *, company_id: int, po_id: int, payload: schemas.ReceivePurchaseOrder, actor_id: int | None
    ) -> models.PurchaseOrder:
        po = await PurchaseOrderService._get_locked(db, company_id=company_id, po_id=po_id)
        if po.status not in ("confirmed", "received"):
            raise ConflictError(
                f"Solo se puede recibir mercancía de un PO 'confirmed' o parcialmente 'received' (actual: '{po.status}')"
            )

        lines_by_id = {line.id: line for line in po.lines}
        for item in payload.lines:
            line = lines_by_id.get(item.line_id)
            if line is None:
                raise ValidationError(f"La línea {item.line_id} no pertenece a este PO")
            new_received = line.quantity_received + item.quantity
            if new_received > line.quantity_ordered:
                raise ValidationError(
                    f"Línea {item.line_id}: se intentó recibir {item.quantity}, pero solo quedan "
                    f"{line.quantity_ordered - line.quantity_received} pendientes de las {line.quantity_ordered} ordenadas"
                )
            line.quantity_received = new_received

            # Recepción real de mercancía = entrada real de stock (spec
            # 8.1: "Recepción de Mercancía [core]: actualiza stock en
            # inventory") — no un efecto secundario simbólico, pasa por el
            # mismo StockService (mismo SELECT FOR UPDATE), pero la
            # variante _no_commit: receive() ya tiene el PO bloqueado con
            # FOR UPDATE en SU PROPIA transacción — dos/tres/N líneas +
            # el header deben confirmarse juntos o nada (bug real
            # encontrado y corregido: record_movement() público commitea
            # solo, cortaría esta transacción a la mitad).
            await StockService._record_movement_no_commit(
                db,
                company_id=company_id,
                payload=inventory_schemas.StockMovementCreate(
                    product_id=line.product_id,
                    warehouse_id=po.warehouse_id,
                    movement_type=inventory_schemas.MovementTypeEnum.entrada,
                    quantity=item.quantity,
                    reference=f"Recepción {po.number}",
                ),
                created_by=actor_id,
            )

        all_fully_received = all(line.quantity_received >= line.quantity_ordered for line in po.lines)
        po.status = "received" if all_fully_received else "confirmed"
        po.version += 1

        await AuditService.log_event(
            db, company_id=company_id, event="purchase_order.received", entity_type="purchase_order",
            entity_id=po.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(po)
        return po

    @staticmethod
    async def close(db: AsyncSession, *, company_id: int, po_id: int, actor_id: int | None) -> models.PurchaseOrder:
        po = await PurchaseOrderService._get_locked(db, company_id=company_id, po_id=po_id)
        if po.status != "received":
            raise ConflictError(f"Solo se puede cerrar un PO totalmente 'received' (actual: '{po.status}')")
        po.status = "closed"
        po.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="purchase_order.closed", entity_type="purchase_order",
            entity_id=po.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(po)
        return po
