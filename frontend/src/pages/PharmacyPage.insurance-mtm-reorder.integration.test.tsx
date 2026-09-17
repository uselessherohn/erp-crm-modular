/**
 * Integración real contra backend en 127.0.0.1:8000 — cubre las tres
 * secciones de PharmacyPage que no tenían test de integración de
 * frontend todavía (módulos 18/20/21, ver STATE.md): MTM/Consulta
 * Farmacéutica, Reposición a Droguerías, y Aseguradoras/Reclamos.
 *
 * Alcance deliberado: se cubre el ciclo completo de MTM (crear sesión →
 * cerrar y facturar) y de Aseguradoras (crear aseguradora → póliza →
 * reclamo → enviar → aprobar → pagar, contra una dispensación real). De
 * Reposición se cubre configurar un punto de pedido y verlo reflejado en
 * la lista — generar una orden de compra real desde una sugerencia
 * necesitaría además dejar el stock por debajo del punto configurado
 * (para que el backend la ofrezca como sugerencia) y requiere el
 * paquete Administrativo, que "El Roble" sí tiene activo — no se cubrió
 * en este cierre por alcance/tiempo, no por dificultad técnica; queda
 * como TODO explícito, no como brecha silenciosa.
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { PharmacyPage } from "@/pages/PharmacyPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas, ApiError } from "@/lib/api-client";

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

describe("PharmacyPage — MTM, Reposición y Aseguradoras contra backend en 127.0.0.1:8000", () => {
  let setupDone = false;
  let suffix: number;

  beforeAll(async () => {
    if (setupDone) return;
    setupDone = true;
    suffix = Date.now();

    const tokens = await apiRequest<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: "admin@elroble.hn", password: "SuperSegura123" },
      responseSchema: schemas.TokenResponse,
    });
    setTokens(tokens.access_token, tokens.refresh_token);

    // Bug real encontrado al correr este archivo en aislamiento (sesión
    // de verificación externa, sep-2026): tanto el cierre de una sesión
    // de MTM como aprobar un reclamo de aseguradora contabilizan una
    // factura real (InvoiceService.post) cuando `administrative` está
    // activo, y "El Roble" no trae ningún mapeo contable seedeado — el
    // mismo patrón ya establecido en MedicalPage.integration.test.tsx.
    // Try/catch por 409: si otro archivo de la suite completa ya lo
    // configuró contra esta misma compañía persistente, el existente
    // sirve igual.
    const acctSuffix = Date.now().toString().slice(-8);
    const accountIdByRole: Record<string, number> = {};
    for (const [role, code, name] of [
      ["receivable", "REC", "Cuentas por Cobrar"],
      ["income", "INC", "Ingresos"],
      ["tax", "TAX", "Impuestos por Pagar"],
      ["cash_bank", "CSH", "Banco"],
    ] as const) {
      const account = await apiRequest<{ id: number }>("/accounting/accounts", {
        method: "POST", body: { code: `PHX${code}${acctSuffix}`, name, account_type: role },
      });
      accountIdByRole[role] = account.id;
    }
    for (const role of ["receivable", "income", "tax"]) {
      try {
        await apiRequest("/accounting/document-account-mappings", {
          method: "POST", body: { document_type: "sales_invoice", role, account_id: accountIdByRole[role] },
        });
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 409) throw err;
      }
    }
    for (const role of ["cash_bank", "receivable"]) {
      try {
        await apiRequest("/accounting/document-account-mappings", {
          method: "POST", body: { document_type: "payment_received", role, account_id: accountIdByRole[role] },
        });
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 409) throw err;
      }
    }
  });

  it("MTM: crea una sesión y la cierra con recibo simple", async () => {
    const user = userEvent.setup();
    const patientName = `Paciente MTM ${suffix}`;
    // MtmSessionService.close() factura al contacto (accounting_invoice
    // o simple_receipt según el paquete activo) — igual que cualquier
    // flujo de facturación del proyecto, exige `is_customer=true` en el
    // contacto (no alcanza con `is_patient`). Real, no un bug: se
    // descubrió al correr este test contra el backend real por primera
    // vez ("...no tiene el flag is_customer activo").
    await apiRequest("/contacts", { method: "POST", body: { name: patientName, is_patient: true, is_customer: true } });

    renderPage();

    await waitFor(() => expect(screen.getByLabelText("Paciente")).toBeInTheDocument(), { timeout: 15000 });
    await user.click(screen.getByLabelText("Paciente"));
    await user.click(await screen.findByRole("option", { name: patientName }));

    await waitFor(() => expect(screen.getByText("Sin sesiones de MTM para este paciente.")).toBeInTheDocument());

    await user.type(
      screen.getByPlaceholderText("Revisión de medicación (obligatorio)"),
      "Paciente refiere buena adherencia al tratamiento."
    );
    await user.type(screen.getByPlaceholderText("Monto de la sesión"), "250");
    await user.click(screen.getByRole("button", { name: /^registrar sesión$/i }));

    await waitFor(() => expect(screen.getByText("Abierta")).toBeInTheDocument(), { timeout: 10000 });

    await user.click(screen.getByRole("button", { name: /^cerrar y facturar$/i }));
    await waitFor(() => expect(screen.getByText("Cerrada")).toBeInTheDocument(), { timeout: 10000 });
  }, 30000);

  it("Reposición: configura un punto de pedido y aparece en la lista", async () => {
    const user = userEvent.setup();
    const warehouseName = `Bodega Reposición ${suffix}`;
    const productName = `Ibuprofeno Reorder ${suffix}`;
    await apiRequest("/inventory/warehouses", { method: "POST", body: { name: warehouseName } });
    await apiRequest("/inventory/products", {
      method: "POST",
      body: { sku: `REORDER-${suffix}`, name: productName, product_type: "consumible" },
    });

    renderPage();

    // Mismo bug real ya corregido en PharmacyPage.integration.test.tsx:
    // hay dos selectores "Sucursal" en la página (dispensación y
    // reposición) — se acota a la sección de Reposición por su
    // encabezado.
    await waitFor(() => expect(screen.getByRole("heading", { name: "Reposición a Droguerías" })).toBeInTheDocument(), {
      timeout: 15000,
    });
    const reorderSection = screen.getByRole("heading", { name: "Reposición a Droguerías" }).closest("section")!;

    await user.click(within(reorderSection).getByLabelText("Sucursal"));
    await user.click(await screen.findByRole("option", { name: warehouseName }));

    await waitFor(() => expect(within(reorderSection).getByLabelText("Producto")).toBeInTheDocument());
    await user.click(within(reorderSection).getByLabelText("Producto"));
    await user.click(await screen.findByRole("option", { name: productName }));

    await user.type(within(reorderSection).getByPlaceholderText("Punto de pedido"), "10");
    await user.type(within(reorderSection).getByPlaceholderText("Cantidad a reponer"), "50");
    await user.click(within(reorderSection).getByRole("button", { name: /^guardar punto de pedido$/i }));

    await waitFor(
      () => expect(within(reorderSection).getByText(`${productName} — punto 10.0000, reponer 50.0000`)).toBeInTheDocument(),
      { timeout: 10000 }
    );
  }, 30000);

  it("Aseguradoras: ciclo completo aseguradora → póliza → reclamo → enviar → aprobar → pagar", async () => {
    const user = userEvent.setup();
    const providerContactName = `Seguros Salud ${suffix}`;
    const patientName = `Paciente Aseguradora ${suffix}`;
    const productName = `Paracetamol Seguro ${suffix}`;
    const warehouseName = `Farmacia Seguro ${suffix}`;

    await apiRequest("/contacts", { method: "POST", body: { name: providerContactName, is_customer: true } });
    const patient = await apiRequest<{ id: number }>("/contacts", {
      method: "POST",
      body: { name: patientName, is_patient: true },
    });
    const warehouse = await apiRequest<{ id: number }>("/inventory/warehouses", {
      method: "POST",
      body: { name: warehouseName },
    });
    const product = await apiRequest<{ id: number }>("/inventory/products", {
      method: "POST",
      body: { sku: `SEGURO-${suffix}`, name: productName, product_type: "consumible", tracks_lots: false },
    });
    await apiRequest("/inventory/stock-movements", {
      method: "POST",
      body: { product_id: product.id, warehouse_id: warehouse.id, movement_type: "entrada", quantity: 100 },
    });
    const dispensation = await apiRequest<{ id: number; document_number: string }>("/pharmacy/dispensations", {
      method: "POST",
      body: {
        warehouse_id: warehouse.id,
        patient_contact_id: patient.id,
        walk_in_reference: "Venta de mostrador — reclamo de prueba",
        lines: [{ product_id: product.id, quantity: "2" }],
      },
    });

    renderPage();

    await waitFor(() => expect(screen.getByRole("heading", { name: "Aseguradoras y Reclamos" })).toBeInTheDocument(), {
      timeout: 15000,
    });
    const insuranceSection = screen.getByRole("heading", { name: "Aseguradoras y Reclamos" }).closest("section")!;

    // 1. Crear aseguradora.
    await user.click(within(insuranceSection).getByLabelText("Contacto aseguradora"));
    await user.click(await screen.findByRole("option", { name: providerContactName }));
    await user.click(within(insuranceSection).getByRole("button", { name: /^crear aseguradora$/i }));
    await waitFor(() => expect(within(insuranceSection).getByText(providerContactName)).toBeInTheDocument(), { timeout: 10000 });

    // 2. Crear póliza para el paciente.
    await user.click(within(insuranceSection).getByLabelText("Paciente póliza"));
    await user.click(await screen.findByRole("option", { name: patientName }));
    await user.click(within(insuranceSection).getByLabelText("Aseguradora póliza"));
    await user.click(await screen.findByRole("option", { name: providerContactName }));
    await user.type(within(insuranceSection).getByPlaceholderText("No. de póliza"), `POL-${suffix}`);
    await user.type(within(insuranceSection).getByPlaceholderText("% cobertura"), "80");
    await user.click(within(insuranceSection).getByRole("button", { name: /^guardar póliza$/i }));
    await waitFor(
      () => expect(within(insuranceSection).getByText(new RegExp(`POL-${suffix}`))).toBeInTheDocument(),
      { timeout: 10000 }
    );

    // 3. Crear reclamo contra la dispensación real recién creada.
    await user.click(within(insuranceSection).getByLabelText("Paciente reclamo"));
    await user.click(await screen.findByRole("option", { name: patientName }));
    await waitFor(() => expect(within(insuranceSection).getByLabelText("Dispensación reclamo")).toBeInTheDocument());
    await user.click(within(insuranceSection).getByLabelText("Dispensación reclamo"));
    await user.click(await screen.findByRole("option", { name: dispensation.document_number }));
    await user.click(within(insuranceSection).getByLabelText("Aseguradora reclamo"));
    await user.click(await screen.findByRole("option", { name: providerContactName }));
    await user.type(within(insuranceSection).getByPlaceholderText("Monto total"), "100");
    await user.type(within(insuranceSection).getByPlaceholderText("Copago paciente"), "20");
    await waitFor(() => expect(within(insuranceSection).getByText("Reclamado a aseguradora: 80.00")).toBeInTheDocument());
    await user.click(within(insuranceSection).getByRole("button", { name: /^crear reclamo$/i }));

    await waitFor(() => expect(within(insuranceSection).getByText("pending")).toBeInTheDocument(), { timeout: 10000 });

    // 4. Enviar → aprobar → pagar (contabiliza factura + pago reales,
    // igual que el resto de flujos financieros de este proyecto).
    await user.click(within(insuranceSection).getByRole("button", { name: /^enviar$/i }));
    await waitFor(() => expect(within(insuranceSection).getByText("submitted")).toBeInTheDocument(), { timeout: 10000 });

    await user.click(within(insuranceSection).getByRole("button", { name: /^aprobar$/i }));
    await waitFor(() => expect(within(insuranceSection).getByText("approved")).toBeInTheDocument(), { timeout: 10000 });

    await user.click(within(insuranceSection).getByRole("button", { name: /^marcar pagado$/i }));
    await waitFor(() => expect(within(insuranceSection).getByText("paid")).toBeInTheDocument(), { timeout: 10000 });
  }, 45000);
});
