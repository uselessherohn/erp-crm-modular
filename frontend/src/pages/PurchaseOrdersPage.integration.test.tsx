/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * purchasing: crear PO (borrador), confirmar, recibir parcialmente desde
 * la UI, verificar que el stock se actualizó de verdad. Mismos caveats
 * que los demás tests de integración (sin navegador real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { PurchaseOrdersPage } from "@/pages/PurchaseOrdersPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PurchaseOrdersPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PurchaseOrdersPage — flujo real de purchasing contra backend en 127.0.0.1:8000", () => {
  let vendorName: string;
  let productSku: string;
  let warehouseName: string;
  let setupDone = false;

  beforeAll(async () => {
    // Guarda de idempotencia — mismo hallazgo real que en inventory
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
    vendorName = `Proveedor PO Test ${suffix}`;
    productSku = `PO-SKU-${suffix}`;
    warehouseName = `Bodega PO Test ${suffix}`;

    await apiRequest("/contacts", { method: "POST", body: { name: vendorName, is_vendor: true } });
    await apiRequest("/inventory/products", {
      method: "POST",
      body: { sku: productSku, name: `Producto PO ${suffix}`, product_type: "facturable", unit_of_measure: "unidad", tracks_lots: false },
    });
    await apiRequest("/inventory/warehouses", { method: "POST", body: { name: warehouseName } });
  });

  it("crea una orden de compra desde la UI, la confirma y recibe parcialmente, reflejando el stock real", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /nueva orden de compra/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /nueva orden de compra/i }));

    await user.click(screen.getByRole("combobox", { name: "Proveedor" }));
    await user.click(await screen.findByRole("option", { name: vendorName }));

    await user.click(screen.getByRole("combobox", { name: "Almacén" }));
    await user.click(await screen.findByRole("option", { name: warehouseName }));

    await user.click(screen.getByRole("combobox", { name: /producto línea 1/i }));
    await user.click(await screen.findByRole("option", { name: productSku }));

    const quantityInputs = screen.getAllByRole("spinbutton");
    await user.type(quantityInputs[0], "50"); // cantidad
    await user.type(quantityInputs[1], "8.25"); // costo unitario

    await user.click(screen.getByRole("button", { name: /^crear orden de compra$/i }));

    // La PO nueva aparece en la lista (estado "Borrador").
    await waitFor(() => expect(screen.getByText("Borrador")).toBeInTheDocument(), { timeout: 5000 });

    // Abrir el detalle y confirmar.
    await user.click(screen.getByText(vendorName));
    await waitFor(() => expect(screen.getByRole("button", { name: /^confirmar$/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /^confirmar$/i }));

    // Tras confirmar, aparece el flujo de recepción parcial.
    await waitFor(() => expect(screen.getByRole("button", { name: /^recibir$/i })).toBeInTheDocument());

    const receiveInput = screen.getByRole("spinbutton");
    await user.type(receiveInput, "20");
    await user.click(screen.getByRole("button", { name: /^recibir$/i }));

    // "20" recibido de "50" ordenado debe reflejarse en la tabla del detalle.
    await waitFor(() => expect(screen.getAllByText("20.0000").length).toBeGreaterThan(0), { timeout: 5000 });

    // Verificación real, no solo confiar en la UI: el stock-level del
    // backend debe mostrar 20 unidades en el almacén elegido.
    const levels = await apiRequest<Array<{ warehouse_id: number; quantity: string }>>("/inventory/stock-levels");
    const warehouses = await apiRequest<Array<{ id: number; name: string }>>("/inventory/warehouses");
    const warehouseId = warehouses.find((w) => w.name === warehouseName)?.id;
    const level = levels.find((l) => l.warehouse_id === warehouseId);
    expect(level?.quantity).toBe("20.0000");
  });
});
