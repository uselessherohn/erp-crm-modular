import { defineConfig, devices } from "@playwright/test";

/**
 * Config de Playwright para tests/e2e/ — navegador REAL (Chromium), a
 * diferencia de src/**\/*.integration.test.tsx (vitest + jsdom, sin DOM ni
 * red de verdad). Existe justamente para cubrir lo que jsdom no puede:
 * layout real, CSS real, y sobre todo CORS real (jsdom/fetch de Node no
 * aplica esa restricción — ver la nota en LoginPage.integration.test.tsx).
 *
 * Requiere DOS cosas corriendo antes de ejecutar `npx playwright test`:
 * 1. El backend real (uvicorn) en http://127.0.0.1:8000 — igual que para
 *    `npx vitest run`.
 * 2. El frontend servido — este config lo levanta solo (ver `webServer`
 *    abajo) con `npm run preview` sobre un build de producción, más
 *    representativo de lo real que el server de `npm run dev`.
 *
 * NOTA DE RED (agent runbook): `npx playwright install --with-deps
 * chromium` necesita descargar el binario del navegador desde
 * playwright.azureedge.net / cdn.playwright.dev — si el entorno donde
 * corre esto bloquea esos hosts, la instalación falla. Confirmar acceso
 * antes de asumir que esta suite corre — ver AGENT_RUNBOOK.md, sección
 * Playwright.
 */
export default defineConfig({
  testDir: ".",
  fullyParallel: false, // los specs comparten datos sembrados por global-setup — correr en serie evita pisarse
  retries: 1,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  globalSetup: "./global-setup.ts",
  use: {
    baseURL: "http://127.0.0.1:4173", // puerto por defecto de `vite preview`
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: "npm run build && npm run preview -- --port 4173",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
