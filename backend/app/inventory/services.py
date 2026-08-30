"""
Servicios de inventory. StockService concentra la lógica sensible a
concurrencia (spec 8.1: "alta contención") — ver docstring de cada método
para el patrón de bloqueo usado y por qué.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services import AuditService
from app.inventory import models, schemas
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


class CategoryService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.CategoryCreate) -> models.Category:
        category = models.Category(company_id=company_id, **payload.model_dump())
        db.add(category)
        await db.commit()
        await db.refresh(category)
        return category

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Category]:
        result = await db.execute(select(models.Category).where(models.Category.company_id == company_id))
        return list(result.scalars().all())


class WarehouseService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.WarehouseCreate) -> models.Warehouse:
        warehouse = models.Warehouse(company_id=company_id, **payload.model_dump())
        db.add(warehouse)
        await db.commit()
        await db.refresh(warehouse)
        return warehouse

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Warehouse]:
        result = await db.execute(select(models.Warehouse).where(models.Warehouse.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, warehouse_id: int) -> models.Warehouse:
        result = await db.execute(
            select(models.Warehouse).where(
                models.Warehouse.company_id == company_id, models.Warehouse.id == warehouse_id
            )
        )
        warehouse = result.scalar_one_or_none()
        if warehouse is None:
            raise NotFoundError(f"Almacén {warehouse_id} no encontrado")
        return warehouse


class ProductService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.ProductCreate, created_by: int | None) -> models.Product:
        existing = await db.execute(
            select(models.Product).where(models.Product.company_id == company_id, models.Product.sku == payload.sku)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(f"Ya existe un producto con SKU '{payload.sku}' en esta compañía")

        product = models.Product(
            company_id=company_id, created_by=created_by, **payload.model_dump(exclude={"product_type"}),
            product_type=payload.product_type.value,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Product]:
        result = await db.execute(select(models.Product).where(models.Product.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, product_id: int) -> models.Product:
        result = await db.execute(
            select(models.Product).where(models.Product.company_id == company_id, models.Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise NotFoundError(f"Producto {product_id} no encontrado")
        return product


class StockService:
    @staticmethod
    async def _get_or_create_lot(
        db: AsyncSession, *, company_id: int, product_id: int, lot_number: str, expiry_date=None
    ) -> models.Lot:
        # get_or_create vía upsert — un duplicado concurrente simplemente no
        # inserta (ON CONFLICT DO NOTHING) y la siguiente SELECT lo trae, en
        # vez de depender de capturar IntegrityError con try/except (más
        # frágil bajo asyncio con sesiones que quedan "dirty" tras un
        # rollback parcial).
        stmt = (
            pg_insert(models.Lot)
            .values(company_id=company_id, product_id=product_id, lot_number=lot_number, expiry_date=expiry_date)
            .on_conflict_do_nothing(index_elements=["company_id", "product_id", "lot_number"])
        )
        await db.execute(stmt)
        result = await db.execute(
            select(models.Lot).where(
                models.Lot.company_id == company_id,
                models.Lot.product_id == product_id,
                models.Lot.lot_number == lot_number,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def _get_locked_level(
        db: AsyncSession, *, company_id: int, product_id: int, warehouse_id: int, lot_id: int | None
    ) -> models.StockLevel:
        """Mismo patrón UPSERT-a-cero + SELECT FOR UPDATE que _apply_delta,
        factorizado para reutilizar en reserve/release_reservation/ship
        (spec 8.1 sales: reserva de stock) sin duplicar el UPSERT."""
        upsert_stmt = (
            pg_insert(models.StockLevel)
            .values(company_id=company_id, product_id=product_id, warehouse_id=warehouse_id, lot_id=lot_id, quantity=0)
            .on_conflict_do_nothing(index_elements=["company_id", "product_id", "warehouse_id", "lot_id"])
        )
        await db.execute(upsert_stmt)

        lot_filter = models.StockLevel.lot_id.is_(None) if lot_id is None else models.StockLevel.lot_id == lot_id
        result = await db.execute(
            select(models.StockLevel)
            .where(
                models.StockLevel.company_id == company_id,
                models.StockLevel.product_id == product_id,
                models.StockLevel.warehouse_id == warehouse_id,
                lot_filter,
            )
            .with_for_update()
        )
        return result.scalar_one()

    @staticmethod
    async def reserve(
        db: AsyncSession, *, company_id: int, product_id: int, warehouse_id: int, lot_id: int | None, quantity: Decimal
    ) -> models.StockLevel:
        """Reserva de stock al confirmar una SalesOrder (spec 8.1) — NO
        descuenta `quantity` (el físico), solo `reserved_quantity`.
        Disponible = quantity - reserved_quantity. Mismo SELECT FOR UPDATE
        que _apply_delta: dos confirmaciones concurrentes del mismo
        producto/almacén se serializan, no compiten por stock fantasma."""
        level = await StockService._get_locked_level(
            db, company_id=company_id, product_id=product_id, warehouse_id=warehouse_id, lot_id=lot_id
        )
        available = level.quantity - level.reserved_quantity
        if quantity > available:
            raise ConflictError(f"Stock disponible insuficiente para reservar: disponible {available}, se pidió {quantity}")
        level.reserved_quantity += quantity
        level.version += 1
        await db.flush()
        return level

    @staticmethod
    async def release_reservation(
        db: AsyncSession, *, company_id: int, product_id: int, warehouse_id: int, lot_id: int | None, quantity: Decimal
    ) -> models.StockLevel:
        """Libera una reserva sin tocar el físico (cancelación de
        SalesOrder antes de enviar)."""
        level = await StockService._get_locked_level(
            db, company_id=company_id, product_id=product_id, warehouse_id=warehouse_id, lot_id=lot_id
        )
        level.reserved_quantity = max(Decimal(0), level.reserved_quantity - quantity)
        level.version += 1
        await db.flush()
        return level

    @staticmethod
    async def ship(
        db: AsyncSession, *, company_id: int, product_id: int, warehouse_id: int, lot_id: int | None, quantity: Decimal
    ) -> models.StockLevel:
        """Envío real (spec 8.1, estado 'enviado' de SalesOrder) — acá SÍ
        se descuenta el físico (`quantity`), Y se libera la reserva
        correspondiente (`reserved_quantity`) en la MISMA operación
        bloqueada, para que nunca quede un estado intermedio donde
        `reserved_quantity > quantity` sea visible a otra transacción."""
        level = await StockService._get_locked_level(
            db, company_id=company_id, product_id=product_id, warehouse_id=warehouse_id, lot_id=lot_id
        )
        if quantity > level.quantity:
            raise ConflictError(f"Stock físico insuficiente para enviar: disponible {level.quantity}, se intentó enviar {quantity}")
        level.quantity -= quantity
        level.reserved_quantity = max(Decimal(0), level.reserved_quantity - quantity)
        level.version += 1
        await db.flush()
        return level

    @staticmethod
    async def _apply_delta(
        db: AsyncSession, *, company_id: int, product_id: int, warehouse_id: int, lot_id: int | None, delta: Decimal
    ) -> models.StockLevel:
        """Núcleo de la sección "alta contención" de spec 8.1.

        Patrón de dos pasos, no un UPDATE ciego:
        1. UPSERT que garantiza que la fila exista con quantity=0 si es la
           primera vez (ON CONFLICT DO NOTHING) — evita la carrera de "dos
           transacciones insertan la primera fila a la vez" sin necesitar
           try/except sobre IntegrityError.
        2. SELECT ... FOR UPDATE sobre esa fila — serializa cualquier otra
           transacción que quiera tocar el MISMO (product, warehouse, lot)
           hasta que esta termine. Otras combinaciones (producto distinto,
           almacén distinto) no se bloquean entre sí — el lock es por fila,
           no de tabla.

        Sin este patrón, dos salidas concurrentes del mismo producto podrían
        leer el mismo saldo "antes" y ambas descontar sobre él, dejando
        stock negativo sin que ninguna lo detecte (clásico lost update).
        """
        upsert_stmt = (
            pg_insert(models.StockLevel)
            .values(company_id=company_id, product_id=product_id, warehouse_id=warehouse_id, lot_id=lot_id, quantity=0)
            .on_conflict_do_nothing(
                index_elements=["company_id", "product_id", "warehouse_id", "lot_id"]
            )
        )
        await db.execute(upsert_stmt)

        lot_filter = models.StockLevel.lot_id.is_(None) if lot_id is None else models.StockLevel.lot_id == lot_id
        result = await db.execute(
            select(models.StockLevel)
            .where(
                models.StockLevel.company_id == company_id,
                models.StockLevel.product_id == product_id,
                models.StockLevel.warehouse_id == warehouse_id,
                lot_filter,
            )
            .with_for_update()
        )
        level = result.scalar_one()

        new_quantity = level.quantity + delta
        if new_quantity < 0:
            raise ConflictError(
                f"Stock insuficiente: disponible {level.quantity}, se intentó descontar {-delta}"
            )
        level.quantity = new_quantity
        level.version += 1
        await db.flush()
        return level

    @staticmethod
    async def _record_movement_no_commit(
        db: AsyncSession, *, company_id: int, payload: schemas.StockMovementCreate, created_by: int | None
    ) -> models.StockMovement:
        """Misma lógica que record_movement, SIN el commit/refresh final —
        para componer varios movimientos dentro de UNA transacción más
        grande (ej. purchasing.receive(): un PO con 5 líneas registra 5
        movimientos + actualiza el header, todo atómico o nada). Bug real
        encontrado al escribir purchasing: record_movement() hacía su
        propio commit() interno, lo que cortaba a la mitad cualquier
        transacción compuesta que lo llamara más de una vez."""
        product = await ProductService.get(db, company_id=company_id, product_id=payload.product_id)
        await WarehouseService.get(db, company_id=company_id, warehouse_id=payload.warehouse_id)

        if product.tracks_lots and not payload.lot_number:
            raise ValidationError(f"El producto '{product.sku}' requiere lot_number (tracks_lots=true)")
        if not product.tracks_lots and payload.lot_number:
            raise ValidationError(f"El producto '{product.sku}' no maneja lotes (tracks_lots=false)")

        lot_id = None
        if payload.lot_number:
            lot = await StockService._get_or_create_lot(
                db,
                company_id=company_id,
                product_id=payload.product_id,
                lot_number=payload.lot_number,
                expiry_date=payload.expiry_date,
            )
            lot_id = lot.id

        sign = Decimal(1) if payload.movement_type in (schemas.MovementTypeEnum.entrada,) else Decimal(-1)
        # 'ajuste' puede ser alza o baja — spec no lo distingue con dos tipos
        # separados, así que se interpreta el signo desde la cantidad misma
        # NO siendo posible (quantity siempre > 0 en el schema); en cambio,
        # se trata 'ajuste' como baja por default (el caso más común/crítico
        # a auditar: mermas, vencimientos, conteos físicos con faltante) y
        # se documenta como DEDUCIBLE — un ajuste de alza real se modela
        # como 'entrada' con reference='ajuste positivo: <motivo>'.
        if payload.movement_type == schemas.MovementTypeEnum.ajuste:
            sign = Decimal(-1)
        delta = sign * payload.quantity

        await StockService._apply_delta(
            db,
            company_id=company_id,
            product_id=payload.product_id,
            warehouse_id=payload.warehouse_id,
            lot_id=lot_id,
            delta=delta,
        )

        movement = models.StockMovement(
            company_id=company_id,
            product_id=payload.product_id,
            warehouse_id=payload.warehouse_id,
            lot_id=lot_id,
            movement_type=payload.movement_type.value,
            quantity=delta,
            reference=payload.reference,
            correlation_id=str(uuid.uuid4()),
            created_by=created_by,
        )
        db.add(movement)
        await db.flush()

        await AuditService.log_event(
            db,
            company_id=company_id,
            event=f"stock.{payload.movement_type.value}",
            entity_type="stock_movement",
            entity_id=movement.id,
            user_id=created_by,
            correlation_id=movement.correlation_id,
        )
        return movement

    @staticmethod
    async def record_movement(
        db: AsyncSession, *, company_id: int, payload: schemas.StockMovementCreate, created_by: int | None
    ) -> models.StockMovement:
        """Entrypoint usado por el router — commitea al final. Para
        componer con otra lógica dentro de la MISMA transacción (ej.
        purchasing.receive), usar _record_movement_no_commit directamente."""
        movement = await StockService._record_movement_no_commit(
            db, company_id=company_id, payload=payload, created_by=created_by
        )
        await db.commit()
        await db.refresh(movement)
        return movement

    @staticmethod
    async def transfer(
        db: AsyncSession, *, company_id: int, payload: schemas.TransferCreate, created_by: int | None
    ) -> list[models.StockMovement]:
        """Una transferencia es SIEMPRE dos StockMovement (salida+entrada)
        con el mismo correlation_id — nunca un movimiento con dos
        warehouse_id (ver docstring de StockMovement en models.py). Ambos
        se aplican en la MISMA transacción de DB: si el destino falla (ej.
        almacén inexistente), la salida del origen también se revierte."""
        await WarehouseService.get(db, company_id=company_id, warehouse_id=payload.source_warehouse_id)
        await WarehouseService.get(db, company_id=company_id, warehouse_id=payload.destination_warehouse_id)
        product = await ProductService.get(db, company_id=company_id, product_id=payload.product_id)

        if product.tracks_lots and not payload.lot_number:
            raise ValidationError(f"El producto '{product.sku}' requiere lot_number (tracks_lots=true)")

        lot_id = None
        if payload.lot_number:
            lot = await StockService._get_or_create_lot(
                db, company_id=company_id, product_id=payload.product_id, lot_number=payload.lot_number
            )
            lot_id = lot.id

        correlation_id = str(uuid.uuid4())
        movements = []

        # Salida del origen PRIMERO — si no hay stock suficiente,
        # _apply_delta lanza ConflictError acá y la transacción completa se
        # revierte antes de tocar el destino (ver rollback en el router).
        await StockService._apply_delta(
            db,
            company_id=company_id,
            product_id=payload.product_id,
            warehouse_id=payload.source_warehouse_id,
            lot_id=lot_id,
            delta=-payload.quantity,
        )
        salida = models.StockMovement(
            company_id=company_id,
            product_id=payload.product_id,
            warehouse_id=payload.source_warehouse_id,
            lot_id=lot_id,
            movement_type="transferencia",
            quantity=-payload.quantity,
            reference=payload.reference,
            correlation_id=correlation_id,
            created_by=created_by,
        )
        db.add(salida)
        movements.append(salida)

        await StockService._apply_delta(
            db,
            company_id=company_id,
            product_id=payload.product_id,
            warehouse_id=payload.destination_warehouse_id,
            lot_id=lot_id,
            delta=payload.quantity,
        )
        entrada = models.StockMovement(
            company_id=company_id,
            product_id=payload.product_id,
            warehouse_id=payload.destination_warehouse_id,
            lot_id=lot_id,
            movement_type="transferencia",
            quantity=payload.quantity,
            reference=payload.reference,
            correlation_id=correlation_id,
            created_by=created_by,
        )
        db.add(entrada)
        movements.append(entrada)

        await db.flush()
        await AuditService.log_event(
            db,
            company_id=company_id,
            event="stock.transferencia",
            entity_type="stock_movement",
            entity_id=salida.id,
            user_id=created_by,
            correlation_id=correlation_id,
        )
        await db.commit()
        for m in movements:
            await db.refresh(m)
        return movements

    @staticmethod
    async def get_levels(
        db: AsyncSession, *, company_id: int, product_id: int | None = None, warehouse_id: int | None = None
    ) -> list[models.StockLevel]:
        stmt = select(models.StockLevel).where(models.StockLevel.company_id == company_id)
        if product_id is not None:
            stmt = stmt.where(models.StockLevel.product_id == product_id)
        if warehouse_id is not None:
            stmt = stmt.where(models.StockLevel.warehouse_id == warehouse_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())
