/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * hr: crear departamento, puesto y empleado con salario desde la UI
 * (como admin, que ve el salario), luego verificar contra el backend que
 * un usuario con un rol SIN `hr:employee:read-sensitive` recibe el
 * salario enmascarado (`null`) — el comportamiento central de DED-21,
 * verificado real, no solo a nivel de UI. Mismos caveats que los demás
 * tests de integración (sin navegador real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { EmployeesPage } from "@/pages/EmployeesPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <EmployeesPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("EmployeesPage — flujo real de hr contra backend en 127.0.0.1:8000", () => {
  let setupDone = false;
  let adminTokens: { access_token: string; refresh_token: string };

  beforeAll(async () => {
    // Guarda de idempotencia — mismo hallazgo real que en los demás módulos.
    if (setupDone) return;
    setupDone = true;

    adminTokens = await apiRequest<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: "admin@elroble.hn", password: "SuperSegura123" },
      responseSchema: schemas.TokenResponse,
    });
    setTokens(adminTokens.access_token, adminTokens.refresh_token);
  });

  it("crea departamento, puesto y empleado con salario desde la UI, visible como admin", async () => {
    const user = userEvent.setup();
    renderPage();

    const suffix = Date.now();
    const deptName = `Ventas ${suffix}`;
    const positionTitle = `Vendedor ${suffix}`;
    const firstName = `Carlos${suffix}`;
    const lastName = "Martínez";

    await waitFor(() => expect(screen.getByRole("button", { name: /nuevo departamento/i })).toBeInTheDocument(), {
      timeout: 15000,
    });
    await user.click(screen.getByRole("button", { name: /nuevo departamento/i }));
    await user.type(screen.getByLabelText("Nombre"), deptName);
    await user.click(screen.getByRole("button", { name: /^crear departamento$/i }));
    await waitFor(() => expect(screen.getByText(deptName)).toBeInTheDocument(), { timeout: 10000 });

    await user.click(screen.getByRole("button", { name: /nuevo puesto/i }));
    await user.type(screen.getByLabelText("Título"), positionTitle);
    await user.click(screen.getByRole("combobox", { name: "Departamento" }));
    await user.click(await screen.findByRole("option", { name: deptName }));
    await user.click(screen.getByRole("button", { name: /^crear puesto$/i }));
    await waitFor(() => expect(screen.getByText(new RegExp(positionTitle))).toBeInTheDocument(), { timeout: 10000 });

    await user.click(screen.getByRole("button", { name: /nuevo empleado/i }));
    await user.type(screen.getByLabelText("Nombre"), firstName);
    await user.type(screen.getByLabelText("Apellido"), lastName);
    await user.click(screen.getByRole("combobox", { name: "Puesto" }));
    await user.click(await screen.findByRole("option", { name: positionTitle }));
    await user.type(screen.getByLabelText("Fecha de contratación"), "2026-01-15");
    await user.type(screen.getByLabelText("Salario (opcional)"), "18000");
    await user.click(screen.getByRole("button", { name: /^crear empleado$/i }));

    await waitFor(() => expect(screen.getByText(`${firstName} ${lastName}`)).toBeInTheDocument(), { timeout: 10000 });
    // El admin tiene hr:employee:read-sensitive — el salario debe mostrarse.
    await waitFor(() => expect(screen.getByText("18000.00")).toBeInTheDocument());

    // Verificación real del enmascarado (DED-21): un usuario con un rol
    // SIN hr:employee:read-sensitive debe recibir salary=null del backend,
    // no solo "no mostrado en la UI" — se verifica contra la API directa,
    // con sus propias credenciales, no reutilizando las del admin.
    const employees = await apiRequest<Array<{ id: number; first_name: string; salary: string | null }>>("/hr/employees");
    const created = employees.find((e) => e.first_name === firstName);
    expect(created?.salary).toBe("18000.00");

    const roleSuffix = suffix;
    const role = await apiRequest<{ id: number }>("/roles", {
      method: "POST",
      body: { name: `HR Básico Test ${roleSuffix}`, permission_ids: await resolvePermissionIds() },
    });
    const limitedEmail = `hr.limitado.${roleSuffix}@elroble.hn`;
    await apiRequest("/users", {
      method: "POST",
      body: { email: limitedEmail, full_name: "HR Limitado", password: "SuperSegura123", role_ids: [role.id] },
    });

    const limitedTokens = await apiRequest<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: limitedEmail, password: "SuperSegura123" },
      responseSchema: schemas.TokenResponse,
    });
    setTokens(limitedTokens.access_token, limitedTokens.refresh_token);

    const employeesAsLimited = await apiRequest<Array<{ first_name: string; salary: string | null }>>("/hr/employees");
    const createdAsLimited = employeesAsLimited.find((e) => e.first_name === firstName);
    expect(createdAsLimited?.salary).toBeNull();

    // Restaurar sesión de admin para no afectar el resto del proceso.
    setTokens(adminTokens.access_token, adminTokens.refresh_token);
  }, 30000);
});

// Los permisos hr:* se crean con ids consecutivos por el bootstrap del
// entorno de test (ver scripts/bootstrap_admin.py) — se resuelven por
// código en vez de asumir ids fijos, para no acoplar el test al orden de
// inserción real de la base.
async function resolvePermissionIds(): Promise<number[]> {
  // No hay endpoint GET /permissions expuesto — se listan roles (que
  // incluyen sus permisos anidados) y se usa el rol admin (id 1, creado
  // por bootstrap) para descubrir los ids reales de los códigos que
  // necesitamos, sin asumir numeración.
  const roles = await apiRequest<Array<{ id: number; permissions: Array<{ id: number; code: string }> }>>("/roles");
  const adminRole = roles.find((r) => r.permissions.some((p) => p.code === "hr:employee:read"));
  const wanted = ["hr:department:list", "hr:position:list", "hr:employee:create", "hr:employee:read"];
  const ids = wanted
    .map((code) => adminRole?.permissions.find((p) => p.code === code)?.id)
    .filter((id): id is number => id !== undefined);
  return ids;
}
