/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * configuración de accounting: crear una cuenta contable, una tasa de
 * impuesto y un mapeo documento→cuenta desde la UI, verificando cada uno
 * contra el backend real. Mismos caveats que los demás tests de
 * integración (sin navegador real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AccountsPage } from "@/pages/AccountsPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AccountsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AccountsPage — configuración real de accounting contra backend en 127.0.0.1:8000", () => {
  let setupDone = false;

  beforeAll(async () => {
    // Guarda de idempotencia — mismo hallazgo real que en purchasing/inventory/sales
    // (beforeAll puede dispararse más de una vez en Vitest 4.x).
    if (setupDone) return;
    setupDone = true;

    const tokens = await apiRequest<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: "admin@elroble.hn", password: "SuperSegura123" },
      responseSchema: schemas.TokenResponse,
    });
    setTokens(tokens.access_token, tokens.refresh_token);
  });

  it("crea una cuenta, una tasa de impuesto y un mapeo documento→cuenta desde la UI", async () => {
    const user = userEvent.setup();
    renderPage();

    const suffix = Date.now();
    const accountCode = `TEST-${suffix}`;
    const accountName = `Cuenta Test ${suffix}`;

    // --- Crear cuenta contable ---
    await waitFor(() => expect(screen.getByRole("button", { name: /nueva cuenta/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /nueva cuenta/i }));
    await user.type(screen.getByLabelText("Código"), accountCode);
    await user.type(screen.getByLabelText("Nombre"), accountName);
    await user.click(screen.getByRole("combobox", { name: "Rol" }));
    await user.click(await screen.findByRole("option", { name: "Cuentas por cobrar" }));
    await user.click(screen.getByRole("button", { name: /^crear cuenta$/i }));

    await waitFor(() => expect(screen.getByText(accountName)).toBeInTheDocument(), { timeout: 5000 });

    const accounts = await apiRequest<Array<{ id: number; code: string; account_type: string }>>("/accounting/accounts");
    const createdAccount = accounts.find((a) => a.code === accountCode);
    expect(createdAccount).toBeTruthy();
    expect(createdAccount?.account_type).toBe("receivable");

    // --- Crear tasa de impuesto ---
    const taxName = `ISV Test ${suffix}`;
    await user.click(screen.getByRole("button", { name: /nueva tasa/i }));
    await user.type(screen.getByLabelText("Nombre"), taxName);
    await user.type(screen.getByLabelText("Porcentaje"), "15");
    await user.click(screen.getByRole("button", { name: /^crear tasa$/i }));

    await waitFor(() => expect(screen.getByText(taxName)).toBeInTheDocument(), { timeout: 5000 });
    const taxRates = await apiRequest<Array<{ name: string; rate: string }>>("/accounting/tax-rates");
    const createdTax = taxRates.find((t) => t.name === taxName);
    expect(createdTax?.rate).toBe("15.00");

    // --- Crear mapeo documento→cuenta ---
    await user.click(screen.getByRole("button", { name: /nuevo mapeo/i }));
    await user.click(screen.getByRole("combobox", { name: "Documento" }));
    await user.click(await screen.findByRole("option", { name: "Factura de venta" }));
    await user.click(screen.getByRole("combobox", { name: "Rol" }));
    await user.click(await screen.findByRole("option", { name: "Cuentas por cobrar" }));
    await user.click(screen.getByRole("combobox", { name: "Cuenta" }));
    await user.click(await screen.findByRole("option", { name: new RegExp(accountCode) }));
    await user.click(screen.getByRole("button", { name: /^guardar mapeo$/i }));

    // Timeout generoso — esta suite corre en serie (fileParallelism:false)
    // contra un backend/Postgres COMPARTIDO sin truncar entre archivos, así
    // que cuantos más módulos de integración se agreguen al proyecto, más
    // datos acumulados hay que renderizar en esta tabla antes de esta
    // aserción. No es una regresión de este test — es un costo estructural
    // conocido del enfoque de integración real sin fixtures aisladas.
    await waitFor(() => expect(screen.getByText("Factura de venta")).toBeInTheDocument(), { timeout: 20000 });

    const mappings = await apiRequest<Array<{ document_type: string; role: string; account_id: number }>>(
      "/accounting/document-account-mappings"
    );
    const createdMapping = mappings.find((m) => m.document_type === "sales_invoice" && m.role === "receivable");
    expect(createdMapping?.account_id).toBe(createdAccount?.id);
  }, 30000);
});
