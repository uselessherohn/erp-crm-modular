/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * órdenes de venta: crear desde la UI, confirmar (reserva stock real),
 * enviar la cantidad completa (descuenta físico + libera reserva) y
 * facturar, verificando el saldo de stock real contra el backend en cada
 * paso. Mismos caveats que los demás tests de integración (sin navegador
 * real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { SalesOrdersPage } from "@/pages/SalesOrdersPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SalesOrdersPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SalesOrdersPage — flujo real de sales contra backend en 127.0.0.1:8000", () => {
  let customerName: string;
  let productSku: string;
  let warehouseName: string;
  let warehouseId: number;
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
    customerName = `Cliente OV Test ${suffix}`;
    productSku = `OV-SKU-${suffix}`;
    warehouseName = `Bodega OV Test ${suffix}`;

    await apiRequest("/contacts", { method: "POST", body: { name: customerName, is_customer: true } });
    const product = await apiRequest<{ id: number }>("/inventory/products", {
      method: "POST",
      body: { sku: productSku, name: `Producto OV ${suffix}`, product_type: "facturable", unit_of_measure: "unidad", tracks_lots: false },
    });
    const warehouse = await apiRequest<{ id: number }>("/inventory/warehouses", { method: "POST", body: { name: warehouseName } });
    warehouseId = warehouse.id;

    // Stock inicial real — sin esto la confirmación de la orden (que reserva
    // contra disponible) rechazaría por insuficiencia.
    await apiRequest("/inventory/stock-movements", {
      method: "POST",
      body: { product_id: product.id, warehouse_id: warehouseId, movement_type: "entrada", quantity: 30 },
    });
  });

  it("crea una orden de venta desde la UI, la confirma, la envía completa y la factura, reflejando el stock real", async () => {
    // Timeout explícito — este flujo hace 4 transiciones de estado reales
    // contra Postgres (confirmar, enviar, facturar) más las verificaciones
    // de stock en cada paso, igual que el equivalente en QuotesPage.
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /nueva orden de venta/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /nueva orden de venta/i }));

    await user.click(screen.getByRole("combobox", { name: "Cliente" }));
    await user.click(await screen.findByRole("option", { name: customerName }));

    await user.click(screen.getByRole("combobox", { name: "Almacén" }));
    await user.click(await screen.findByRole("option", { name: warehouseName }));

    await user.click(screen.getByRole("combobox", { name: /producto línea 1/i }));
    await user.click(await screen.findByRole("option", { name: productSku }));

    const numberInputs = screen.getAllByRole("spinbutton");
    await user.type(numberInputs[0], "10"); // cantidad
    await user.type(numberInputs[1], "60.00"); // precio unitario

    await user.click(screen.getByRole("button", { name: /^crear orden de venta$/i }));

    // La orden nueva aparece en la lista (estado "Borrador").
    await waitFor(() => expect(screen.getByText("Borrador")).toBeInTheDocument(), { timeout: 5000 });
    // Espera explícita a que el diálogo de creación termine de cerrarse —
    // la lista puede refrescarse (por invalidación de query) un instante
    // antes de que el diálogo se desmonte, dejando la tabla momentáneamente
    // aria-hidden detrás del overlay todavía abierto (hallazgo real de la
    // Fase 4 de accounting, mismo patrón aplicado acá retroactivamente).
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /nueva orden de venta/i })).not.toBeInTheDocument());

    // Abrir el detalle y confirmar (esto reserva stock, no lo descuenta).
    // Se busca la fila específicamente dentro de la tabla — el mismo nombre
    // de cliente puede quedar también en el trigger del combobox si el
    // diálogo de creación no se desmontó del todo tras cerrarse.
    const table = screen.getByRole("table");
    await user.click(within(table).getByText(customerName));
    await waitFor(() => expect(screen.getByRole("button", { name: /^confirmar$/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /^confirmar$/i }));

    // Tras confirmar, disponible = 30 - 10 reservadas = 20 (physical sigue en 30).
    await waitFor(async () => {
      const levels = await apiRequest<Array<{ warehouse_id: number; quantity: string; reserved_quantity: string }>>("/inventory/stock-levels");
      const level = levels.find((l) => l.warehouse_id === warehouseId);
      expect(level?.quantity).toBe("30.0000");
      expect(level?.reserved_quantity).toBe("10.0000");
    }, { timeout: 5000 });

    // Enviar la cantidad completa desde el diálogo de detalle.
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(screen.getByRole("spinbutton")).toBeInTheDocument());
    await user.type(screen.getByRole("spinbutton"), "10");
    await user.click(screen.getByRole("button", { name: /^enviar$/i }));

    // Envío completo -> estado "enviado". Se busca dentro del diálogo — el
    // subtítulo de la página también contiene "Enviada"/"Facturada" como
    // parte de la leyenda del flujo de estados.
    await waitFor(() => expect(within(dialog).getByText(/enviada/i)).toBeInTheDocument(), { timeout: 5000 });
    await waitFor(async () => {
      const levels = await apiRequest<Array<{ warehouse_id: number; quantity: string; reserved_quantity: string }>>("/inventory/stock-levels");
      const level = levels.find((l) => l.warehouse_id === warehouseId);
      expect(level?.quantity).toBe("20.0000");
      expect(level?.reserved_quantity).toBe("0.0000");
    }, { timeout: 5000 });

    // Facturar.
    await waitFor(() => expect(screen.getByRole("button", { name: /^facturar$/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /^facturar$/i }));
    await waitFor(() => expect(within(dialog).getByText(/facturada/i)).toBeInTheDocument(), { timeout: 5000 });

    // Verificación final real contra el backend.
    const orders = await apiRequest<Array<{ customer_id: number; status: string }>>("/sales/sales-orders");
    const contacts = await apiRequest<Array<{ id: number; name: string }>>("/contacts");
    const customerId = contacts.find((c) => c.name === customerName)?.id;
    const finalOrder = orders.find((o) => o.customer_id === customerId);
    expect(finalOrder?.status).toBe("facturado");
  }, 15000);
});
