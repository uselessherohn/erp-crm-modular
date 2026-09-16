/**
 * SHIM TEMPORAL — módulo 20 (pharmacy, Reposición a Droguerías). Mismo
 * motivo que `pharmacy-mtm-temp-contract.ts`: esta parte de `pharmacy`
 * no pasó por el CI que generó el contrato real del módulo 16. Borrar
 * en cuanto se congele `contracts/openapi.json` contra un servidor real.
 */
import { z } from "zod";

export const ReorderPointRead = z.object({
  id: z.number(),
  company_id: z.number(),
  product_id: z.number(),
  warehouse_id: z.number(),
  reorder_point: z.union([z.number(), z.string()]),
  reorder_quantity: z.union([z.number(), z.string()]),
  preferred_vendor_id: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type ReorderPointRead = z.infer<typeof ReorderPointRead>;

export const ReorderPointUpsert = z.object({
  product_id: z.number(),
  warehouse_id: z.number(),
  reorder_point: z.union([z.number(), z.string()]),
  reorder_quantity: z.union([z.number(), z.string()]),
  preferred_vendor_id: z.number().nullable().optional(),
});
export type ReorderPointUpsert = z.infer<typeof ReorderPointUpsert>;

export const ReorderSuggestionRead = z.object({
  product_id: z.number(),
  warehouse_id: z.number(),
  available_quantity: z.union([z.number(), z.string()]),
  reorder_point: z.union([z.number(), z.string()]),
  reorder_quantity: z.union([z.number(), z.string()]),
  below_by: z.union([z.number(), z.string()]),
  preferred_vendor_id: z.number().nullable(),
});
export type ReorderSuggestionRead = z.infer<typeof ReorderSuggestionRead>;

export const ReorderPurchaseOrderGenerate = z.object({
  warehouse_id: z.number(),
  vendor_id: z.number(),
  currency_code: z.string().max(3).optional(),
  expected_date: z.string().nullable().optional(),
  lines: z.array(z.object({
    product_id: z.number(),
    quantity: z.union([z.number(), z.string()]),
    unit_cost: z.union([z.number(), z.string()]),
  })).min(1),
});
export type ReorderPurchaseOrderGenerate = z.infer<typeof ReorderPurchaseOrderGenerate>;
