/**
 * Integración real contra backend en 127.0.0.1:8000 — requiere que exista
 * la compañía + admin de bootstrap (backend/scripts/bootstrap_admin.py) con
 * los permisos core:user:create/list. Mismo caveat que LoginPage.integration:
 * sin navegador real disponible (ver network_configuration del cierre), no
 * verifica CORS.
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { UsersPage } from "@/pages/UsersPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderUsersPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <UsersPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("UsersPage — integración real contra backend en 127.0.0.1:8000", () => {
  beforeAll(async () => {
    // Login real (no se reusa el token entre archivos de test — cada
    // proceso de vitest arranca con auth-store vacío).
    const tokens = await apiRequest<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: "admin@elroble.hn", password: "SuperSegura123" },
      responseSchema: schemas.TokenResponse,
    });
    setTokens(tokens.access_token, tokens.refresh_token);
  });

  it("lista los usuarios existentes (al menos el admin de bootstrap)", async () => {
    renderUsersPage();
    await waitFor(() => expect(screen.getByText("admin@elroble.hn")).toBeInTheDocument());
  });

  it("crea un usuario nuevo y aparece en la lista sin recargar", async () => {
    const user = userEvent.setup();
    renderUsersPage();

    await waitFor(() => expect(screen.getByText("admin@elroble.hn")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /nuevo usuario/i }));

    const uniqueEmail = `nuevo-${Date.now()}@elroble.hn`;
    await user.type(screen.getByLabelText(/nombre completo/i), "Empleado de Prueba");
    await user.type(screen.getByLabelText(/^correo$/i), uniqueEmail);
    await user.type(screen.getByLabelText(/contraseña temporal/i), "password123");
    await user.click(screen.getByRole("button", { name: /^crear usuario$/i }));

    await waitFor(() => expect(screen.getByText(uniqueEmail)).toBeInTheDocument(), { timeout: 5000 });
  });

  it("abre el detalle de un usuario al hacer click en la fila (GET /users/{id})", async () => {
    const user = userEvent.setup();
    renderUsersPage();

    await waitFor(() => expect(screen.getByText("admin@elroble.hn")).toBeInTheDocument());
    await user.click(screen.getByText("admin@elroble.hn"));

    await waitFor(() => expect(screen.getByText("Detalle de usuario")).toBeInTheDocument());
    // El diálogo de detalle muestra el nombre completo vía GET /users/{id},
    // no el dato ya cacheado de la lista — confirma que pega al endpoint.
    await waitFor(() => expect(screen.getByText("Admin Bootstrap")).toBeInTheDocument());
  });
});
