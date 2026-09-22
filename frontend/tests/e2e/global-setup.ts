import { execSync } from "node:child_process";
import path from "node:path";

const BACKEND_URL = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8000";
const BACKEND_ROOT = path.resolve(__dirname, "../../../backend");
const ADMIN_EMAIL = "admin@elroble.hn";
const ADMIN_PASSWORD = "SuperSegura123";

/**
 * Siembra "El Roble" + el admin de bootstrap UNA sola vez, antes de correr
 * cualquier spec — mismo criterio exacto que README.md ya documenta para
 * `npx vitest run` (src/**\/*.integration.test.tsx): sin esto, cualquier
 * intento de login devuelve "Credenciales inválidas" porque no hay ningún
 * usuario todavía.
 *
 * Idempotente: si "El Roble" + el admin YA existen (ej. esta suite ya
 * corrió antes contra la misma base), el login de prueba tiene éxito y no
 * se reintenta el seed — evita que backend/scripts/bootstrap_admin.py
 * falle por duplicados (no es idempotente él mismo — asume base fresca).
 */
export default async function globalSetup() {
  const alreadySeeded = await tryLogin();
  if (alreadySeeded) {
    console.log("[e2e/global-setup] 'El Roble' + admin ya existían — reutilizando.");
    return;
  }

  console.log("[e2e/global-setup] Sembrando 'El Roble' + admin de bootstrap...");

  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!internalApiKey) {
    throw new Error(
      "[e2e/global-setup] Falta INTERNAL_API_KEY en el entorno — es el mismo valor que " +
        "backend/.env (settings.internal_api_key). Ver AGENT_RUNBOOK.md, sección Playwright."
    );
  }

  const companyResponse = await fetch(`${BACKEND_URL}/internal/companies`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Internal-Api-Key": internalApiKey },
    body: JSON.stringify({ name: "El Roble" }),
  });
  if (!companyResponse.ok) {
    const body = await companyResponse.text();
    throw new Error(`[e2e/global-setup] POST /internal/companies falló (${companyResponse.status}): ${body}`);
  }

  // backend/scripts/bootstrap_admin.py busca "El Roble" por nombre y crea
  // el usuario admin@elroble.hn / SuperSegura123 con todos los permisos
  // necesarios para navegar el panel — correrlo como subproceso Python es
  // más simple y confiable que reimplementar esa lógica (RBAC, paquetes
  // licenciados) en TypeScript.
  execSync("python -m scripts.bootstrap_admin", {
    cwd: BACKEND_ROOT,
    stdio: "inherit",
    env: { ...process.env },
  });

  const seeded = await tryLogin();
  if (!seeded) {
    throw new Error(
      "[e2e/global-setup] El seed corrió pero el login de verificación posterior sigue fallando — " +
        "revisar el output de bootstrap_admin.py arriba."
    );
  }
  console.log("[e2e/global-setup] Listo.");
}

async function tryLogin(): Promise<boolean> {
  try {
    const response = await fetch(`${BACKEND_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
    });
    return response.ok;
  } catch {
    // Backend no responde en absoluto — se deja que el error real (no
    // "está levantado el backend?") explote más claro cuando el primer
    // spec intente conectarse, en vez de tragárselo acá.
    return false;
  }
}
