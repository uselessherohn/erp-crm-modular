import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";

type PriceListRead = components["schemas"]["PriceListRead"];
type QuoteRead = components["schemas"]["QuoteRead"];
type SalesOrderRead = components["schemas"]["SalesOrderRead"];

type PriceListCreate = z.infer<typeof schemas.PriceListCreate>;
type QuoteCreate = z.infer<typeof schemas.QuoteCreate>;
type SalesOrderCreate = z.infer<typeof schemas.SalesOrderCreate>;
type ShipSalesOrder = z.infer<typeof schemas.ShipSalesOrder>;

export function usePriceLists() {
  return useQuery({
    queryKey: ["sales", "price-lists"],
    queryFn: () => apiRequest<PriceListRead[]>("/sales/price-lists", { responseSchema: schemas.PriceListRead.array() }),
  });
}

export function useCreatePriceList() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PriceListCreate) =>
      apiRequest<PriceListRead>("/sales/price-lists", { method: "POST", body: payload, responseSchema: schemas.PriceListRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales", "price-lists"] }),
  });
}

export function useQuotes() {
  return useQuery({
    queryKey: ["sales", "quotes"],
    queryFn: () => apiRequest<QuoteRead[]>("/sales/quotes", { responseSchema: schemas.QuoteRead.array() }),
  });
}

export function useQuote(id: number | null) {
  return useQuery({
    queryKey: ["sales", "quotes", id],
    queryFn: () => apiRequest<QuoteRead>(`/sales/quotes/${id}`, { responseSchema: schemas.QuoteRead }),
    enabled: id !== null,
  });
}

export function useCreateQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: QuoteCreate) =>
      apiRequest<QuoteRead>("/sales/quotes", { method: "POST", body: payload, responseSchema: schemas.QuoteRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales", "quotes"] }),
  });
}

function useQuoteTransition(action: "send" | "accept" | "cancel") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (quoteId: number) =>
      apiRequest<QuoteRead>(`/sales/quotes/${quoteId}/${action}`, { method: "POST", responseSchema: schemas.QuoteRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales", "quotes"] }),
  });
}

export const useSendQuote = () => useQuoteTransition("send");
export const useAcceptQuote = () => useQuoteTransition("accept");
export const useCancelQuote = () => useQuoteTransition("cancel");

export function useConvertQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ quoteId, warehouseId }: { quoteId: number; warehouseId: number }) =>
      apiRequest<SalesOrderRead>(`/sales/quotes/${quoteId}/convert`, {
        method: "POST",
        query: { warehouse_id: warehouseId },
        responseSchema: schemas.SalesOrderRead,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sales", "quotes"] });
      qc.invalidateQueries({ queryKey: ["sales", "sales-orders"] });
    },
  });
}

export function useSalesOrders() {
  return useQuery({
    queryKey: ["sales", "sales-orders"],
    queryFn: () => apiRequest<SalesOrderRead[]>("/sales/sales-orders", { responseSchema: schemas.SalesOrderRead.array() }),
  });
}

export function useSalesOrder(id: number | null) {
  return useQuery({
    queryKey: ["sales", "sales-orders", id],
    queryFn: () => apiRequest<SalesOrderRead>(`/sales/sales-orders/${id}`, { responseSchema: schemas.SalesOrderRead }),
    enabled: id !== null,
  });
}

export function useCreateSalesOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SalesOrderCreate) =>
      apiRequest<SalesOrderRead>("/sales/sales-orders", { method: "POST", body: payload, responseSchema: schemas.SalesOrderRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sales", "sales-orders"] }),
  });
}

function useOrderTransition(action: "confirm" | "start-preparation" | "invoice" | "cancel") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orderId: number) =>
      apiRequest<SalesOrderRead>(`/sales/sales-orders/${orderId}/${action}`, { method: "POST", responseSchema: schemas.SalesOrderRead }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sales", "sales-orders"] });
      qc.invalidateQueries({ queryKey: ["inventory", "stock-levels"] });
    },
  });
}

export const useConfirmSalesOrder = () => useOrderTransition("confirm");
export const useStartPreparationSalesOrder = () => useOrderTransition("start-preparation");
export const useInvoiceSalesOrder = () => useOrderTransition("invoice");
export const useCancelSalesOrder = () => useOrderTransition("cancel");

export function useShipSalesOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, payload }: { orderId: number; payload: ShipSalesOrder }) =>
      apiRequest<SalesOrderRead>(`/sales/sales-orders/${orderId}/ship`, {
        method: "POST",
        body: payload,
        responseSchema: schemas.SalesOrderRead,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sales", "sales-orders"] });
      qc.invalidateQueries({ queryKey: ["inventory", "stock-levels"] });
    },
  });
}
