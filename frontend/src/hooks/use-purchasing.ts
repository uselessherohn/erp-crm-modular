import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";

type PurchaseOrderRead = components["schemas"]["PurchaseOrderRead"];

// Decimal (quantity_ordered, unit_cost) produce el mismo choque de tipos
// entre openapi-typescript y Zod ya documentado en inventory — se usa
// z.infer acá también para los tipos de creación/recepción.
type PurchaseOrderCreate = z.infer<typeof schemas.PurchaseOrderCreate>;
type ReceivePurchaseOrder = z.infer<typeof schemas.ReceivePurchaseOrder>;

export function usePurchaseOrders() {
  return useQuery({
    queryKey: ["purchasing", "purchase-orders"],
    queryFn: () =>
      apiRequest<PurchaseOrderRead[]>("/purchasing/purchase-orders", {
        responseSchema: schemas.PurchaseOrderRead.array(),
      }),
  });
}

export function usePurchaseOrder(id: number | null) {
  return useQuery({
    queryKey: ["purchasing", "purchase-orders", id],
    queryFn: () =>
      apiRequest<PurchaseOrderRead>(`/purchasing/purchase-orders/${id}`, { responseSchema: schemas.PurchaseOrderRead }),
    enabled: id !== null,
  });
}

export function useCreatePurchaseOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PurchaseOrderCreate) =>
      apiRequest<PurchaseOrderRead>("/purchasing/purchase-orders", {
        method: "POST",
        body: payload,
        responseSchema: schemas.PurchaseOrderRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["purchasing", "purchase-orders"] }),
  });
}

function useTransition(action: "confirm" | "cancel" | "close") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (poId: number) =>
      apiRequest<PurchaseOrderRead>(`/purchasing/purchase-orders/${poId}/${action}`, {
        method: "POST",
        responseSchema: schemas.PurchaseOrderRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["purchasing", "purchase-orders"] }),
  });
}

export const useConfirmPurchaseOrder = () => useTransition("confirm");
export const useCancelPurchaseOrder = () => useTransition("cancel");
export const useClosePurchaseOrder = () => useTransition("close");

export function useReceivePurchaseOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ poId, payload }: { poId: number; payload: ReceivePurchaseOrder }) =>
      apiRequest<PurchaseOrderRead>(`/purchasing/purchase-orders/${poId}/receive`, {
        method: "POST",
        body: payload,
        responseSchema: schemas.PurchaseOrderRead,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["purchasing", "purchase-orders"] });
      qc.invalidateQueries({ queryKey: ["inventory", "stock-levels"] });
    },
  });
}
