"""
Servicios de sales.

Máquina de estados SalesOrder: draft -> confirmed (reserva stock) ->
en_preparacion (administrativo) -> enviado (descuenta físico + libera
reserva, parcial soportado) -> facturado (administrativo, DEDUCIBLE: sin
lógica adicional todavía, no existe `accounting`). cancelado alcanzable
desde draft/confirmed/en_preparacion (libera cualquier reserva pendiente)
— no desde enviado/facturado (ya hay física de por medio, requeriría RMA,
[extendido], no construido).

Quote: draft -> sent -> accepted -> converted (terminal, generó una
SalesOrder) / expired / cancelled. DEDUCIBLE: solo se puede convertir una
cotización 'accepted' — no confirmado por Roberto.

Todas las transiciones de estado usan SELECT ... FOR UPDATE sobre la fila
del documento (mismo patrón que purchasing).

**Hook cross-módulo agregado en el cierre de accounting (módulo 6), sin
reabrir el contrato público de sales** — `SalesOrderService.confirm()`
invoca `accounting.CreditControlService.assert_customer_not_blocked()`
si el paquete 'administrative' está activo (Motor de Contención
Financiera, DED-12). Ningún endpoint/schema de sales cambió — el cambio
es interno a confirm(), retrocompatible por definición (spec 7: solo
ampliación aditiva de comportamiento, no de contrato).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts.services import ContactService
from app.core.dependencies import get_active_packages
from app.core.services import AuditService, DocumentNumberingService
from app.inventory.services import ProductService, StockService, WarehouseService
from app.sales import models, schemas
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


class PriceListService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.PriceListCreate) -> models.PriceList:
        for item in payload.items:
            await ProductService.get(db, company_id=company_id, product_id=item.product_id)
        if payload.customer_id is not None:
            await ContactService.get_contact(db, company_id=company_id, contact_id=payload.customer_id)

        price_list = models.PriceList(
            company_id=company_id,
            name=payload.name,
            currency_code=payload.currency_code,
            customer_id=payload.customer_id,
            is_default=payload.is_default,
        )
        db.add(price_list)
        await db.flush()
        for item in payload.items:
            db.add(
                models.PriceListItem(
                    company_id=company_id,
                    price_list_id=price_list.id,
                    product_id=item.product_id,
                    unit_price=item.unit_price,
                    min_quantity=item.min_quantity,
                )
            )
        await db.commit()
        await db.refresh(price_list)
        return price_list

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.PriceList]:
        result = await db.execute(select(models.PriceList).where(models.PriceList.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def get_price(
        db: AsyncSession, *, company_id: int, price_list_id: int, product_id: int, quantity: Decimal
    ) -> Decimal:
        result = await db.execute(
            select(models.PriceListItem)
            .where(
                models.PriceListItem.company_id == company_id,
                models.PriceListItem.price_list_id == price_list_id,
                models.PriceListItem.product_id == product_id,
                models.PriceListItem.min_quantity <= quantity,
            )
            .order_by(models.PriceListItem.min_quantity.desc())
            .limit(1)
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise NotFoundError(f"Producto {product_id} no tiene precio en la lista {price_list_id} para cantidad {quantity}")
        return item.unit_price


class QuoteService:
    @staticmethod
    async def create_draft(
        db: AsyncSession, *, company_id: int, payload: schemas.QuoteCreate, created_by: int | None
    ) -> models.Quote:
        customer = await ContactService.get_contact(db, company_id=company_id, contact_id=payload.customer_id)
        if not customer.is_customer:
            raise ValidationError(f"El contacto '{customer.name}' no tiene el flag is_customer activo")
        for line in payload.lines:
            await ProductService.get(db, company_id=company_id, product_id=line.product_id)

        number = await DocumentNumberingService.next_number(
            db, company_id=company_id, doc_type="quote", prefix="QT", year=datetime.now(timezone.utc).year
        )
        quote = models.Quote(
            company_id=company_id,
            number=number,
            customer_id=payload.customer_id,
            price_list_id=payload.price_list_id,
            currency_code=payload.currency_code,
            valid_until=payload.valid_until,
            created_by=created_by,
        )
        db.add(quote)
        await db.flush()
        for line in payload.lines:
            db.add(
                models.QuoteLine(
                    company_id=company_id, quote_id=quote.id,
                    product_id=line.product_id, quantity=line.quantity, unit_price=line.unit_price,
                )
            )
        await AuditService.log_event(
            db, company_id=company_id, event="quote.created", entity_type="quote", entity_id=quote.id, user_id=created_by
        )
        await db.commit()
        await db.refresh(quote)
        return quote

    @staticmethod
    async def _get_locked(db: AsyncSession, *, company_id: int, quote_id: int) -> models.Quote:
        result = await db.execute(
            select(models.Quote).where(models.Quote.company_id == company_id, models.Quote.id == quote_id).with_for_update()
        )
        quote = result.scalar_one_or_none()
        if quote is None:
            raise NotFoundError(f"Cotización {quote_id} no encontrada")
        return quote

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, quote_id: int) -> models.Quote:
        result = await db.execute(select(models.Quote).where(models.Quote.company_id == company_id, models.Quote.id == quote_id))
        quote = result.scalar_one_or_none()
        if quote is None:
            raise NotFoundError(f"Cotización {quote_id} no encontrada")
        return quote

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Quote]:
        result = await db.execute(select(models.Quote).where(models.Quote.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def send(db: AsyncSession, *, company_id: int, quote_id: int, actor_id: int | None) -> models.Quote:
        quote = await QuoteService._get_locked(db, company_id=company_id, quote_id=quote_id)
        if quote.status != "draft":
            raise ConflictError(f"Solo se puede enviar una cotización en 'draft' (actual: '{quote.status}')")
        quote.status = "sent"
        quote.version += 1
        await db.commit()
        await db.refresh(quote)
        return quote

    @staticmethod
    async def accept(db: AsyncSession, *, company_id: int, quote_id: int, actor_id: int | None) -> models.Quote:
        quote = await QuoteService._get_locked(db, company_id=company_id, quote_id=quote_id)
        if quote.status != "sent":
            raise ConflictError(f"Solo se puede aceptar una cotización 'sent' (actual: '{quote.status}')")
        if quote.valid_until < date.today():
            raise ConflictError(f"La cotización venció el {quote.valid_until.isoformat()}")
        quote.status = "accepted"
        quote.version += 1
        await db.commit()
        await db.refresh(quote)
        return quote

    @staticmethod
    async def cancel(db: AsyncSession, *, company_id: int, quote_id: int, actor_id: int | None) -> models.Quote:
        quote = await QuoteService._get_locked(db, company_id=company_id, quote_id=quote_id)
        if quote.status not in ("draft", "sent", "accepted"):
            raise ConflictError(f"No se puede cancelar una cotización en '{quote.status}'")
        quote.status = "cancelled"
        quote.version += 1
        await db.commit()
        await db.refresh(quote)
        return quote

    @staticmethod
    async def convert_to_order(
        db: AsyncSession, *, company_id: int, quote_id: int, warehouse_id: int, actor_id: int | None
    ) -> models.SalesOrder:
        quote = await QuoteService._get_locked(db, company_id=company_id, quote_id=quote_id)
        if quote.status != "accepted":
            raise ConflictError(f"Solo se puede convertir una cotización 'accepted' (actual: '{quote.status}')")

        order = await SalesOrderService.create_draft(
            db,
            company_id=company_id,
            payload=schemas.SalesOrderCreate(
                customer_id=quote.customer_id,
                warehouse_id=warehouse_id,
                price_list_id=quote.price_list_id,
                currency_code=quote.currency_code,
                lines=[
                    schemas.SalesOrderLineCreate(product_id=line.product_id, quantity=line.quantity, unit_price=line.unit_price)
                    for line in quote.lines
                ],
            ),
            created_by=actor_id,
            _skip_commit=True,
        )
        quote.status = "converted"
        quote.converted_to_order_id = order.id
        quote.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="quote.converted", entity_type="quote", entity_id=quote.id, user_id=actor_id
        )
        await db.commit()
        await db.refresh(order)
        return order


class SalesOrderService:
    @staticmethod
    async def create_draft(
        db: AsyncSession, *, company_id: int, payload: schemas.SalesOrderCreate, created_by: int | None,
        _skip_commit: bool = False,
    ) -> models.SalesOrder:
        customer = await ContactService.get_contact(db, company_id=company_id, contact_id=payload.customer_id)
        if not customer.is_customer:
            raise ValidationError(f"El contacto '{customer.name}' no tiene el flag is_customer activo")
        await WarehouseService.get(db, company_id=company_id, warehouse_id=payload.warehouse_id)
        for line in payload.lines:
            await ProductService.get(db, company_id=company_id, product_id=line.product_id)

        number = await DocumentNumberingService.next_number(
            db, company_id=company_id, doc_type="sales_order", prefix="SO", year=datetime.now(timezone.utc).year
        )
        order = models.SalesOrder(
            company_id=company_id,
            number=number,
            customer_id=payload.customer_id,
            warehouse_id=payload.warehouse_id,
            price_list_id=payload.price_list_id,
            currency_code=payload.currency_code,
            created_by=created_by,
        )
        db.add(order)
        await db.flush()
        for line in payload.lines:
            db.add(
                models.SalesOrderLine(
                    company_id=company_id, sales_order_id=order.id,
                    product_id=line.product_id, quantity=line.quantity, unit_price=line.unit_price,
                )
            )
        await AuditService.log_event(
            db, company_id=company_id, event="sales_order.created", entity_type="sales_order", entity_id=order.id, user_id=created_by
        )
        if _skip_commit:
            # Usado por QuoteService.convert_to_order: la creación de la
            # orden y la actualización de la cotización deben ser una sola
            # transacción atómica — el caller hace el commit final.
            await db.flush()
            return order
        await db.commit()
        await db.refresh(order)
        return order

    @staticmethod
    async def _get_locked(db: AsyncSession, *, company_id: int, order_id: int) -> models.SalesOrder:
        result = await db.execute(
            select(models.SalesOrder)
            .where(models.SalesOrder.company_id == company_id, models.SalesOrder.id == order_id)
            .with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise NotFoundError(f"Orden de venta {order_id} no encontrada")
        return order

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, order_id: int) -> models.SalesOrder:
        result = await db.execute(
            select(models.SalesOrder).where(models.SalesOrder.company_id == company_id, models.SalesOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise NotFoundError(f"Orden de venta {order_id} no encontrada")
        return order

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.SalesOrder]:
        result = await db.execute(select(models.SalesOrder).where(models.SalesOrder.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def confirm(db: AsyncSession, *, company_id: int, order_id: int, actor_id: int | None) -> models.SalesOrder:
        order = await SalesOrderService._get_locked(db, company_id=company_id, order_id=order_id)
        if order.status != "draft":
            raise ConflictError(f"Solo se puede confirmar una orden en 'draft' (actual: '{order.status}')")

        # Motor de Contención Financiera (accounting, DED-12) — acoplamiento
        # flojo intencional: solo se evalúa si el paquete 'administrative'
        # (que incluye accounting) está activo para la compañía. Si
        # accounting no está activo, spec dice "el documento origen genera
        # un comprobante simple sin asiento" — es decir, sales sigue
        # funcionando standalone sin bloquear nada.
        active_packages = await get_active_packages(company_id, db)
        if "administrative" in active_packages:
            from app.accounting.services import CreditControlService

            await CreditControlService.assert_customer_not_blocked(
                db, company_id=company_id, contact_id=order.customer_id
            )

        for line in order.lines:
            await StockService.reserve(
                db, company_id=company_id, product_id=line.product_id, warehouse_id=order.warehouse_id,
                lot_id=None, quantity=line.quantity,
            )

        order.status = "confirmed"
        order.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="sales_order.confirmed", entity_type="sales_order", entity_id=order.id, user_id=actor_id
        )
        await db.commit()
        await db.refresh(order)
        return order

    @staticmethod
    async def start_preparation(db: AsyncSession, *, company_id: int, order_id: int, actor_id: int | None) -> models.SalesOrder:
        order = await SalesOrderService._get_locked(db, company_id=company_id, order_id=order_id)
        if order.status != "confirmed":
            raise ConflictError(f"Solo se puede pasar a preparación desde 'confirmed' (actual: '{order.status}')")
        order.status = "en_preparacion"
        order.version += 1
        await db.commit()
        await db.refresh(order)
        return order

    @staticmethod
    async def ship(
        db: AsyncSession, *, company_id: int, order_id: int, payload: schemas.ShipSalesOrder, actor_id: int | None
    ) -> models.SalesOrder:
        order = await SalesOrderService._get_locked(db, company_id=company_id, order_id=order_id)
        if order.status not in ("confirmed", "en_preparacion"):
            raise ConflictError(f"Solo se puede enviar desde 'confirmed'/'en_preparacion' (actual: '{order.status}')")

        lines_by_id = {line.id: line for line in order.lines}
        for item in payload.lines:
            line = lines_by_id.get(item.line_id)
            if line is None:
                raise ValidationError(f"La línea {item.line_id} no pertenece a esta orden")
            new_shipped = line.quantity_shipped + item.quantity
            if new_shipped > line.quantity:
                raise ValidationError(
                    f"Línea {item.line_id}: se intentó enviar {item.quantity}, pero solo quedan "
                    f"{line.quantity - line.quantity_shipped} pendientes de las {line.quantity} ordenadas"
                )
            line.quantity_shipped = new_shipped

            await StockService.ship(
                db, company_id=company_id, product_id=line.product_id, warehouse_id=order.warehouse_id,
                lot_id=None, quantity=item.quantity,
            )

        all_fully_shipped = all(line.quantity_shipped >= line.quantity for line in order.lines)
        order.status = "enviado" if all_fully_shipped else "en_preparacion"
        order.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="sales_order.shipped", entity_type="sales_order", entity_id=order.id, user_id=actor_id
        )
        await db.commit()
        await db.refresh(order)
        return order

    @staticmethod
    async def invoice(db: AsyncSession, *, company_id: int, order_id: int, actor_id: int | None) -> models.SalesOrder:
        order = await SalesOrderService._get_locked(db, company_id=company_id, order_id=order_id)
        if order.status != "enviado":
            raise ConflictError(f"Solo se puede facturar una orden totalmente 'enviado' (actual: '{order.status}')")
        order.status = "facturado"
        order.version += 1
        await db.commit()
        await db.refresh(order)
        return order

    @staticmethod
    async def cancel(db: AsyncSession, *, company_id: int, order_id: int, actor_id: int | None) -> models.SalesOrder:
        order = await SalesOrderService._get_locked(db, company_id=company_id, order_id=order_id)
        if order.status not in ("draft", "confirmed", "en_preparacion"):
            raise ConflictError(f"No se puede cancelar una orden en '{order.status}' — ya tiene envíos registrados")

        if order.status in ("confirmed", "en_preparacion"):
            for line in order.lines:
                pending = line.quantity - line.quantity_shipped
                if pending > 0:
                    await StockService.release_reservation(
                        db, company_id=company_id, product_id=line.product_id, warehouse_id=order.warehouse_id,
                        lot_id=None, quantity=pending,
                    )

        order.status = "cancelado"
        order.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="sales_order.cancelled", entity_type="sales_order", entity_id=order.id, user_id=actor_id
        )
        await db.commit()
        await db.refresh(order)
        return order
