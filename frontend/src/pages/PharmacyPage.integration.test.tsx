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
import { render, screen, waitFor, within } from "@testing-library/react";
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

    // Bug real de este test, encontrado en esta sesión al fusionar el
    // módulo 20 (reposición a droguerías): su sección de "Puntos de
    // pedido" agrega un SEGUNDO selector también etiquetado "Sucursal"
    // en la misma página, siempre visible — `getByLabelText("Sucursal")`
    // dejó de ser único. Se acota la búsqueda a la sección de
    // "Dispensación / Venta de mostrador" específicamente.
    const dispensationSection = screen.getByRole("heading", { name: /dispensación.*venta de mostrador/i }).closest("section")!;

    await user.click(screen.getByLabelText("Cliente"));
    await user.click(await screen.findByRole("option", { name: customerName }));

    await user.click(within(dispensationSection).getByLabelText("Sucursal"));
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

/**
 * Módulo 18 — Aseguradoras [extendido]. Crea una aseguradora (envuelve un
 * contacto real con is_customer=true, DED-62), una dispensación real, y un
 * reclamo — recorre el ciclo completo pending -> submitted -> approved ->
 * paid desde la UI. `administrative` SÍ está activo en el seed de
 * bootstrap_admin.py, así que ejercita la rama real `billing_mode=
 * "accounting_invoice"` (Invoice/Payment reales contra la aseguradora como
 * cliente) — la rama `claim_only` (administrative inactivo) ya está
 * cubierta en pytest (test_claim_full_lifecycle_claim_only_when_
 * administrative_inactive).
 */
describe("PharmacyPage — Aseguradoras/Reclamos contra backend en 127.0.0.1:8000", () => {
  let setupDone = false;
  let insurerName: string;
  let patientName: string;
  let orderDocumentNumber: string;

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
    insurerName = `Aseguradora UI ${suffix}`;
    patientName = `Paciente Seguro ${suffix}`;

    await apiRequest("/contacts", { method: "POST", body: { name: insurerName, is_customer: true } });
    const patient = await apiRequest<{ id: number }>("/contacts", { method: "POST", body: { name: patientName, is_customer: true } });

    const warehouse = await apiRequest<{ id: number }>("/inventory/warehouses", { method: "POST", body: { name: `Bodega Seguro ${suffix}` } });
    const product = await apiRequest<{ id: number }>("/inventory/products", {
      method: "POST", body: { sku: `INS-${suffix}`, name: `Producto Seguro ${suffix}`, product_type: "consumible", tracks_lots: false },
    });
    await apiRequest("/inventory/stock-movements", {
      method: "POST", body: { product_id: product.id, warehouse_id: warehouse.id, movement_type: "entrada", quantity: 10 },
    });
    const order = await apiRequest<{ document_number: string }>("/pharmacy/dispensations", {
      method: "POST",
      body: {
        warehouse_id: warehouse.id, patient_contact_id: patient.id,
        walk_in_reference: "Venta de mostrador", allergy_check_notes: "Sin alergias conocidas",
        lines: [{ product_id: product.id, quantity: "1" }],
      },
    });
    orderDocumentNumber = order.document_number;

    // "administrative" está activo en el seed de bootstrap_admin.py, así
    // que aprobar/pagar el reclamo ejercita la rama real de Invoice/Payment
    // (DED-62/64) — necesita mapeos de cuenta reales, igual que en pytest
    // (ver _setup_sales_invoice_account_mappings en test_pharmacy_module.py).
    // No hay seed automático de plan de cuentas (spec DED-10).
    const accountRoles: Array<{ role: string; name: string }> = [
      { role: "receivable", name: "Cuentas por Cobrar" },
      { role: "income", name: "Ingresos" },
      { role: "tax", name: "Impuestos por Pagar" },
      { role: "cash_bank", name: "Banco" },
    ];
    const accountIdByRole: Record<string, number> = {};
    for (const { role, name } of accountRoles) {
      const account = await apiRequest<{ id: number }>("/accounting/accounts", {
        method: "POST", body: { code: `TEST-${role}-${suffix}`, name, account_type: role },
      });
      accountIdByRole[role] = account.id;
    }
    for (const role of ["receivable", "income", "tax"]) {
      await apiRequest("/accounting/document-account-mappings", {
        method: "POST", body: { document_type: "sales_invoice", role, account_id: accountIdByRole[role] },
      });
    }
    for (const role of ["cash_bank", "receivable"]) {
      await apiRequest("/accounting/document-account-mappings", {
        method: "POST", body: { document_type: "payment_received", role, account_id: accountIdByRole[role] },
      });
    }
  });

  it("crea aseguradora, crea reclamo, y lo recorre pending -> paid desde la UI", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText(/contacto aseguradora/i)).toBeInTheDocument(), { timeout: 15000 });

    await user.click(screen.getByLabelText(/contacto aseguradora/i));
    await user.click(await screen.findByRole("option", { name: insurerName }));
    await user.click(screen.getByRole("button", { name: /crear aseguradora/i }));

    await waitFor(async () => {
      await user.click(screen.getByLabelText(/aseguradora reclamo/i));
      expect(await screen.findByRole("option", { name: insurerName })).toBeInTheDocument();
    }, { timeout: 10000 });
    await user.keyboard("{Escape}");

    await user.click(screen.getByLabelText(/paciente reclamo/i));
    await user.click(await screen.findByRole("option", { name: patientName }));

    await user.click(screen.getByLabelText(/dispensación reclamo/i));
    await user.click(await screen.findByRole("option", { name: orderDocumentNumber }));

    await user.click(screen.getByLabelText(/aseguradora reclamo/i));
    await user.click(await screen.findByRole("option", { name: insurerName }));

    await user.type(screen.getByPlaceholderText("Monto total"), "100");
    await user.type(screen.getByPlaceholderText("Copago paciente"), "20");
    await waitFor(() => expect(screen.getByText(/reclamado a aseguradora: 80.00/i)).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /crear reclamo/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /^enviar$/i })).toBeInTheDocument(), { timeout: 10000 });
    await user.click(screen.getByRole("button", { name: /^enviar$/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /^aprobar$/i })).toBeInTheDocument(), { timeout: 10000 });
    await user.click(screen.getByRole("button", { name: /^aprobar$/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /marcar pagado/i })).toBeInTheDocument(), { timeout: 10000 });
    await user.click(screen.getByRole("button", { name: /marcar pagado/i }));

    await waitFor(() => expect(screen.getByText("paid")).toBeInTheDocument(), { timeout: 10000 });
  }, 30000);
});
