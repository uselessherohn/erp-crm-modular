/**
 * Integración real contra backend en 127.0.0.1:8000 — configurar almacén y
 * lista de precios por defecto desde el panel.
 *
 * NOTA DE ESTE CIERRE: escrito y revisado a mano, NO ejecutado — mismo
 * motivo que `WebsitePage.integration.test.tsx` (sin servidor/Postgres/
 * node_modules en este entorno). Requiere que la compañía de prueba ya
 * tenga al menos un almacén (`inventory`) y una lista de precios
 * (`sales`) creados de antemano — no los crea este test.
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { EcommercePage } from "@/pages/EcommercePage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <EcommercePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("EcommercePage — flujo real contra backend en 127.0.0.1:8000", () => {
  beforeAll(async () => {
    const tokens = await apiRequest<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: "admin@elroble.hn", password: "SuperSegura123" },
      responseSchema: schemas.TokenResponse,
    });
    setTokens(tokens.access_token, tokens.refresh_token);
  });

  it("muestra el formulario de configuración y permite guardar un almacén por defecto", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText("Almacén por defecto")).toBeInTheDocument(), { timeout: 15000 });

    const warehouseSelect = screen.getByLabelText("Almacén por defecto") as HTMLSelectElement;
    const firstRealOption = Array.from(warehouseSelect.options).find((o) => o.value !== "");
    expect(firstRealOption).toBeDefined();

    await user.selectOptions(warehouseSelect, firstRealOption!.value);
    await user.click(screen.getByRole("button", { name: /^guardar$/i }));

    await waitFor(() => expect(warehouseSelect.value).toBe(firstRealOption!.value), { timeout: 10000 });
  }, 30000);
});
