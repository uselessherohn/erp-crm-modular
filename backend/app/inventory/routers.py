from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_permission
from app.core.models import User
from app.inventory import schemas
from app.inventory.services import CategoryService, ProductService, StockService, WarehouseService

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.post("/categories", response_model=schemas.CategoryRead, status_code=201)
async def create_category(
    payload: schemas.CategoryCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("inventory:category:create")),
) -> schemas.CategoryRead:
    category = await CategoryService.create(db, company_id=company_id, payload=payload)
    return schemas.CategoryRead.model_validate(category)


@router.get("/categories", response_model=list[schemas.CategoryRead])
async def list_categories(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("inventory:category:list")),
) -> list[schemas.CategoryRead]:
    categories = await CategoryService.list(db, company_id=company_id)
    return [schemas.CategoryRead.model_validate(c) for c in categories]


@router.post("/warehouses", response_model=schemas.WarehouseRead, status_code=201)
async def create_warehouse(
    payload: schemas.WarehouseCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("inventory:warehouse:create")),
) -> schemas.WarehouseRead:
    warehouse = await WarehouseService.create(db, company_id=company_id, payload=payload)
    return schemas.WarehouseRead.model_validate(warehouse)


@router.get("/warehouses", response_model=list[schemas.WarehouseRead])
async def list_warehouses(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("inventory:warehouse:list")),
) -> list[schemas.WarehouseRead]:
    warehouses = await WarehouseService.list(db, company_id=company_id)
    return [schemas.WarehouseRead.model_validate(w) for w in warehouses]


@router.post("/products", response_model=schemas.ProductRead, status_code=201)
async def create_product(
    payload: schemas.ProductCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("inventory:product:create")),
) -> schemas.ProductRead:
    product = await ProductService.create(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.ProductRead.model_validate(product)


@router.get("/products", response_model=list[schemas.ProductRead])
async def list_products(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("inventory:product:list")),
) -> list[schemas.ProductRead]:
    products = await ProductService.list(db, company_id=company_id)
    return [schemas.ProductRead.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=schemas.ProductRead)
async def get_product(
    product_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("inventory:product:read")),
) -> schemas.ProductRead:
    product = await ProductService.get(db, company_id=company_id, product_id=product_id)
    return schemas.ProductRead.model_validate(product)


@router.post("/stock-movements", response_model=schemas.StockMovementRead, status_code=201)
async def create_stock_movement(
    payload: schemas.StockMovementCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("inventory:stock:write")),
) -> schemas.StockMovementRead:
    movement = await StockService.record_movement(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.StockMovementRead.model_validate(movement)


@router.post("/stock-transfers", response_model=list[schemas.StockMovementRead], status_code=201)
async def create_transfer(
    payload: schemas.TransferCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("inventory:stock:write")),
) -> list[schemas.StockMovementRead]:
    movements = await StockService.transfer(db, company_id=company_id, payload=payload, created_by=actor.id)
    return [schemas.StockMovementRead.model_validate(m) for m in movements]


@router.get("/stock-levels", response_model=list[schemas.StockLevelRead])
async def list_stock_levels(
    product_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("inventory:stock:read")),
) -> list[schemas.StockLevelRead]:
    levels = await StockService.get_levels(db, company_id=company_id, product_id=product_id, warehouse_id=warehouse_id)
    return [schemas.StockLevelRead.model_validate(lvl) for lvl in levels]
