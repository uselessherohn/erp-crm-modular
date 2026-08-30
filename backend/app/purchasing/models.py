"""
Módulo 4 — purchasing (spec sección 8.1), subset [core]: Órdenes de Compra
(PO) draft→confirmed→received→closed(+cancelled), Recepción de Mercancía,
Control de Recepción Parcial.

Convenciones aplicadas (spec sección 5):
- Documento transaccional: estados explícitos, NO soft delete.
- Dinero: Numeric(18,2), nunca float. currency_code en el header.
- Numeración atómica vía DocumentNumberingService (core), nunca MAX()+1.

[extendido] fuera de este cierre: Requisiciones internas, Gestión/
Evaluación de Proveedores (no hay entidad Supplier — reutiliza Contact con
is_vendor=true, tal cual pide la spec), RFQ, Contratos Marco/Blanket Orders.
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


class PurchaseOrderStatusEnum(str, enum.Enum):
    draft = "draft"
    confirmed = "confirmed"
    received = "received"  # recepción completa
    closed = "closed"
    cancelled = "cancelled"


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    number: Mapped[str] = mapped_column(String(50), nullable=False)  # PO-2026-000001
    vendor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")

    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # version: bloqueo optimista adicional para el header (spec 5 nombra
    # explícitamente "stock, saldos, contadores" — un PO no es ninguno de
    # los tres, pero como documento transaccional con transiciones de
    # estado concurrentes (dos usuarios confirmando/cancelando a la vez),
    # aplica el mismo criterio de defensa en profundidad por consistencia.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'received', 'closed', 'cancelled')",
            name="ck_purchase_orders_status",
        ),
        UniqueConstraint("company_id", "number", name="uq_purchase_orders_company_number"),
    )

    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="purchase_order", lazy="selectin", cascade="all, delete-orphan"
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    purchase_order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, server_default="0")
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity_ordered > 0", name="ck_po_lines_quantity_ordered_positive"),
        CheckConstraint("quantity_received >= 0", name="ck_po_lines_quantity_received_nonneg"),
        CheckConstraint("unit_cost >= 0", name="ck_po_lines_unit_cost_nonneg"),
    )

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="lines", lazy="selectin")
