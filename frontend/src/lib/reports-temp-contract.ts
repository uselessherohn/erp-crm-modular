/**
 * SHIM TEMPORAL — módulo 24 (reports). Mismo motivo y mismo TODO que
 * `website-temp-contract.ts`/`ecommerce-temp-contract.ts`: sin servidor
 * real ni acceso a npm en el entorno donde se escribió este módulo, no se
 * pudo correr el codegen real. Reemplazar por `@/lib/generated/api-types`
 * + `@/lib/generated/schemas` y BORRAR este archivo en cuanto se congele
 * `contracts/openapi.json` contra un servidor real.
 */
import { z } from "zod";

export const MetricInfo = z.object({
  key: z.string(),
  label: z.string(),
  columns: z.array(z.string()),
});
export type MetricInfo = z.infer<typeof MetricInfo>;

export const MetricDataResult = z.object({
  key: z.string(),
  columns: z.array(z.string()),
  rows: z.array(z.record(z.string(), z.unknown())),
});
export type MetricDataResult = z.infer<typeof MetricDataResult>;

export const DashboardWidget = z.object({
  widget_type: z.enum(["table", "metric"]).default("table"),
  metric_key: z.string(),
  title: z.string(),
});
export type DashboardWidget = z.infer<typeof DashboardWidget>;

export const DashboardCreate = z.object({
  name: z.string().min(1).max(200),
  widgets: z.array(DashboardWidget).default([]),
});
export type DashboardCreate = z.infer<typeof DashboardCreate>;

export const DashboardRead = z.object({
  id: z.number(),
  company_id: z.number(),
  name: z.string(),
  owner_user_id: z.number().nullable(),
  widgets: z.array(DashboardWidget),
  created_at: z.string(),
  updated_at: z.string(),
});
export type DashboardRead = z.infer<typeof DashboardRead>;
