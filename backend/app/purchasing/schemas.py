from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PurchaseOrderStatusEnum(str, Enum):
    draft = "draft"
    confirmed = "confirmed"
    received = "received"
    closed = "closed"
    cancelled = "cancelled"


class PurchaseOrderLineCreate(BaseModel):
    product_id: int
    quantity_ordered: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., ge=0)


class PurchaseOrderCreate(BaseModel):
    vendor_id: int
    warehouse_id: int
    currency_code: str = Field(default="HNL", max_length=3)
    expected_date: date | None = None
    reference: str | None = Field(None, max_length=300)
    lines: list[PurchaseOrderLineCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def unique_products(self) -> "PurchaseOrderCreate":
        product_ids = [line.product_id for line in self.lines]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("No se puede repetir el mismo producto en dos líneas — sumá la cantidad en una sola")
        return self


class PurchaseOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    quantity_ordered: Decimal
    quantity_received: Decimal
    unit_cost: Decimal


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    number: str
    vendor_id: int
    warehouse_id: int
    status: PurchaseOrderStatusEnum
    currency_code: str
    expected_date: date | None
    reference: str | None
    version: int
    created_at: datetime
    lines: list[PurchaseOrderLineRead]


class ReceiveLineItem(BaseModel):
    line_id: int
    quantity: Decimal = Field(..., gt=0)


class ReceivePurchaseOrder(BaseModel):
    """Recepción de mercancía — parcial o total (spec 8.1: 'Control de
    Recepción Parcial [core]'). No requiere venir con TODAS las líneas."""

    lines: list[ReceiveLineItem] = Field(..., min_length=1)
