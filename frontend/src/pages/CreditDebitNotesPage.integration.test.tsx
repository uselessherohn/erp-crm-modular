/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * notas de crédito: crear una factura ya contabilizada por API, luego
 * crear una nota de crédito desde la UI relacionada a esa factura,
 * contabilizarla, y verificar que queda "posted" con su propio asiento
 * en el backend real. Mismos caveats que los demás tests de integración
 * (sin navegador real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { CreditDebitNotesPage } from "@/pages/CreditDebitNotesPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CreditDebitNotesPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CreditDebitNotesPage — flujo real de accounting contra backend en 127.0.0.1:8000", () => {
  let customerName: string;
  let invoiceNumber: string;
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
    customerName = `Cliente Nota ${suffix}`;
    await apiRequest("/contacts", { method: "POST", body: { name: customerName, is_customer: true } });

    const receivable = await apiRequest<{ id: number }>("/accounting/accounts", {
      method: "POST",
      body: { code: `CXC-N-${suffix}`, name: "Cuentas por Cobrar", account_type: "receivable" },
    });
    const income = await apiRequest<{ id: number }>("/accounting/accounts", {
      method: "POST",
      body: { code: `ING-N-${suffix}`, name: "Ingresos", account_type: "income" },
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
      body: { document_type: "sales_credit_note", role: "receivable", account_id: receivable.id },
    });
    await apiRequest("/accounting/document-account-mappings", {
      method: "POST",
      body: { document_type: "sales_credit_note", role: "income", account_id: income.id },
    });

    const contacts = await apiRequest<Array<{ id: number; name: string }>>("/contacts");
    const customerId = contacts.find((c) => c.name === customerName)?.id as number;

    const invoice = await apiRequest<{ id: number; number: string }>("/accounting/invoices", {
      method: "POST",
      body: {
        direction: "sale",
        contact_id: customerId,
        issue_date: "2026-08-26",
        lines: [{ description: "Producto con defecto", quantity: "1", unit_price: "300.00" }],
      },
    });
    invoiceNumber = invoice.number;
    await apiRequest(`/accounting/invoices/${invoice.id}/post`, { method: "POST" });
  });

  it("crea una nota de crédito desde la UI relacionada a una factura y la contabiliza", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /nueva nota/i })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /nueva nota/i }));

    await user.click(screen.getByRole("combobox", { name: "Contacto" }));
    await user.click(await screen.findByRole("option", { name: customerName }));

    await user.click(screen.getByRole("combobox", { name: "Factura relacionada" }));
    await user.click(await screen.findByRole("option", { name: new RegExp(invoiceNumber) }));

    await user.type(screen.getByLabelText("Motivo"), "Producto defectuoso, devolución parcial");
    await user.type(screen.getByLabelText("Fecha de emisión"), "2026-08-26");

    await user.type(screen.getByPlaceholderText("Descripción"), "Devolución producto con defecto");
    const numberInputs = screen.getAllByRole("spinbutton");
    await user.clear(numberInputs[0]);
    await user.type(numberInputs[0], "1");
    await user.type(numberInputs[1], "300.00");

    await user.click(screen.getByRole("button", { name: /^crear nota$/i }));

    await waitFor(() => expect(screen.getByText("Borrador")).toBeInTheDocument(), { timeout: 5000 });
    // Espera explícita a que el diálogo de creación termine de cerrarse —
    // la lista puede refrescarse (por invalidación de query) un instante
    // antes de que el diálogo se desmonte, dejando la tabla momentáneamente
    // aria-hidden detrás del overlay todavía abierto.
    await waitFor(() => expect(screen.queryByText("Nueva nota de crédito/débito")).not.toBeInTheDocument());

    const table = screen.getByRole("table");
    await user.click(within(table).getByText(customerName));
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: /^contabilizar$/i })).toBeInTheDocument());
    await user.click(within(dialog).getByRole("button", { name: /^contabilizar$/i }));

    await waitFor(() => expect(within(dialog).getByText(/^contabilizada —/i)).toBeInTheDocument(), { timeout: 5000 });

    // Verificación real contra el backend.
    const notes = await apiRequest<Array<{ contact_id: number; status: string; total: string; journal_entry_id: number | null }>>(
      "/accounting/credit-debit-notes"
    );
    const contacts = await apiRequest<Array<{ id: number; name: string }>>("/contacts");
    const customerId = contacts.find((c) => c.name === customerName)?.id;
    const note = notes.find((n) => n.contact_id === customerId);
    expect(note?.status).toBe("posted");
    expect(note?.total).toBe("300.00");
    expect(note?.journal_entry_id).toBeTruthy();
  }, 15000);
});
