import { test, expect } from "@playwright/test";

/**
 * El flujo más básico y a la vez el que más importa cubrir con un
 * navegador REAL: CORS. jsdom (vitest) no aplica esa restricción — un
 * bug de configuración de CORS en el backend pasaría inadvertido ahí y
 * solo se vería acá (ver la nota en
 * src/pages/LoginPage.integration.test.tsx).
 */
test.describe("Login", () => {
  test("inicia sesión con credenciales válidas y llega al panel", async ({ page }) => {
    await page.goto("/login");

    await page.getByLabel(/correo/i).fill("admin@elroble.hn");
    await page.getByLabel(/contraseña/i).fill("SuperSegura123");
    await page.getByRole("button", { name: /ingresar/i }).click();

    // No queda en /login tras un login exitoso — el layout autenticado
    // redirige a /contacts por defecto (ver App.tsx, <Navigate to="/contacts">).
    await expect(page).toHaveURL(/\/contacts/, { timeout: 10_000 });
    // Algo del layout autenticado (nav lateral) debería ser visible — no
    // dependemos del label exacto de UN link, sino de que el nav exista.
    await expect(page.getByRole("link", { name: /contactos/i })).toBeVisible();
  });

  test("credenciales inválidas muestran un error y NO navegan fuera de /login", async ({ page }) => {
    await page.goto("/login");

    await page.getByLabel(/correo/i).fill("admin@elroble.hn");
    await page.getByLabel(/contraseña/i).fill("password-incorrecta");
    await page.getByRole("button", { name: /ingresar/i }).click();

    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);
  });
});
