from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductTypeEnum(str, Enum):
    facturable = "facturable"
    consumible = "consumible"
    servicio = "servicio"


class MovementTypeEnum(str, Enum):
    entrada = "entrada"
    salida = "salida"
    ajuste = "ajuste"
    # 'transferencia' no está acá a propósito: en el modelo se representa
    # como dos StockMovement (salida+entrada), nunca como un tercer tipo
    # con dos warehouse_id — ver TransferCreate más abajo.


class CategoryBase(BaseModel):
    name: str = Field(..., max_length=200)
    parent_id: int | None = None


class CategoryCreate(CategoryBase):
    pass


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    is_active: bool


class WarehouseBase(BaseModel):
    name: str = Field(..., max_length=200)
    address: str | None = Field(None, max_length=500)


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseRead(WarehouseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    is_active: bool


class ProductBase(BaseModel):
    sku: str = Field(..., max_length=100)
    barcode: str | None = Field(None, max_length=100)
    name: str = Field(..., max_length=300)
    product_type: ProductTypeEnum
    category_id: int | None = None
    unit_of_measure: str = Field(default="unidad", max_length=20)
    tracks_lots: bool = False


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    is_active: bool
    created_at: datetime


class LotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    lot_number: str
    expiry_date: date | None


class StockMovementCreate(BaseModel):
    """Entrada/salida/ajuste simples — un solo almacén. Para mover stock
    entre almacenes, usar TransferCreate (spec: transferencia no es un tipo
    de movimiento suelto, es un par entrada+salida atómico)."""

    product_id: int
    warehouse_id: int
    movement_type: MovementTypeEnum
    quantity: Decimal = Field(..., gt=0, description="Siempre positivo — el signo lo determina movement_type")
    lot_number: str | None = Field(None, max_length=100, description="Requerido si el producto tracks_lots")
    expiry_date: date | None = None
    reference: str | None = Field(None, max_length=300)


class TransferCreate(BaseModel):
    product_id: int
    source_warehouse_id: int
    destination_warehouse_id: int
    quantity: Decimal = Field(..., gt=0)
    lot_number: str | None = Field(None, max_length=100)
    reference: str | None = Field(None, max_length=300)

    @model_validator(mode="after")
    def different_warehouses(self) -> "TransferCreate":
        if self.source_warehouse_id == self.destination_warehouse_id:
            raise ValueError("El almacén de origen y destino no pueden ser el mismo")
        return self


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    warehouse_id: int
    lot_id: int | None
    movement_type: str
    quantity: Decimal
    reference: str | None
    correlation_id: str | None
    created_at: datetime
    created_by: int | None


class StockLevelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    warehouse_id: int
    lot_id: int | None
    quantity: Decimal
    reserved_quantity: Decimal
