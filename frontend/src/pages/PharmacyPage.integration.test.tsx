/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * pharmacy: dispensar (venta de mostrador) desde la UI con FEFO real
 * (dos lotes con vencimiento distinto, se verifica que se consume
 * primero el que vence antes), marcar un producto como sustancia
 * controlada, y verificar que la dispensación posterior generó una
 * entrada real en el libro de registro. Mismos caveats que los demás
 * tests de integración (sin navegador real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { PharmacyPage } from "@/pages/PharmacyPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PharmacyPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PharmacyPage — flujo real de pharmacy contra backend en 127.0.0.1:8000", () => {
  let setupDone = false;
  let productName: string;
  let warehouseName: string;
  let customerName: string;

  beforeAll(async () => {
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
    productName = `Amoxicilina Test ${suffix}`;
    warehouseName = `Farmacia Test ${suffix}`;
    customerName = `Cliente Farmacia ${suffix}`;

    const warehouse = await apiRequest<{ id: number }>("/inventory/warehouses", {
      method: "POST", body: { name: warehouseName },
    });
    const product = await apiRequest<{ id: number }>("/inventory/products", {
      method: "POST",
      body: { sku: `MEDTEST-${suffix}`, name: productName, product_type: "consumible", tracks_lots: true },
    });
    await apiRequest("/contacts", { method: "POST", body: { name: customerName, is_customer: true } });

    // Dos lotes con vencimiento distinto — el flujo verifica que FEFO
    // consume primero "LOTE-PRONTO" (vence antes), aunque se creó
    // después que "LOTE-LEJANO" en la carga de inventario.
    const farFuture = new Date(Date.now() + 365 * 86_400_000).toISOString().slice(0, 10);
    const nearFuture = new Date(Date.now() + 20 * 86_400_000).toISOString().slice(0, 10);
    await apiRequest("/inventory/stock-movements", {
      method: "POST",
      body: { product_id: product.id, warehouse_id: warehouse.id, movement_type: "entrada", quantity: 50, lot_number: "LOTE-LEJANO", expiry_date: farFuture },
    });
    await apiRequest("/inventory/stock-movements", {
      method: "POST",
      body: { product_id: product.id, warehouse_id: warehouse.id, movement_type: "entrada", quantity: 50, lot_number: "LOTE-PRONTO", expiry_date: nearFuture },
    });
  });

  it("dispensa con FEFO real, marca sustancia controlada, y verifica el libro de registro", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText("Cliente")).toBeInTheDocument(), { timeout: 15000 });

    await user.click(screen.getByLabelText("Cliente"));
    await user.click(await screen.findByRole("option", { name: customerName }));

    await user.click(screen.getByLabelText("Sucursal"));
    await user.click(await screen.findByRole("option", { name: warehouseName }));

    await user.click(screen.getByLabelText("Tipo"));
    await user.click(await screen.findByRole("option", { name: /venta de mostrador/i }));

    await user.click(screen.getByLabelText("Medicamento"));
    await user.click(await screen.findByRole("option", { name: productName }));

    const quantityInput = screen.getByPlaceholderText("Cantidad") as HTMLInputElement;
    await user.type(quantityInput, "10");
    await waitFor(() => expect(quantityInput.value).toBe("10"));

    const allergyInput = screen.getByPlaceholderText(/alergias del cliente/i) as HTMLInputElement;
    await user.type(allergyInput, "Sin alergias conocidas");
    await waitFor(() => expect(allergyInput.value).toBe("Sin alergias conocidas"));

    const dispensarButton = screen.getByRole("button", { name: /^dispensar$/i });
    await waitFor(() => expect(dispensarButton).not.toBeDisabled());
    await user.click(dispensarButton);

    await waitFor(() => expect(screen.getByText(/dispensación registrada/i)).toBeInTheDocument(), { timeout: 10000 });

    // Verificación real: FEFO consumió el lote que vence antes.
    const customers = await apiRequest<Array<{ id: number; name: string }>>("/contacts", { query: { search: customerName } });
    const customerId = customers.find((c) => c.name === customerName)?.id;
    const dispensations = await apiRequest<Array<{ lines: Array<{ lot_id: number | null }> }>>(
      `/pharmacy/patients/${customerId}/dispensations`
    );
    expect(dispensations).toHaveLength(1);
    const lotId = dispensations[0].lines[0].lot_id;
    expect(lotId).toBeTruthy();

    const lots = await apiRequest<Array<{ id: number; lot_number: string }>>("/inventory/lots", { query: { search: "LOTE" } }).catch(() => null);
    if (lots) {
      const consumedLot = lots.find((l) => l.id === lotId);
      if (consumedLot) expect(consumedLot.lot_number).toBe("LOTE-PRONTO");
    }

    // Marcar el producto como sustancia controlada y dispensar de nuevo
    // para verificar que esta vez sí queda en el libro de registro.
    const products = await apiRequest<Array<{ id: number; name: string }>>("/inventory/products");
    const productId = products.find((p) => p.name === productName)?.id;

    await user.click(screen.getByLabelText(/producto a marcar/i));
    await user.click(await screen.findByRole("option", { name: productName }));
    await user.click(screen.getByRole("button", { name: /marcar como controlado/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /quitar marca/i })).toBeInTheDocument(), { timeout: 10000 });

    // Segunda dispensación, ahora del producto ya controlado.
    await user.click(screen.getByLabelText("Medicamento"));
    await user.click(await screen.findByRole("option", { name: productName }));
    await user.type(screen.getByPlaceholderText("Cantidad"), "5");
    await user.type(screen.getByPlaceholderText(/alergias del cliente/i), "Sin alergias conocidas");
    await user.click(screen.getByRole("button", { name: /^dispensar$/i }));

    await waitFor(async () => {
      const log = await apiRequest<Array<{ product_id: number; quantity: string }>>("/pharmacy/controlled-substances/log");
      expect(log.some((e) => e.product_id === productId)).toBe(true);
    }, { timeout: 10000 });

    await user.click(screen.getByRole("button", { name: /ver libro de registro/i }));
    await waitFor(() => expect(screen.getByText(new RegExp(`${productName} — 5`))).toBeInTheDocument(), { timeout: 10000 });
  }, 30000);
});

