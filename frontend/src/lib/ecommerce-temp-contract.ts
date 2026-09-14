/**
 * SHIM TEMPORAL — módulo 23 (ecommerce). Mismo motivo y mismo TODO que
 * `website-temp-contract.ts` (módulo 22): sin servidor real ni acceso a
 * npm en el entorno donde se escribió este módulo, no se pudo correr el
 * codegen real. Reemplazar por `@/lib/generated/api-types` +
 * `@/lib/generated/schemas` y BORRAR este archivo en cuanto se congele
 * `contracts/openapi.json` contra un servidor real.
 *
 * Solo cubre las rutas del panel interno (`/ecommerce/settings`) — el
 * storefront público (carrito/checkout/webhook) es, por diseño, un
 * frontend separado (spec 10) que no vive en este panel administrativo,
 * así que sus tipos no hacen falta acá.
 */
import { z } from "zod";

export const EcommerceSettingsUpdate = z.object({
  default_warehouse_id: z.number().nullable().optional(),
  default_price_list_id: z.number().nullable().optional(),
});
export type EcommerceSettingsUpdate = z.infer<typeof EcommerceSettingsUpdate>;

export const EcommerceSettingsRead = z.object({
  id: z.number(),
  company_id: z.number(),
  default_warehouse_id: z.number().nullable(),
  default_price_list_id: z.number().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type EcommerceSettingsRead = z.infer<typeof EcommerceSettingsRead>;

export const EcommerceSettingsCreated = EcommerceSettingsRead.extend({
  webhook_secret: z.string(),
});
export type EcommerceSettingsCreated = z.infer<typeof EcommerceSettingsCreated>;
