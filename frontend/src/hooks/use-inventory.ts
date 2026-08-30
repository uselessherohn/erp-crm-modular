import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";

type CategoryRead = components["schemas"]["CategoryRead"];
type CategoryCreate = components["schemas"]["CategoryCreate"];
type WarehouseRead = components["schemas"]["WarehouseRead"];
type WarehouseCreate = components["schemas"]["WarehouseCreate"];
type ProductRead = components["schemas"]["ProductRead"];
type ProductCreate = components["schemas"]["ProductCreate"];
type StockMovementRead = components["schemas"]["StockMovementRead"];
type StockLevelRead = components["schemas"]["StockLevelRead"];

// quantity (Decimal en Pydantic -> unión number|string en Zod) produce
// tipos ligeramente distintos entre openapi-typescript y el z.infer del
// schema generado — se usa la variante Zod acá, la misma que .parse()
// devuelve en las páginas que llaman a estos hooks (mismo origen de tipo
// en ambos lados en vez de dos generadores independientes divergiendo).
type StockMovementCreate = z.infer<typeof schemas.StockMovementCreate>;
type TransferCreate = z.infer<typeof schemas.TransferCreate>;

export function useCategories() {
  return useQuery({
    queryKey: ["inventory", "categories"],
    queryFn: () => apiRequest<CategoryRead[]>("/inventory/categories", { responseSchema: schemas.CategoryRead.array() }),
  });
}

export function useCreateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CategoryCreate) =>
      apiRequest<CategoryRead>("/inventory/categories", { method: "POST", body: payload, responseSchema: schemas.CategoryRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", "categories"] }),
  });
}

export function useWarehouses() {
  return useQuery({
    queryKey: ["inventory", "warehouses"],
    queryFn: () => apiRequest<WarehouseRead[]>("/inventory/warehouses", { responseSchema: schemas.WarehouseRead.array() }),
  });
}

export function useCreateWarehouse() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: WarehouseCreate) =>
      apiRequest<WarehouseRead>("/inventory/warehouses", { method: "POST", body: payload, responseSchema: schemas.WarehouseRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", "warehouses"] }),
  });
}

export function useProducts() {
  return useQuery({
    queryKey: ["inventory", "products"],
    queryFn: () => apiRequest<ProductRead[]>("/inventory/products", { responseSchema: schemas.ProductRead.array() }),
  });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProductCreate) =>
      apiRequest<ProductRead>("/inventory/products", { method: "POST", body: payload, responseSchema: schemas.ProductRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", "products"] }),
  });
}

export function useStockLevels(params: { productId?: number; warehouseId?: number } = {}) {
  return useQuery({
    queryKey: ["inventory", "stock-levels", params],
    queryFn: () =>
      apiRequest<StockLevelRead[]>("/inventory/stock-levels", {
        query: { product_id: params.productId, warehouse_id: params.warehouseId },
        responseSchema: schemas.StockLevelRead.array(),
      }),
  });
}

export function useCreateStockMovement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: StockMovementCreate) =>
      apiRequest<StockMovementRead>("/inventory/stock-movements", {
        method: "POST",
        body: payload,
        responseSchema: schemas.StockMovementRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", "stock-levels"] }),
  });
}

export function useCreateTransfer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TransferCreate) =>
      apiRequest<StockMovementRead[]>("/inventory/stock-transfers", {
        method: "POST",
        body: payload,
        responseSchema: schemas.StockMovementRead.array(),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", "stock-levels"] }),
  });
}
