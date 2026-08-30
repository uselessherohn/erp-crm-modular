"""
Módulo 3 — inventory (spec sección 8.1), subset [core] de este cierre:
Product, Category, Warehouse, StockMovement, Lot, StockLevel.

[extendido] fuera de este cierre (TODO explícito en STATE.md, no
silencioso): FEFO/FIFO/LIFO, alertas de caducidad, bloqueo/cuarentena de
lote, costeo por lote, valoración de inventario, conversión de unidades,
kits/BOM.

Decisión DEDUCIBLE (no en spec literal): spec marca "Movimientos de Stock...
alta contención" — se interpreta como necesidad de saldo materializado
(StockLevel) actualizado atómicamente junto con cada StockMovement, en vez
de recalcular SUM() en cada lectura. StockMovement queda como ledger
append-only (nunca se edita ni borra un movimiento — solo se revierte con
un movimiento de signo contrario, mismo criterio que audit).
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class ProductTypeEnum(str, enum.Enum):
    facturable = "facturable"
    consumible = "consumible"
    servicio = "servicio"


class MovementTypeEnum(str, enum.Enum):
    entrada = "entrada"
    salida = "salida"
    transferencia = "transferencia"
    ajuste = "ajuste"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Jerarquía simple auto-referencial — spec no pide más que
    # "Categorización y Atributos [core]", sin especificar profundidad.
    parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("categories.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("company_id", "name", "parent_id", name="uq_categories_company_name_parent"),)


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_warehouses_company_name"),)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    product_type: Mapped[str] = mapped_column(String(20), nullable=False)
    category_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("categories.id"), nullable=True)

    # Unidad de medida simple (string libre, ej. "unidad", "caja", "ml") —
    # Conversión de Unidades de Medida es [extendido, requiere
    # Administrativo], no construida en este cierre.
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unidad")

    # Trazabilidad por Lotes y Vencimientos [core] (spec 8.1) — si true,
    # todo StockMovement de este producto exige lot_id.
    tracks_lots: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "sku", name="uq_products_company_sku"),
        CheckConstraint(
            "product_type IN ('facturable', 'consumible', 'servicio')", name="ck_products_product_type"
        ),
    )


class Lot(Base):
    """Trazabilidad por lotes/series y vencimientos [core] — dependencia
    técnica exacta que Farmacéutico necesita como mínimo (spec 2.2)."""

    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False, index=True)

    lot_number: Mapped[str] = mapped_column(String(100), nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", "product_id", "lot_number", name="uq_lots_company_product_number"),
    )


class StockMovement(Base):
    """Ledger append-only — nunca se UPDATE/DELETE (mismo criterio que
    audit, aunque sin trigger de BD todavía: TODO — ver cierre)."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False, index=True)
    lot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("lots.id"), nullable=True)

    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Positivo en entradas/ajustes-alza, negativo en salidas/ajustes-baja —
    # una transferencia se modela como DOS movimientos (salida en origen +
    # entrada en destino), no un solo registro con dos warehouse_id, para
    # que el saldo materializado (StockLevel) se recalcule con una sola
    # regla uniforme sin casos especiales.
    quantity: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)

    reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "movement_type IN ('entrada', 'salida', 'transferencia', 'ajuste')",
            name="ck_stock_movements_movement_type",
        ),
        CheckConstraint("quantity <> 0", name="ck_stock_movements_quantity_nonzero"),
    )


class StockLevel(Base):
    """Saldo materializado — DEDUCIBLE (ver docstring del módulo). Se
    actualiza con UPSERT atómico en la misma transacción que inserta el
    StockMovement correspondiente, nunca de forma independiente."""

    __tablename__ = "stock_levels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False, index=True)
    lot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("lots.id"), nullable=True)

    quantity: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, server_default="0")

    # Reserva de stock (spec 8.1, sales: "confirmados, asignación/reserva
    # de stock") — agregado retroactivamente en el cierre de sales.
    # Disponible para vender = quantity - reserved_quantity. La reserva se
    # incrementa al confirmar una SalesOrder (StockService.reserve) y se
    # libera/consume al enviar (StockService.ship, que descuenta quantity
    # Y reserved_quantity juntos) o cancelar (StockService.release_reservation).
    reserved_quantity: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, server_default="0")

    # Bloqueo optimista adicional (spec sección 5, Concurrencia: "entidades
    # de alta contención — stock, saldos, contadores — llevan columna
    # version"). Hallazgo retroactivo: no estaba en el cierre original de
    # este módulo. El SELECT FOR UPDATE de StockService._apply_delta ya
    # garantiza la corrección bajo concurrencia (probado con 10 conexiones
    # reales) — version es defensa en profundidad para cualquier código
    # futuro que lea-modifique-escriba esta tabla SIN pasar por ese método
    # (ej. un PATCH directo hipotético), no el mecanismo primario.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # NULLS NOT DISTINCT (PG 15+) para que dos filas con lot_id NULL
        # para el mismo producto/almacén sigan violando unicidad — sin
        # esto, NULL != NULL permitiría filas duplicadas para productos sin
        # tracks_lots.
        UniqueConstraint(
            "company_id", "product_id", "warehouse_id", "lot_id",
            name="uq_stock_levels_company_product_warehouse_lot",
            postgresql_nulls_not_distinct=True,
        ),
    )
