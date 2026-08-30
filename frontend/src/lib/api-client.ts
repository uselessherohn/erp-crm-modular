/**
 * Cliente HTTP delgado. NO reemplaza el codegen: los tipos vienen de
 * `generated/api-types.ts` (openapi-typescript) y la validación runtime de
 * `generated/schemas.ts` (openapi-zod-client, --export-schemas) — ambos
 * generados desde contracts/openapi.json (Fase 2.5). Este archivo es
 * glue code hecho a mano (fetch + manejo de tokens), no contrato.
 */
import { schemas } from "@/lib/generated/schemas";
import type { z } from "zod";
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from "@/lib/auth-store";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function parseErrorBody(res: Response): Promise<never> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // sin body JSON — error genérico
  }
  const error = (body as { error?: { code: string; message: string; details?: unknown } } | null)?.error;

  // Para VALIDATION_ERROR con detalle de Pydantic (details.errors[]), el
  // mensaje específico (ej. "al menos un rol activo") es más útil para el
  // usuario que el genérico "Error de validación en la solicitud" — se
  // extrae acá el primer mensaje concreto si existe, sin perder el
  // genérico como fallback.
  let message = error?.message ?? res.statusText;
  const details = error?.details as { errors?: Array<{ msg?: string }> } | undefined;
  const firstDetailMsg = details?.errors?.[0]?.msg;
  if (firstDetailMsg) {
    // Pydantic prefija "Value error, " a los mensajes de model_validator —
    // se recorta para no mostrarlo tal cual en la UI.
    message = firstDetailMsg.replace(/^Value error,\s*/, "");
  }

  throw new ApiError(error?.code ?? "UNKNOWN_ERROR", message, res.status, error?.details);
}

let refreshPromise: Promise<void> | null = null;

async function refreshAccessToken(): Promise<void> {
  const raw = getRefreshToken();
  if (!raw) throw new ApiError("NO_REFRESH_TOKEN", "Sin refresh token", 401);

  const res = await fetch(`${BASE_URL}/auth/refresh?raw_refresh_token=${encodeURIComponent(raw)}`, {
    method: "POST",
  });
  if (!res.ok) {
    clearTokens();
    await parseErrorBody(res);
  }
  const data = schemas.TokenResponse.parse(await res.json());
  setTokens(data.access_token, data.refresh_token);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  auth?: boolean;
  /** Schema Zod (generado) para validar la respuesta en runtime. */
  responseSchema?: z.ZodTypeAny;
}

export async function apiRequest<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, auth = true, responseSchema } = options;

  const url = new URL(path, BASE_URL);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }

  const doFetch = async () => {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (auth) {
      const token = getAccessToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    return fetch(url.toString(), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let res = await doFetch();

  // Un solo intento de refresh automático ante 401 con token expirado —
  // evita loops infinitos si el refresh también falla.
  if (res.status === 401 && auth && getRefreshToken()) {
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }
    try {
      await refreshPromise;
      res = await doFetch();
    } catch {
      // el refresh falló — se propaga el 401 original abajo
    }
  }

  if (!res.ok) {
    await parseErrorBody(res);
  }

  if (res.status === 204) return undefined as T;

  const data = await res.json();
  return responseSchema ? (responseSchema.parse(data) as T) : (data as T);
}

export { schemas };
