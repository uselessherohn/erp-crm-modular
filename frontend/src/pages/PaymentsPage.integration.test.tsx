/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * pagos: crear una factura ya contabilizada por API, luego crear un pago
 * parcial desde la UI asignado a esa factura, contabilizarlo, y verificar
 * que el saldo de la factura se redujo en el backend real. Mismos
 * caveats que los demás tests de integración (sin navegador real, no
 * CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { PaymentsPage } from "@/pages/PaymentsPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PaymentsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PaymentsPage — flujo real de accounting contra backend en 127.0.0.1:8000", () => {
  let customerName: string;
  let invoiceNumber: string;
  let invoiceId: number;
  let setupDone = false;

  beforeAll(async () => {
    // Guarda de idempotencia — mismo hallazgo real que en purchasing/inventory/sales.
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
    customerName = `Cliente Pago ${suffix}`;
    await apiRequest("/contacts", { method: "POST", body: { name: customerName, is_customer: true } });

    const receivable = await apiRequest<{ id: number }>("/accounting/accounts", {
      method: "POST",
      body: { code: `CXC-P-${suffix}`, name: "Cuentas por Cobrar", account_type: "receivable" },
    });
    const income = await apiRequest<{ id: number }>("/accounting/accounts", {
      method: "POST",
      body: { code: `ING-P-${suffix}`, name: "Ingresos", account_type: "income" },
    });
    const cash = await apiRequest<{ id: number }>("/accounting/accounts", {
      method: "POST",
      body: { code: `CAJA-P-${suffix}`, name: "Caja", account_type: "cash_bank" },
    });
    await apiRequest("/accounting/document-account-mappings", {
      method: "POST",
      body: { document_type: "sales_invoice", role: "receivable", account_id: receivable.id },
    });
    await apiRequest("/accounting/document-account-mappings", {
      method: "POST",
      body: { document_type: "sales_invoice", role: "income", account_id: income.id },
    });
    await apiRequest("/accounting/document-account-mappings", {
      method: "POST",
      body: { document_type: "payment_received", role: "cash_bank", account_id: cash.id },
    });
    await apiRequest("/accounting/document-account-mappings", {
      method: "POST",
      body: { document_type: "payment_received", role: "receivable", account_id: receivable.id },
    });

    const contacts = await apiRequest<Array<{ id: number; name: string }>>("/contacts");
    const customerId = contacts.find((c) => c.name === customerName)?.id as number;

    const invoice = await apiRequest<{ id: number; number: string }>("/accounting/invoices", {
      method: "POST",
      body: {
        direction: "sale",
        contact_id: customerId,
        issue_date: "2026-08-26",
        lines: [{ description: "Servicio", quantity: "1", unit_price: "1000.00" }],
      },
    });
    invoiceNumber = invoice.number;
    invoiceId = invoice.id;
    await apiRequest(`/accounting/invoices/${invoiceId}/post`, { method: "POST" });
  });

  it("crea un pago parcial desde la UI, lo asigna a una factura y reduce su saldo real al contabilizarlo", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /nuevo pago/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /nuevo pago/i }));

    await user.click(screen.getByRole("combobox", { name: "Contacto" }));
    await user.click(await screen.findByRole("option", { name: customerName }));

    await user.type(screen.getByLabelText("Fecha"), "2026-08-26");
    await user.type(screen.getByLabelText("Monto"), "400.00");

    await user.click(screen.getByRole("button", { name: /\+ factura/i }));
    await user.click(screen.getByRole("combobox", { name: /factura línea 1/i }));
    await user.click(await screen.findByRole("option", { name: new RegExp(invoiceNumber) }));

    const amountInputs = screen.getAllByRole("spinbutton");
    // amountInputs[0] = Monto (ya con 400.00), amountInputs[1] = Monto aplicado de la asignación
    await user.type(amountInputs[1], "400.00");

    await user.click(screen.getByRole("button", { name: /^crear pago$/i }));

    await waitFor(() => expect(screen.getByText("Borrador")).toBeInTheDocument(), { timeout: 5000 });
    // Espera explícita a que el diálogo de creación termine de cerrarse —
    // la lista puede refrescarse (por invalidación de query) un instante
    // antes de que el diálogo se desmonte, dejando la tabla momentáneamente
    // aria-hidden detrás del overlay todavía abierto.
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /nuevo pago/i })).not.toBeInTheDocument());

    const table = screen.getByRole("table");
    await user.click(within(table).getByText(customerName));
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: /^contabilizar$/i })).toBeInTheDocument());
    await user.click(within(dialog).getByRole("button", { name: /^contabilizar$/i }));

    await waitFor(() => expect(within(dialog).getByText(/^contabilizado —/i)).toBeInTheDocument(), { timeout: 5000 });

    // Verificación real contra el backend: la factura debe reflejar el
    // saldo reducido y el estado partially_paid.
    const invoice = await apiRequest<{ balance_due: string; status: string }>(`/accounting/invoices/${invoiceId}`);
    expect(invoice.balance_due).toBe("600.00");
    expect(invoice.status).toBe("partially_paid");
  }, 15000);
});
