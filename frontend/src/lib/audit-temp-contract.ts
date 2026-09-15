/**
 * SHIM TEMPORAL — módulo 25 (audit). Mismo motivo y mismo TODO que
 * `reports-temp-contract.ts`/`website-temp-contract.ts`: sin servidor
 * real ni acceso a npm en el entorno donde se escribió este módulo, no
 * se pudo correr el codegen real. Reemplazar por
 * `@/lib/generated/api-types` + `@/lib/generated/schemas` y BORRAR este
 * archivo en cuanto se congele `contracts/openapi.json` contra un
 * servidor real.
 */
import { z } from "zod";

export const AuditLogRead = z.object({
  id: z.number(),
  company_id: z.number(),
  event: z.string(),
  entity_type: z.string(),
  entity_id: z.number(),
  user_id: z.number().nullable(),
  correlation_id: z.string(),
  changes: z.record(z.string(), z.unknown()).nullable(),
  created_at: z.string(),
});
export type AuditLogRead = z.infer<typeof AuditLogRead>;

export const AuditRetentionPolicyRead = z.object({
  company_id: z.number(),
  retention_days: z.number(),
  updated_at: z.string(),
});
export type AuditRetentionPolicyRead = z.infer<typeof AuditRetentionPolicyRead>;

export const AuditRetentionPolicyUpdate = z.object({
  retention_days: z.number().int().min(1).max(3650),
});
export type AuditRetentionPolicyUpdate = z.infer<typeof AuditRetentionPolicyUpdate>;

export const AuditPurgeEligibleCount = z.object({
  retention_days: z.number(),
  eligible_count: z.number(),
  excluded_medical_count: z.number(),
});
export type AuditPurgeEligibleCount = z.infer<typeof AuditPurgeEligibleCount>;
