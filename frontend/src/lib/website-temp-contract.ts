/**
 * SHIM TEMPORAL — módulo 22 (website).
 *
 * El resto del frontend obtiene sus tipos (`generated/api-types.ts`) y su
 * validación runtime (`generated/schemas.ts`) de un codegen real
 * (`openapi-typescript` + `openapi-zod-client --export-schemas`) corrido
 * contra `contracts/openapi.json`, que a su vez se congela con
 * `curl http://127.0.0.1:8000/openapi.json` (Fase 2.5 — ver README.md y
 * STATE.md). Ese ciclo completo necesita un servidor real corriendo +
 * acceso a la registry de npm — ninguno de los dos estaba disponible en
 * el entorno donde se escribió este módulo (sin red, sin Postgres).
 *
 * Este archivo es un reemplazo HECHO A MANO de lo que ese codegen
 * generaría para las rutas de `website`, escrito para que coincida campo
 * por campo con `backend/app/website/schemas.py`.
 *
 * TODO bloqueante antes de dar por cerrado el módulo 22: correr el ciclo
 * real de Fase 2.5 (servidor real + codegen) y BORRAR este archivo,
 * reemplazando sus usos por `@/lib/generated/api-types` y
 * `@/lib/generated/schemas`, como hace el resto del proyecto. Mientras
 * este archivo exista, `WebsitePage.tsx` es una excepción documentada a
 * la regla "los tipos siempre vienen de codegen, nunca a mano".
 */
import { z } from "zod";

export const websitePageStatus = z.enum(["draft", "published"]);

export const WebsitePageCreate = z.object({
  slug: z
    .string()
    .min(1)
    .max(150)
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Solo minúsculas, números y guiones (kebab-case)"),
  title: z.string().min(1).max(300),
  content: z.string().default(""),
});
export type WebsitePageCreate = z.infer<typeof WebsitePageCreate>;

export const WebsitePageUpdate = z.object({
  title: z.string().min(1).max(300).optional(),
  content: z.string().optional(),
});
export type WebsitePageUpdate = z.infer<typeof WebsitePageUpdate>;

export const WebsitePageRead = z.object({
  id: z.number(),
  company_id: z.number(),
  slug: z.string(),
  title: z.string(),
  content: z.string(),
  status: websitePageStatus,
  published_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type WebsitePageRead = z.infer<typeof WebsitePageRead>;

export const WebsiteFormSubmissionRead = z.object({
  id: z.number(),
  company_id: z.number(),
  page_id: z.number().nullable(),
  form_name: z.string(),
  payload: z.record(z.string(), z.unknown()),
  contact_id: z.number(),
  created_at: z.string(),
});
export type WebsiteFormSubmissionRead = z.infer<typeof WebsiteFormSubmissionRead>;
