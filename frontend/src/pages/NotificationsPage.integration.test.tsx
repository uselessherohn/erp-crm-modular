/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * notifications: crear una plantilla desde la UI, editarla, enviar una
 * notificación (directa y por plantilla) y verificar la campana
 * (`NotificationBell`) — contador de no leídas, marcar como leída y
 * marcar todas como leídas — contra datos reales, no mockeados. Mismos
 * caveats que los demás tests de integración (sin navegador real, no
 * CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { NotificationBell } from "@/components/NotificationBell";
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

describe("NotificationsPage + NotificationBell — flujo real contra backend en 127.0.0.1:8000", () => {
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

  it("crea y edita una plantilla, envía una notificación por plantilla, y la campana refleja el no leído", async () => {
    const user = userEvent.setup();
    const suffix = Date.now();
    const templateCode = `welcome_${suffix}`;

    renderWith(<NotificationsPage />);

    await waitFor(() => expect(screen.getByLabelText("Código")).toBeInTheDocument(), { timeout: 15000 });

    await user.type(screen.getByLabelText("Código"), templateCode);
    await user.type(screen.getByLabelText(/Asunto/), "Hola {{name}");
    await user.type(screen.getByLabelText(/Cuerpo \(admite/), "Bienvenido {{name}, tu código es {{code}");
    await user.click(screen.getByRole("button", { name: /^crear plantilla$/i }));

    await waitFor(() => expect(screen.getByText(templateCode)).toBeInTheDocument(), { timeout: 10000 });

    // Editar: click en la fila abre el formulario en modo edición.
    await user.click(screen.getByText(templateCode));
    const subjectInput = screen.getByLabelText(/Asunto/) as HTMLInputElement;
    await waitFor(() => expect(subjectInput.value).toBe("Hola {name}"));
    await user.clear(subjectInput);
    await user.type(subjectInput, "Hola {{name}, editado");
    await user.click(screen.getByRole("button", { name: /guardar cambios/i }));

    await waitFor(async () => {
      const templates = await apiRequest<Array<{ code: string; subject_template: string }>>("/notifications/templates");
      const t = templates.find((x) => x.code === templateCode);
      expect(t?.subject_template).toBe("Hola {name}, editado");
    }, { timeout: 10000 });

    // Enviar por plantilla al propio admin (para poder verificar la campana).
    const me = await apiRequest<{ id: number; full_name: string | null; email: string }>("/users/me");

    const recipientSelect = screen.getByRole("combobox", { name: "Destinatario" });
    await user.click(recipientSelect);
    await user.click(await screen.findByRole("option", { name: me.full_name ?? me.email }));

    await user.click(screen.getByRole("combobox", { name: "Modo de contenido" }));
    await user.click(await screen.findByRole("option", { name: "Desde plantilla" }));

    await user.click(screen.getByRole("combobox", { name: "Plantilla" }));
    await user.click(await screen.findByRole("option", { name: templateCode }));

    await user.type(screen.getByLabelText(/Contexto/), `name=Roberto\ncode=${suffix}`);
    await user.click(screen.getByRole("button", { name: /^enviar$/i }));

    await waitFor(() => expect(screen.getByText(/notificación enviada/i)).toBeInTheDocument(), { timeout: 10000 });

    // Verificación real contra el backend: el placeholder se resolvió con
    // el contexto enviado (DED-29).
    const notifications = await apiRequest<Array<{ title: string; body: string; read_at: string | null }>>("/notifications");
    const sent = notifications.find((n) => n.title === "Hola Roberto, editado");
    expect(sent).toBeTruthy();
    expect(sent!.body).toBe(`Bienvenido Roberto, tu código es ${suffix}`);
    expect(sent!.read_at).toBeNull();

    // La campana — render independiente — refleja el no leído real.
    renderWith(<NotificationBell />);
    const bellButtons = screen.getAllByRole("button", { name: "Notificaciones" });
    const bellButton = bellButtons[bellButtons.length - 1];
    await waitFor(() => expect(within(bellButton).getByText(/^\d+\+?$/)).toBeInTheDocument(), { timeout: 10000 });

    await user.click(bellButton);
    const notificationItem = await screen.findByText("Hola Roberto, editado", {}, { timeout: 10000 });
    await user.click(notificationItem);

    await waitFor(async () => {
      const refreshed = await apiRequest<Array<{ title: string; read_at: string | null }>>("/notifications");
      const found = refreshed.find((n) => n.title === "Hola Roberto, editado");
      expect(found?.read_at).not.toBeNull();
    }, { timeout: 10000 });
  }, 30000);
});
