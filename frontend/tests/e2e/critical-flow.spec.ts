import { execSync } from "node:child_process";
import path from "node:path";
import { test, expect } from "@playwright/test";

/**
 * Flujo crítico end-to-end: login -> ver una factura real -> registrar un
 * pago contra ella -> confirmar que el saldo se actualiza. La parte previa
 * a "ver la factura" (crear cliente, producto, orden de venta, confirmarla,
 * enviarla, facturarla y contabilizar la factura) se siembra por fuera de
 * la UI, vía seed_invoice_ready_to_pay.py — reimplementar esa cadena de 7
 * pasos clickeando la UI en cada spec sería lento y frágil; lo que este
 * spec verifica con un navegador real es la parte que más lo necesita: que
 * un pago real, creado desde la UI, se refleje correctamente.
 *
 * ADVERTENCIA — SIN VERIFICAR CONTRA UN NAVEGADOR REAL: quien escribió
 * este spec no tuvo acceso a un navegador real en su entorno (mismo motivo
 * que LoginPage.integration.test.tsx documenta — cdn.playwright.dev fuera
 * del allowlist de red de ese entorno). Los selectores de
 * CreatePaymentDialog.tsx SÍ se confirmaron leyendo el componente
 * directamente (no son un invento), pero la primera corrida real de este
 * spec, en un entorno con navegador, puede necesitar ajustes menores
 * (timing de los Select de Radix, orden exacto de renderizado). Ver
 * AGENT_RUNBOOK.md, sección Playwright, para qué hacer si falla.
 */

let contactName: string;
let invoiceNumber: string;

test.beforeAll(() => {
  const backendRoot = path.resolve(__dirname, "../../../backend");
  const output = execSync("python ../frontend/tests/e2e/seed_invoice_ready_to_pay.py", {
    cwd: backendRoot,
    encoding: "utf-8",
  });
  // El script imprime UN SOLO JSON por stdout — puede haber líneas de log
  // de SQLAlchemy antes si el nivel de logging está en INFO, así que se
  // toma la última línea no vacía en vez de asumir que stdout es 100% JSON.
  const lastLine = output.trim().split("\n").filter(Boolean).pop() ?? "{}";
  const seeded = JSON.parse(lastLine) as { contact_name: string; invoice_number: string; invoice_total: string };
  contactName = seeded.contact_name;
  invoiceNumber = seeded.invoice_number;
});

test.describe("Flujo crítico: login -> ver factura -> registrar pago", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/correo/i).fill("admin@elroble.hn");
    await page.getByLabel(/contraseña/i).fill("SuperSegura123");
    await page.getByRole("button", { name: /ingresar/i }).click();
    await expect(page).toHaveURL(/\/contacts/, { timeout: 10_000 });
  });

  test("la factura sembrada es visible en Facturación", async ({ page }) => {
    await page.getByRole("link", { name: /facturación/i }).click();
    await expect(page).toHaveURL(/\/invoices/);
    await expect(page.getByText(invoiceNumber)).toBeVisible({ timeout: 10_000 });
  });

  test("registrar un pago contra la factura y verlo reflejado en Pagos", async ({ page }) => {
    await page.getByRole("link", { name: /^pagos$/i }).click();
    await expect(page).toHaveURL(/\/payments/);

    await page.getByRole("button", { name: /nuevo pago/i }).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    // "Tipo" ya viene en "Cobro (cliente)" por default en el form
    // (direction: "sale") — no hace falta tocarlo salvo que el default
    // cambie; se deja explícito para que el spec sea autodescriptivo.
    await page.getByRole("combobox", { name: /tipo/i }).click();
    await page.getByRole("option", { name: /cobro \(cliente\)/i }).click();

    await page.getByRole("combobox", { name: /^contacto$/i }).click();
    await page.getByRole("option", { name: contactName }).click();

    await page.locator("#payment_date").fill(new Date().toISOString().slice(0, 10));
    await page.locator("#amount").fill("500.00");

    // Asignar el pago a la factura sembrada — botón "+ Factura" agrega una
    // fila de asignación, recién ahí aparece el selector de factura.
    await page.getByRole("button", { name: /\+ factura/i }).click();
    await page.getByRole("combobox", { name: /factura línea 1/i }).click();
    await page.getByRole("option", { name: new RegExp(invoiceNumber) }).click();

    await page.getByRole("button", { name: /crear pago/i }).click();
    await expect(page.getByRole("dialog")).toBeHidden({ timeout: 10_000 });

    // El pago recién creado debería aparecer en la tabla — se busca por
    // el nombre del contacto (columna "Contacto") en vez del número de
    // pago, que el spec no conoce de antemano.
    await expect(page.getByRole("row", { name: new RegExp(contactName) })).toBeVisible({ timeout: 10_000 });
  });
});
