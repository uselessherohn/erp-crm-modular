"""
Módulo 5 — sales (spec sección 8.1), subset [core]: Cotizaciones (validez
temporal, conversión a pedido), Órdenes de Venta (draft->confirmed->
en_preparacion->enviado->facturado->cancelado, con reserva real de stock
al confirmar), Listas de Precios (por cliente/volumen/campaña,
multi-moneda).

[extendido] fuera de este cierre: Descuentos/Promociones, Comisiones de
Vendedores, Devoluciones (RMA).

Convenciones (spec 5): documentos transaccionales con estados explícitos,
dinero Numeric(18,2), numeración atómica vía DocumentNumberingService.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

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


# ---------------------------------------------------------------------------
# Listas de Precios [core] — por cliente/volumen/campaña, multi-moneda.
# DEDUCIBLE: "por cliente" se modela como un PriceList opcionalmente
# asociado a UN Contact (customer_id nullable) — si es NULL, es una lista
# general (ej. "Mayoreo", "Lista base"); "volumen" se modela con
# min_quantity en PriceListItem (precio por quiebre de cantidad); campaña
# no tiene fecha de vigencia propia en este cierre — TODO-11 abajo.
# ---------------------------------------------------------------------------
class PriceList(Base):
    __tablename__ = "price_lists"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")
    customer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["PriceListItem"]] = relationship(back_populates="price_list", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_price_lists_company_name"),
    )


class PriceListItem(Base):
    __tablename__ = "price_list_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    price_list_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("price_lists.id", ondelete="CASCADE"), nullable=False, index=True)

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    min_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, server_default="1")

    price_list: Mapped["PriceList"] = relationship(back_populates="items", lazy="selectin")

    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_price_list_items_unit_price_nonneg"),
        CheckConstraint("min_quantity > 0", name="ck_price_list_items_min_quantity_positive"),
        UniqueConstraint("company_id", "price_list_id", "product_id", "min_quantity", name="uq_price_list_items_list_product_qty"),
    )


# ---------------------------------------------------------------------------
# Cotizaciones [core]
# ---------------------------------------------------------------------------
class QuoteStatusEnum(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    expired = "expired"
    cancelled = "cancelled"
    converted = "converted"  # terminal — ya generó una SalesOrder


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    number: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    price_list_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("price_lists.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)

    converted_to_order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sales_orders.id"), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    lines: Mapped[list["QuoteLine"]] = relationship(back_populates="quote", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'sent', 'accepted', 'expired', 'cancelled', 'converted')",
            name="ck_quotes_status",
        ),
        UniqueConstraint("company_id", "number", name="uq_quotes_company_number"),
    )


class QuoteLine(Base):
    __tablename__ = "quote_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    quote_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True)

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    quote: Mapped["Quote"] = relationship(back_populates="lines", lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_quote_lines_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_quote_lines_unit_price_nonneg"),
    )


# ---------------------------------------------------------------------------
# Órdenes de Venta [core]
# ---------------------------------------------------------------------------
class SalesOrderStatusEnum(str, enum.Enum):
    draft = "draft"
    confirmed = "confirmed"
    en_preparacion = "en_preparacion"
    enviado = "enviado"
    facturado = "facturado"
    cancelado = "cancelado"


class SalesOrder(Base):
    __tablename__ = "sales_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    number: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False)
    price_list_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("price_lists.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")

    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    lines: Mapped[list["SalesOrderLine"]] = relationship(back_populates="sales_order", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'en_preparacion', 'enviado', 'facturado', 'cancelado')",
            name="ck_sales_orders_status",
        ),
        UniqueConstraint("company_id", "number", name="uq_sales_orders_company_number"),
    )


class SalesOrderLine(Base):
    __tablename__ = "sales_order_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    sales_order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True)

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    quantity_shipped: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, server_default="0")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    sales_order: Mapped["SalesOrder"] = relationship(back_populates="lines", lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sales_order_lines_quantity_positive"),
        CheckConstraint("quantity_shipped >= 0", name="ck_sales_order_lines_quantity_shipped_nonneg"),
        CheckConstraint("unit_price >= 0", name="ck_sales_order_lines_unit_price_nonneg"),
    )
