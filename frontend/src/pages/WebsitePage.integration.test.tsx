/**
 * Integración real contra backend en 127.0.0.1:8000 — crear una página
 * desde la UI, publicarla, y verificar que un envío de formulario público
 * (`/public/website/{company_id}/forms`, sin auth) crea un contacto lead y
 * aparece en la sección "Formularios recibidos" del panel interno.
 *
 * NOTA DE ESTE CIERRE: escrito y revisado a mano contra el código real de
 * `WebsitePage.tsx`/`use-website.ts`, pero NO ejecutado — el entorno de
 * diseño no tenía servidor backend corriendo, Postgres, ni `node_modules`
 * instalado (sin red para `npm install`). Correr
 * `npm run dev` (backend) + `npx vitest run src/pages/WebsitePage.integration.test.tsx`
 * antes de marcar el módulo 22 como (✓) en STATE.md — mismo estándar que
 * el resto de los tests de este archivo (ver NotificationsPage.integration.test.tsx).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { WebsitePage } from "@/pages/WebsitePage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function renderWith(children: React.ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WebsitePage — flujo real contra backend en 127.0.0.1:8000", () => {
  let setupDone = false;
  let companyId: number;

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

    const me = await apiRequest<{ company_id: number }>("/users/me");
    companyId = me.company_id;
  });

  it("crea y publica una página, y un envío público de formulario aparece en el panel", async () => {
    const user = userEvent.setup();
    const suffix = Date.now();
    const slug = `landing-${suffix}`;
    const title = `Landing ${suffix}`;

    renderWith(<WebsitePage />);

    await waitFor(() => expect(screen.getByLabelText("Slug")).toBeInTheDocument(), { timeout: 15000 });

    await user.type(screen.getByLabelText("Slug"), slug);
    await user.type(screen.getByLabelText("Título"), title);
    await user.type(screen.getByLabelText("Contenido"), "Contenido de prueba");
    await user.click(screen.getByRole("button", { name: /^crear página$/i }));

    await waitFor(() => expect(screen.getByText(title)).toBeInTheDocument(), { timeout: 10000 });
    await user.click(screen.getByRole("button", { name: /^publicar$/i }));
    await waitFor(() => expect(screen.getByText("Publicada")).toBeInTheDocument(), { timeout: 10000 });

    // Ruta pública (sin JWT) — visitante anónimo del storefront.
    const publicPage = await fetch(`${BASE_URL}/public/website/${companyId}/pages/${slug}`).then((r) => r.json());
    expect(publicPage.title).toBe(title);

    const email = `lead-${suffix}@example.com`;
    const submitRes = await fetch(`${BASE_URL}/public/website/${companyId}/forms`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ form_name: "contacto", name: "Lead de Prueba", email, message: "Hola" }),
    });
    expect(submitRes.status).toBe(201);

    await waitFor(
      async () => {
        const contacts = await apiRequest<Array<{ email: string | null; is_lead: boolean }>>("/contacts", {
          query: { search: email },
        });
        const lead = contacts.find((c) => c.email === email);
        expect(lead?.is_lead).toBe(true);
      },
      { timeout: 10000 }
    );

    // Re-render para reflejar el envío recién creado en "Formularios recibidos".
    renderWith(<WebsitePage />);
    await waitFor(() => expect(screen.getByText(email)).toBeInTheDocument(), { timeout: 10000 });
  }, 30000);
});
