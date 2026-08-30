/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * cotizaciones: crear desde la UI (borrador), enviar, aceptar y convertir
 * a orden de venta, verificando que la orden resultante existe de verdad
 * en el backend. Mismos caveats que los demás tests de integración (sin
 * navegador real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { QuotesPage } from "@/pages/QuotesPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <QuotesPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function futureDateInput(daysAhead: number): string {
  const d = new Date();
  d.setDate(d.getDate() + daysAhead);
  return d.toISOString().slice(0, 10); // YYYY-MM-DD, formato de <input type="date">
}

describe("QuotesPage — flujo real de sales contra backend en 127.0.0.1:8000", () => {
  let customerName: string;
  let productSku: string;
  let warehouseName: string;
  let setupDone = false;

  beforeAll(async () => {
    // Guarda de idempotencia — mismo hallazgo real que en purchasing/inventory.
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
    customerName = `Cliente Cotización ${suffix}`;
    productSku = `QT-SKU-${suffix}`;
    warehouseName = `Bodega QT Test ${suffix}`;

    await apiRequest("/contacts", { method: "POST", body: { name: customerName, is_customer: true } });
    await apiRequest("/inventory/products", {
      method: "POST",
      body: { sku: productSku, name: `Producto QT ${suffix}`, product_type: "facturable", unit_of_measure: "unidad", tracks_lots: false },
    });
    await apiRequest("/inventory/warehouses", { method: "POST", body: { name: warehouseName } });
  });

  it("crea una cotización desde la UI, la envía, la acepta y la convierte a orden de venta real", async () => {
    // Timeout explícito más alto que el default (5000ms) — este flujo hace
    // 4 transiciones de estado reales contra Postgres, mismo criterio que
    // PurchaseOrdersPage.integration.test.tsx para su flujo de confirmar+recibir.
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /nueva cotización/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /nueva cotización/i }));

    await user.click(screen.getByRole("combobox", { name: "Cliente" }));
    await user.click(await screen.findByRole("option", { name: customerName }));

    const validUntilInput = screen.getByLabelText("Válida hasta");
    await user.type(validUntilInput, futureDateInput(30));

    await user.click(screen.getByRole("combobox", { name: /producto línea 1/i }));
    await user.click(await screen.findByRole("option", { name: productSku }));

    const numberInputs = screen.getAllByRole("spinbutton");
    await user.type(numberInputs[0], "10"); // cantidad
    await user.type(numberInputs[1], "45.00"); // precio unitario

    await user.click(screen.getByRole("button", { name: /^crear cotización$/i }));

    // La cotización nueva aparece en la lista (estado "Borrador").
    await waitFor(() => expect(screen.getByText("Borrador")).toBeInTheDocument(), { timeout: 5000 });

    // Abrir el detalle, enviar, aceptar.
    await user.click(screen.getByText(customerName));
    await waitFor(() => expect(screen.getByRole("button", { name: /^enviar$/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /^enviar$/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /^aceptar$/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /^aceptar$/i }));

    // Tras aceptar aparece el selector de almacén para convertir a orden.
    await waitFor(() => expect(screen.getByRole("combobox", { name: /almacén conversión/i })).toBeInTheDocument());
    await user.click(screen.getByRole("combobox", { name: /almacén conversión/i }));
    await user.click(await screen.findByRole("option", { name: warehouseName }));

    await user.click(screen.getByRole("button", { name: /^convertir a orden$/i }));

    // Tras convertir, la cotización pasa a "Convertida" en el diálogo (se
    // recarga el detalle porque la mutación invalida la query de la
    // cotización). Se busca dentro del diálogo específicamente — "Convertida"
    // también aparece en el subtítulo de la página y en filas de otras
    // cotizaciones ya convertidas en corridas previas de este mismo test.
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(within(dialog).getByText(/^convertida —/i)).toBeInTheDocument(), { timeout: 5000 });

    // Verificación real contra el backend: debe existir una orden de venta
    // real para este cliente. `convert_to_order` crea la orden en estado
    // "draft" (no auto-confirma — ver app/sales/services.py) con la línea
    // copiada de la cotización.
    const orders = await apiRequest<Array<{ customer_id: number; status: string; lines: Array<{ quantity: string }> }>>("/sales/sales-orders");
    const contacts = await apiRequest<Array<{ id: number; name: string }>>("/contacts");
    const customerId = contacts.find((c) => c.name === customerName)?.id;
    const createdOrder = orders.find((o) => o.customer_id === customerId);
    expect(createdOrder).toBeTruthy();
    expect(createdOrder?.status).toBe("draft");
    expect(createdOrder?.lines[0]?.quantity).toBe("10.0000");
  }, 15000);
});
