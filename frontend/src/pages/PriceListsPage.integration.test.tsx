/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * listas de precios: crear una lista con un precio por producto desde la
 * UI, verificar que aparece en la tarjeta con el precio y la cantidad
 * mínima correctos. Mismos caveats que los demás tests de integración
 * (sin navegador real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { PriceListsPage } from "@/pages/PriceListsPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PriceListsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PriceListsPage — flujo real de sales contra backend en 127.0.0.1:8000", () => {
  let productSku: string;
  let setupDone = false;

  beforeAll(async () => {
    // Guarda de idempotencia — mismo hallazgo real que en purchasing/inventory
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

    const suffix = Date.now();
    productSku = `PL-SKU-${suffix}`;

    await apiRequest("/inventory/products", {
      method: "POST",
      body: { sku: productSku, name: `Producto PL ${suffix}`, product_type: "facturable", unit_of_measure: "unidad", tracks_lots: false },
    });
  });

  it("crea una lista de precios desde la UI y la muestra con su precio por quiebre de volumen", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /nueva lista de precios/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /nueva lista de precios/i }));

    const suffix = Date.now();
    const listName = `Lista Mayoreo ${suffix}`;
    await user.type(screen.getByLabelText("Nombre"), listName);

    await user.click(screen.getByRole("combobox", { name: /producto precio 1/i }));
    await user.click(await screen.findByRole("option", { name: productSku }));

    const priceInputs = screen.getAllByRole("spinbutton");
    // priceInputs[0] = Precio, priceInputs[1] = Desde cant. (ya trae "1" por defecto)
    await user.type(priceInputs[0], "125.50");

    await user.click(screen.getByRole("button", { name: /^crear lista de precios$/i }));

    await waitFor(() => expect(screen.getByText(listName)).toBeInTheDocument(), { timeout: 5000 });
    await waitFor(() => expect(screen.getByText(productSku)).toBeInTheDocument());
    expect(screen.getByText("125.50")).toBeInTheDocument();
    expect(screen.getByText(/desde 1/)).toBeInTheDocument();

    // Verificación real contra el backend, no solo confiar en la UI.
    const lists = await apiRequest<Array<{ name: string; items: Array<{ unit_price: string; min_quantity: string }> }>>("/sales/price-lists");
    const created = lists.find((pl) => pl.name === listName);
    expect(created?.items[0]?.unit_price).toBe("125.50");
  });
});