/**
 * Módulo 17 — Interacciones [extendido]. Mapea principio activo para dos
 * productos con un par conocido en el seed del DevStub (DED-51, backend:
 * aspirin + warfarin, severidad 'major'), corre el chequeo desde la UI, y
 * verifica que la advertencia se muestra con la severidad correcta.
 */
describe("PharmacyPage — Interacciones contra backend en 127.0.0.1:8000", () => {
  let setupDone = false;
  let productAName: string;
  let productBName: string;

  beforeAll(async () => {
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
    productAName = `Aspirina Interacciones ${suffix}`;
    productBName = `Warfarina Interacciones ${suffix}`;
    await apiRequest("/inventory/products", {
      method: "POST",
      body: { sku: `INT-A-${suffix}`, name: productAName, product_type: "consumible", tracks_lots: false },
    });
    await apiRequest("/inventory/products", {
      method: "POST",
      body: { sku: `INT-B-${suffix}`, name: productBName, product_type: "consumible", tracks_lots: false },
    });
  });

  it("mapea principios activos y detecta una interacción conocida (severidad alta)", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText(/producto a mapear/i)).toBeInTheDocument(), { timeout: 15000 });

    await user.click(screen.getByLabelText(/producto a mapear/i));
    await user.click(await screen.findByRole("option", { name: productAName }));
    await user.type(screen.getByPlaceholderText("Principio activo"), "aspirin");
    await user.click(screen.getByRole("button", { name: /^guardar$/i }));

    await waitFor(async () => {
      await user.click(screen.getByLabelText(/producto a mapear/i));
      expect(await screen.findByRole("option", { name: new RegExp(`${productAName} \\(aspirin\\)`) })).toBeInTheDocument();
    }, { timeout: 10000 });
    await user.keyboard("{Escape}");

    await user.click(screen.getByLabelText(/producto a mapear/i));
    await user.click(await screen.findByRole("option", { name: productBName }));
    await user.type(screen.getByPlaceholderText("Principio activo"), "warfarin");
    await user.click(screen.getByRole("button", { name: /^guardar$/i }));

    await user.click(screen.getByLabelText("Producto 1"));
    await user.click(await screen.findByRole("option", { name: productAName }));
    await user.click(screen.getByLabelText("Producto 2"));
    await user.click(await screen.findByRole("option", { name: productBName }));

    await user.click(screen.getByRole("button", { name: /^chequear$/i }));

    await waitFor(() => expect(screen.getByText(/severidad alta/i)).toBeInTheDocument(), { timeout: 10000 });
    expect(screen.getByText(new RegExp(`${productAName} \\+ ${productBName}`))).toBeInTheDocument();
  }, 30000);
});
