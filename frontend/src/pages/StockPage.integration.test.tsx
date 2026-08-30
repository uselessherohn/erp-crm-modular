/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * inventory: crear producto, crear almacén, registrar entrada, ver el
 * saldo reflejado en StockPage. Mismos caveats que los demás tests de
 * integración (sin navegador real, no verifica CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { StockPage } from "@/pages/StockPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderStockPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <StockPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("StockPage — flujo real de inventory contra backend en 127.0.0.1:8000", () => {
  let productSku: string;
  let productName: string;
  let warehouseName: string;
  let setupDone = false;

  beforeAll(async () => {
    // Guarda de idempotencia: se observó empíricamente que beforeAll podía
    // dispararse dos veces en una sola invocación de "vitest run" (dos
    // POST /inventory/products reales con SKUs distintos, 7s aparte,
    // confirmado revisando la tabla products directamente) — mecanismo
    // interno de Vitest 4.x no identificado con certeza, no reproducible
    // vía curl directo contra el backend. Esta guarda hace el setup seguro
    // ante una posible doble invocación, sea cual sea la causa exacta.
    if (setupDone) return;
    setupDone = true;

    const tokens = await apiRequest<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: "admin@elroble.hn", password: "SuperSegura123" },
      responseSchema: schemas.TokenResponse,
    });
    setTokens(tokens.access_token, tokens.refresh_token);

    // name también único (no solo sku/warehouse): dos corridas de este
    // test contra la misma DB sin truncar entre medio dejaban dos
    // productos con el mismo `name` visible, volviendo getByText ambiguo
    // — bug de higiene del test, no de la app, encontrado al reproducir.
    const suffix = Date.now();
    productSku = `SKU-${suffix}`;
    productName = `Martillo de Bola 16oz ${suffix}`;
    warehouseName = `Bodega Central ${suffix}`;

    const product = await apiRequest<{ id: number }>("/inventory/products", {
      method: "POST",
      body: { sku: productSku, name: productName, product_type: "facturable", unit_of_measure: "unidad", tracks_lots: false },
    });
    const warehouse = await apiRequest<{ id: number }>("/inventory/warehouses", {
      method: "POST",
      body: { name: warehouseName },
    });

    // Entrada real vía API — la UI de StockPage solo necesita reflejar el
    // saldo resultante, la creación del movimiento en sí ya está probada
    // exhaustivamente (con concurrencia) en el backend.
    await apiRequest("/inventory/stock-movements", {
      method: "POST",
      body: { product_id: product.id, warehouse_id: warehouse.id, movement_type: "entrada", quantity: 75 },
    });
  });

  it("refleja el saldo real tras una entrada de stock", async () => {
    renderStockPage();
    await waitFor(() => expect(screen.getByText(productName)).toBeInTheDocument());
    expect(screen.getByText(warehouseName)).toBeInTheDocument();
    expect(screen.getByText("75.0000")).toBeInTheDocument();
  });

  it("registra un movimiento nuevo desde la UI y actualiza el saldo sin recargar", async () => {
    const user = userEvent.setup();
    renderStockPage();

    await waitFor(() => expect(screen.getByText(productName)).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /registrar movimiento/i }));

    // Radix Select no es un <select> nativo — se abre por click y se elige
    // la opción por texto visible, como haría una persona real. Se
    // consulta por role="option" (no getByText): Radix duplica el texto de
    // cada opción en un <span> interno (mismo patrón de "nodo de medición"
    // que el trigger) — getByText matchea AMBOS y revienta con "multiple
    // elements found". Bug real de test encontrado al ejecutarlo.
    await user.click(screen.getByRole("combobox", { name: "Producto" }));
    await user.click(await screen.findByRole("option", { name: new RegExp(productSku) }));

    await user.click(screen.getByRole("combobox", { name: "Almacén" }));
    await user.click(await screen.findByRole("option", { name: warehouseName }));

    await user.click(screen.getByRole("combobox", { name: "Tipo de movimiento" }));
    await user.click(await screen.findByRole("option", { name: "Entrada" }));

    await user.type(screen.getByLabelText(/cantidad/i), "25");
    await user.click(screen.getByRole("button", { name: /^registrar$/i }));

    await waitFor(() => expect(screen.getByText("100.0000")).toBeInTheDocument(), { timeout: 5000 });
  });
});
