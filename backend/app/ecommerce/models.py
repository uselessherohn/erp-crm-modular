"""
Módulo 23 — ecommerce (spec sección 8.4).

Alcance [core] construido en este cierre: Catálogo de Productos (lectura,
reutiliza `inventory.Product` + la lista de precios por defecto de
`sales`), Carrito de Compras (sesión anónima por token), Checkout
(crea/reutiliza `Contact(is_customer=true)` + `sales.SalesOrder` real —
NO se inventa un modelo `Order` paralelo, ver DED en
`diseno_modulos_22_25_erp_crm.md` sección 2.2), Procesamiento de Pagos
(webhook con verificación de firma + deduplicación por `event_id`,
confirma la orden y genera+contabiliza la factura real vía `accounting`).

Fuera de alcance [extendido], no construido aquí: Gestión de Envíos,
Cupones y Descuentos, Reseñas, Devoluciones de Ecommerce, notificación
transaccional al cliente (el módulo 26 `notifications` solo notifica
`User` internos, no `Contact` externos — no existe canal de email al
cliente en este proyecto; TODO explícito, no una omisión silenciosa).

Depende de `website` (22, relación de paquete comercial — ver nota de
secuencia en el documento de diseño), `inventory` (3), `sales` (5),
`accounting` (6) — los tres últimos como mínimos técnicos, siempre juntos
(spec 2.2).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EcommerceSettings(Base):
    """Configuración mínima necesaria para que el checkout funcione — una
    fila por compañía. DEDUCIBLE: sin esto configurado, el checkout falla
    con un error de validación explícito en vez de adivinar un almacén o
    lista de precios (spec no dice cuál usar; no hay campo "default" en
    `Warehouse` — hallazgo real de este cierre, ver STATE.md)."""

    __tablename__ = "ecommerce_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, unique=True)

    default_warehouse_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=True)
    default_price_list_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("price_lists.id"), nullable=True)

    # DEDUCIBLE: verificación de firma de webhook simplificada a un
    # secreto compartido por compañía (HMAC-SHA256) en vez del esquema
    # propio de cada pasarela real (Stripe/PayPal/MercadoPago tienen cada
    # una su propio mecanismo de firma) — no se integró ningún SDK de
    # pasarela real en este cierre (spec 8.4 no especifica cuál usar).
    webhook_secret: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Cart(Base):
    __tablename__ = "ecommerce_carts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    # AMBIGUO (ver diseno_modulos_22_25_erp_crm.md sección 2.4): el diseño
    # original proponía cookie firmada; se implementó como token opaco
    # devuelto en el body y repetido en el header `X-Cart-Token` en cada
    # request siguiente — funcionalmente equivalente, más simple de
    # implementar y de probar sin navegador real. Cambiar a cookie no
    # tocaría el modelo, solo routers.py.
    session_token: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")  # open|checked_out
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")

    # Trazabilidad hacia la orden real una vez hecho el checkout — no hay
    # un modelo `Order` propio, el carrito apunta directo a `sales.SalesOrder`.
    sales_order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sales_orders.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("company_id", "session_token", name="uq_ecommerce_carts_company_token"),)


class CartItem(Base):
    __tablename__ = "ecommerce_cart_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    cart_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ecommerce_carts.id", ondelete="CASCADE"), nullable=False, index=True)

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    # Precio congelado al agregar al carrito (spec 8.4) — cache de
    # UI/checkout, no fuente de verdad: `sales.SalesOrderLine.unit_price`
    # es la que realmente queda facturada, tomada de nuevo desde
    # `PriceListService.get_price` en el momento del checkout, no copiada
    # de este campo (evita que un carrito viejo "congele" un precio
    # desactualizado hasta el checkout real).
    unit_price_snapshot: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("cart_id", "product_id", name="uq_ecommerce_cart_items_cart_product"),)


class PaymentGatewayEvent(Base):
    """Deduplicación de webhooks por `event_id` — mecanismo separado del
    `Idempotency-Key` genérico de spec 7 (ese cubre reintentos del
    checkout desde el cliente; este cubre reintentos del webhook desde la
    pasarela, spec 8.4 lo aclara como algo distinto)."""

    __tablename__ = "ecommerce_payment_gateway_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    gateway: Mapped[str] = mapped_column(String(30), nullable=False)
    event_id: Mapped[str] = mapped_column(String(150), nullable=False)
    payload_raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sales_order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sales_orders.id"), nullable=True)

    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", "gateway", "event_id", name="uq_ecommerce_payment_events_company_gateway_event"),
    )
