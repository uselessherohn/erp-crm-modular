from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuoteStatusEnum(str, Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    expired = "expired"
    cancelled = "cancelled"
    converted = "converted"


class SalesOrderStatusEnum(str, Enum):
    draft = "draft"
    confirmed = "confirmed"
    en_preparacion = "en_preparacion"
    enviado = "enviado"
    facturado = "facturado"
    cancelado = "cancelado"


# ---------------------------------------------------------------------------
# Listas de precios
# ---------------------------------------------------------------------------
class PriceListItemCreate(BaseModel):
    product_id: int
    unit_price: Decimal = Field(..., ge=0)
    min_quantity: Decimal = Field(default=Decimal(1), gt=0)


class PriceListCreate(BaseModel):
    name: str = Field(..., max_length=200)
    currency_code: str = Field(default="HNL", max_length=3)
    customer_id: int | None = None
    is_default: bool = False
    items: list[PriceListItemCreate] = Field(default_factory=list)


class PriceListItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    unit_price: Decimal
    min_quantity: Decimal


class PriceListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    name: str
    currency_code: str
    customer_id: int | None
    is_default: bool
    items: list[PriceListItemRead]


# ---------------------------------------------------------------------------
# Cotizaciones
# ---------------------------------------------------------------------------
class QuoteLineCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)


class QuoteCreate(BaseModel):
    customer_id: int
    price_list_id: int | None = None
    currency_code: str = Field(default="HNL", max_length=3)
    valid_until: date
    lines: list[QuoteLineCreate] = Field(..., min_length=1)


class QuoteLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    quantity: Decimal
    unit_price: Decimal


class QuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    number: str
    customer_id: int
    price_list_id: int | None
    status: QuoteStatusEnum
    currency_code: str
    valid_until: date
    converted_to_order_id: int | None
    version: int
    created_at: datetime
    lines: list[QuoteLineRead]


# ---------------------------------------------------------------------------
# Órdenes de Venta
# ---------------------------------------------------------------------------
class SalesOrderLineCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)


class SalesOrderCreate(BaseModel):
    customer_id: int
    warehouse_id: int
    price_list_id: int | None = None
    currency_code: str = Field(default="HNL", max_length=3)
    lines: list[SalesOrderLineCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def unique_products(self) -> "SalesOrderCreate":
        product_ids = [line.product_id for line in self.lines]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("No se puede repetir el mismo producto en dos líneas — sumá la cantidad en una sola")
        return self


class SalesOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    quantity: Decimal
    quantity_shipped: Decimal
    unit_price: Decimal


class SalesOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    number: str
    customer_id: int
    warehouse_id: int
    price_list_id: int | None
    status: SalesOrderStatusEnum
    currency_code: str
    version: int
    created_at: datetime
    lines: list[SalesOrderLineRead]


class ShipLineItem(BaseModel):
    line_id: int
    quantity: Decimal = Field(..., gt=0)


class ShipSalesOrder(BaseModel):
    """Envío parcial o total (mismo criterio que Recepción Parcial de
    purchasing) — no requiere venir con TODAS las líneas."""

    lines: list[ShipLineItem] = Field(..., min_length=1)
