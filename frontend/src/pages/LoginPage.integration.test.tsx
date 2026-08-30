/**
 * Integración real, no un mock de fetch: este test asume que el backend
 * (uvicorn) está corriendo en 127.0.0.1:8000 con una compañía + usuario de
 * bootstrap ya creados (ver backend/scripts/bootstrap_admin.py). No hay
 * navegador real disponible en este entorno (cdn.playwright.dev no está en
 * el allowlist de red) — jsdom + fetch nativo de Node cubre lógica de
 * formulario, llamada HTTP real y actualización de estado, pero NO
 * verifica CORS (jsdom/Node fetch no aplica esa restricción — solo los
 * navegadores la aplican). La verificación de CORS queda pendiente de
 * prueba manual en navegador real, documentada en el cierre.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { LoginPage } from "@/pages/LoginPage";
import { clearTokens, getAccessToken } from "@/lib/auth-store";

function renderLogin() {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("LoginPage — integración real contra backend en 127.0.0.1:8000", () => {
  beforeEach(() => {
    clearTokens();
  });

  it("inicia sesión con credenciales válidas y guarda el access token", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText(/correo/i), "admin@elroble.hn");
    await user.type(screen.getByLabelText(/contraseña/i), "SuperSegura123");
    await user.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => expect(getAccessToken()).not.toBeNull(), { timeout: 5000 });
  });

  it("muestra 'Credenciales inválidas' con password incorrecta (mensaje genérico del backend)", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText(/correo/i), "admin@elroble.hn");
    await user.type(screen.getByLabelText(/contraseña/i), "password_incorrecta");
    await user.click(screen.getByRole("button", { name: /ingresar/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Credenciales inválidas"));
    expect(getAccessToken()).toBeNull();
  });

  it("valida el formulario client-side con el mismo schema Zod del backend (email inválido)", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText(/correo/i), "no-es-un-email");
    await user.type(screen.getByLabelText(/contraseña/i), "cualquiera");
    await user.click(screen.getByRole("button", { name: /ingresar/i }));

    // No debería ni siquiera llegar a pegarle al backend — el resolver de
    // Zod generado rechaza el formato antes del submit.
    await waitFor(() => expect(screen.queryByText(/email/i)).toBeInTheDocument());
    expect(getAccessToken()).toBeNull();
  });
});
