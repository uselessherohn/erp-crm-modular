/**
 * Integración real contra backend en 127.0.0.1:8000 (mismos caveats que
 * UsersPage.integration.test.tsx: sin navegador real, no verifica CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ContactsPage } from "@/pages/ContactsPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderContactsPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ContactsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ContactsPage — integración real contra backend en 127.0.0.1:8000", () => {
  beforeAll(async () => {
    const tokens = await apiRequest<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: "admin@elroble.hn", password: "SuperSegura123" },
      responseSchema: schemas.TokenResponse,
    });
    setTokens(tokens.access_token, tokens.refresh_token);

    // Datos base para la búsqueda — creados directo por API, no por UI,
    // para no acoplar este test al de creación.
    await apiRequest("/contacts", {
      method: "POST",
      body: { name: "Farmacia Central Tegucigalpa", is_customer: true },
    });
    await apiRequest("/contacts", {
      method: "POST",
      body: { name: "Distribuidora San José", is_vendor: true },
    });
  });

  it("lista los contactos existentes", async () => {
    renderContactsPage();
    await waitFor(() => expect(screen.getByText("Farmacia Central Tegucigalpa")).toBeInTheDocument());
    expect(screen.getByText("Distribuidora San José")).toBeInTheDocument();
  });

  it("busca con typo y encuentra el contacto vía pg_trgm (backend real)", async () => {
    const user = userEvent.setup();
    renderContactsPage();

    await waitFor(() => expect(screen.getByText("Farmacia Central Tegucigalpa")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText(/buscar por nombre/i), "Farmasia Sentral");

    // Debounce de 300ms + roundtrip real — esperamos a que la lista se
    // reduzca al único resultado relevante.
    await waitFor(
      () => {
        expect(screen.getByText("Farmacia Central Tegucigalpa")).toBeInTheDocument();
        expect(screen.queryByText("Distribuidora San José")).not.toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  it("crea un contacto nuevo con rol y aparece en la lista", async () => {
    const user = userEvent.setup();
    renderContactsPage();

    await waitFor(() => expect(screen.getByText("Farmacia Central Tegucigalpa")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /nuevo contacto/i }));

    const uniqueName = `Proveedor de Prueba ${Date.now()}`;
    await user.type(screen.getByLabelText(/^nombre$/i), uniqueName);
    await user.click(screen.getByLabelText(/proveedor/i));
    await user.click(screen.getByRole("button", { name: /^crear contacto$/i }));

    await waitFor(() => expect(screen.getByText(uniqueName)).toBeInTheDocument(), { timeout: 5000 });
  });

  it("rechaza crear un contacto sin ningún rol — error del backend visible en el form", async () => {
    const user = userEvent.setup();
    renderContactsPage();

    await waitFor(() => expect(screen.getByText("Farmacia Central Tegucigalpa")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /nuevo contacto/i }));
    await user.type(screen.getByLabelText(/^nombre$/i), "Sin Ningún Rol");
    await user.click(screen.getByRole("button", { name: /^crear contacto$/i }));

    // El schema Zod generado no conoce el model_validator de Pydantic
    // (invisible en el JSON Schema) — el error llega recién del backend.
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/al menos un rol/i));
  });
});
