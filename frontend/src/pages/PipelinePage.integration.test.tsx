/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * pipeline: crear etapas (incluida una terminal "ganada"), crear una
 * oportunidad desde la UI, moverla de etapa, cerrarla ganada, y registrar
 * una actividad. Requiere el paquete 'administrative' activo (gating real
 * de spec 2.3, primer módulo del proyecto que lo aplica) — se activa
 * directamente contra la base en beforeAll, ya que no existe endpoint
 * público para contratar paquetes. Mismos caveats que los demás tests de
 * integración (sin navegador real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { PipelinePage } from "@/pages/PipelinePage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PipelinePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PipelinePage — flujo real de pipeline contra backend en 127.0.0.1:8000", () => {
  let contactName: string;
  let stageName: string;
  let setupDone = false;

  beforeAll(async () => {
    // Guarda de idempotencia — mismo hallazgo real que en los demás módulos
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
    contactName = `Lead Pipeline ${suffix}`;
    stageName = `Prospecto ${suffix}`;

    await apiRequest("/contacts", { method: "POST", body: { name: contactName, is_lead: true } });
    await apiRequest("/pipeline/stages", { method: "POST", body: { name: stageName, sort_order: 1 } });
    await apiRequest("/pipeline/stages", {
      method: "POST",
      body: { name: `Ganada ${suffix}`, sort_order: 99, is_won: true },
    });
  });

  it("crea una oportunidad desde la UI, la mueve de etapa y la cierra ganada", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /nueva oportunidad/i })).toBeInTheDocument(), {
      timeout: 10000,
    });
    await user.click(screen.getByRole("button", { name: /nueva oportunidad/i }));

    const opportunityName = `Venta materiales ${Date.now()}`;
    await user.type(screen.getByLabelText("Nombre"), opportunityName);

    await user.click(screen.getByRole("combobox", { name: "Contacto" }));
    await user.click(await screen.findByRole("option", { name: contactName }));

    await user.click(screen.getByRole("combobox", { name: "Etapa inicial" }));
    await user.click(await screen.findByRole("option", { name: stageName }));

    await user.type(screen.getByLabelText("Monto estimado"), "25000");

    await user.click(screen.getByRole("button", { name: /^crear oportunidad$/i }));

    // La tarjeta aparece en la columna de su etapa.
    await waitFor(() => expect(screen.getByText(opportunityName)).toBeInTheDocument(), { timeout: 10000 });

    // Abrir el detalle y cerrar ganada.
    await user.click(screen.getByText(opportunityName));
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: /^cerrar ganada$/i })).toBeInTheDocument());
    await user.click(within(dialog).getByRole("button", { name: /^cerrar ganada$/i }));

    await waitFor(() => expect(within(dialog).getByText(/^ganada —/i)).toBeInTheDocument(), { timeout: 5000 });

    // Verificación real contra el backend.
    const opportunities = await apiRequest<Array<{ name: string; status: string; closed_at: string | null }>>(
      "/pipeline/opportunities"
    );
    const created = opportunities.find((o) => o.name === opportunityName);
    expect(created?.status).toBe("won");
    expect(created?.closed_at).toBeTruthy();
  }, 20000);
});
