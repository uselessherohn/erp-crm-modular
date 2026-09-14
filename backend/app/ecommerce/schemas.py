from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Configuración (panel interno)
# ---------------------------------------------------------------------------
class EcommerceSettingsUpdate(BaseModel):
    default_warehouse_id: int | None = None
    default_price_list_id: int | None = None


class EcommerceSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    default_warehouse_id: int | None
    default_price_list_id: int | None
    # `webhook_secret` NUNCA se expone en `EcommerceSettingsRead` — se
    # entrega una sola vez, en la respuesta de creación
    # (`EcommerceSettingsCreated`), igual criterio que cualquier secreto
    # emitido una sola vez en el resto del proyecto (ej. API keys).
    created_at: datetime
    updated_at: datetime


class EcommerceSettingsCreated(EcommerceSettingsRead):
    webhook_secret: str


# ---------------------------------------------------------------------------
# Catálogo público
# ---------------------------------------------------------------------------
class CatalogItem(BaseModel):
    product_id: int
    sku: str
    name: str
    unit_price: Decimal


# ---------------------------------------------------------------------------
# Carrito (storefront público)
# ---------------------------------------------------------------------------
class CartItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    quantity: Decimal
    unit_price_snapshot: Decimal


class CartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    currency_code: str
    sales_order_id: int | None
    items: list[CartItemRead]


class CartCreated(CartRead):
    # Se entrega una sola vez, al crear el carrito — mismo criterio que
    # `webhook_secret` arriba. El storefront lo repite en el header
    # `X-Cart-Token` en cada request siguiente sobre este carrito.
    session_token: str


class AddCartItem(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------
class CheckoutRequest(BaseModel):
    name: str = Field(..., max_length=300)
    email: str = Field(..., max_length=255)
    phone: str | None = Field(None, max_length=50)


class CheckoutResult(BaseModel):
    sales_order_id: int
    sales_order_number: str
    status: str
    total_lines: int
