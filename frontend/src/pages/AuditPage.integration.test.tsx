/**
 * Integración real contra backend en 127.0.0.1:8000 — crea un contacto
 * (dispara un evento de auditoría real, `contact.created`), verifica que
 * aparece filtrado en la sección "Registro de actividad", y confirma que
 * la política de retención se puede editar desde la UI y persiste de
 * verdad (GET después de PUT devuelve el valor guardado, no el default).
 *
 * TODO cerrado en esta sesión: este módulo (25, audit completo) no tenía
 * su propio test de integración de frontend — ver STATE.md, sección
 * `audit`.
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AuditPage } from "@/pages/AuditPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderWith(children: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AuditPage — flujo real contra backend en 127.0.0.1:8000", () => {
  let setupDone = false;

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
  });

  it("un evento real (crear contacto) aparece en el registro filtrado por tipo de entidad", async () => {
    const suffix = Date.now();
    const contactName = `Contacto Audit ${suffix}`;

    // Se dispara el evento por API directa (no por UI) porque lo que se
    // quiere probar acá es que AuditPage LEE eventos reales que
    // cualquier módulo ya genera (contacts, en este caso), no la UI de
    // creación de contactos en sí — eso ya lo cubre
    // ContactsPage.integration.test.tsx.
    const contact = await apiRequest<{ id: number }>("/contacts", {
      method: "POST",
      body: { name: contactName, is_lead: true },
    });
    expect(contact.id).toBeGreaterThan(0);

    renderWith(<AuditPage />);

    await waitFor(() => expect(screen.getByLabelText("Tipo de entidad")).toBeInTheDocument(), { timeout: 15000 });

    const entityTypeInput = screen.getByLabelText("Tipo de entidad");
    await userEvent.setup().type(entityTypeInput, "contact");

    await waitFor(
      () => {
        // Otros archivos de esta misma suite (PharmacyPage, etc.) también
        // crean contactos reales contra la misma compañía persistente —
        // "contact.created" no es un texto único en la tabla. Se busca
        // entre TODAS las filas con ese evento la que además referencia
        // el `entity_id` de este contacto específico.
        const rows = screen.getAllByText("contact.created").map((el) => el.closest("tr")!);
        const match = rows.find((row) => within(row).queryByText(new RegExp(`#${contact.id}$`)));
        expect(match).toBeTruthy();
      },
      { timeout: 10000 }
    );
  }, 30000);

  it("la política de retención se edita desde la UI y el valor persiste", async () => {
    renderWith(<AuditPage />);

    await waitFor(() => expect(screen.getByLabelText("Días de retención")).toBeInTheDocument(), { timeout: 15000 });

    const user = userEvent.setup();

    // Valor distinto cada corrida (basado en el segundo actual, acotado
    // a un rango válido) para no depender de qué dejó una corrida previa.
    const newDays = 30 + (Date.now() % 60);
    const input = screen.getByLabelText("Días de retención") as HTMLInputElement;
    // Bug real encontrado en esta sesión (ver el fix en AuditPage.tsx):
    // `user.clear()` no dejaba el campo vacío de verdad — el componente
    // volvía a mostrar el valor persistido de inmediato como fallback de
    // display, así que escribir después CONCATENABA dígitos ("90" + "51"
    // → "9051"). Corregido en el componente (el campo ahora se
    // inicializa una sola vez con el valor real, editable de verdad) —
    // `clear()` + `type()` ya funciona como cabría esperar.
    await user.clear(input);
    await user.type(input, String(newDays));
    expect(input.value).toBe(String(newDays));
    await user.click(screen.getByRole("button", { name: /^guardar$/i }));

    // Se confirma contra la API directo (fuente de verdad real) y con un
    // montaje nuevo del componente (simula reabrir la página), no solo
    // mirando el mismo input que se acaba de editar.
    await waitFor(async () => {
      const persisted = await apiRequest<{ retention_days: number }>("/audit/retention-policy");
      expect(persisted.retention_days).toBe(newDays);
    }, { timeout: 10000 });

    renderWith(<AuditPage />);
    await waitFor(() => expect((screen.getAllByLabelText("Días de retención").at(-1) as HTMLInputElement).value).toBe(String(newDays)), {
      timeout: 10000,
    });
  }, 30000);
});
