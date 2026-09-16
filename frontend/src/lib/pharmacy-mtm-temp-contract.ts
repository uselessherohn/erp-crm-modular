/**
 * SHIM TEMPORAL — módulo 21 (pharmacy MTM). A diferencia del resto de
 * `pharmacy` (que ya usa el contrato real generado en
 * `@/lib/generated/api-types` + `@/lib/generated/schemas`, verificado
 * vía CI en el cierre del módulo 16), este módulo se agregó en una
 * sesión sin servidor real disponible para correr el codegen. Mismo
 * motivo y mismo TODO que `audit-temp-contract.ts`/`reports-temp-contract.ts`:
 * reemplazar por el contrato real y BORRAR este archivo en cuanto se
 * congele `contracts/openapi.json` contra un servidor real.
 */
import { z } from "zod";

export const MtmSessionRead = z.object({
  id: z.number(),
  company_id: z.number(),
  patient_contact_id: z.number(),
  pharmacist_user_id: z.number(),
  session_date: z.string(),
  medication_review: z.string(),
  adherence_notes: z.string().nullable(),
  adverse_effects_notes: z.string().nullable(),
  recommendations: z.string().nullable(),
  fee_amount: z.union([z.number(), z.string()]),
  currency_code: z.string(),
  status: z.enum(["open", "closed", "cancelled"]),
  closed_at: z.string().nullable(),
  cancelled_at: z.string().nullable(),
  cancel_reason: z.string().nullable(),
  created_at: z.string(),
});
export type MtmSessionRead = z.infer<typeof MtmSessionRead>;

export const MtmSessionCreate = z.object({
  patient_contact_id: z.number(),
  session_date: z.string(),
  medication_review: z.string().min(1),
  adherence_notes: z.string().nullable().optional(),
  adverse_effects_notes: z.string().nullable().optional(),
  recommendations: z.string().nullable().optional(),
  fee_amount: z.union([z.number(), z.string()]),
  currency_code: z.string().max(3).optional(),
});
export type MtmSessionCreate = z.infer<typeof MtmSessionCreate>;

export const MtmSessionCancel = z.object({
  cancel_reason: z.string().min(1).max(500),
});
export type MtmSessionCancel = z.infer<typeof MtmSessionCancel>;

export const MtmSessionClose = z.object({
  issue_date: z.string(),
  tax_rate_id: z.number().nullable().optional(),
});
export type MtmSessionClose = z.infer<typeof MtmSessionClose>;

export const MtmBillingRecordRead = z.object({
  id: z.number(),
  company_id: z.number(),
  session_id: z.number(),
  billing_mode: z.enum(["accounting_invoice", "simple_receipt"]),
  status: z.string(),
  amount: z.union([z.number(), z.string()]),
  currency_code: z.string(),
  issue_date: z.string(),
  invoice_id: z.number().nullable(),
  receipt_number: z.string().nullable(),
  cancelled_at: z.string().nullable(),
  cancel_reason: z.string().nullable(),
  created_at: z.string(),
});
export type MtmBillingRecordRead = z.infer<typeof MtmBillingRecordRead>;
