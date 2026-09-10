/**
 * Integración real contra backend en 127.0.0.1:8000 — flujo completo de
 * medical: agendar cita desde la UI, confirmarla, registrar una consulta
 * (con diagnóstico cifrado en el backend), y verificar RBAC clínico
 * "own patients" real: un usuario con `medical:consultation:read-own-
 * patients` (sin `-all`) que NUNCA atendió al paciente recibe 403 al
 * intentar leer la consulta directamente contra la API — no solo "no se
 * muestra en la UI". Mismos caveats que los demás tests de integración
 * (sin navegador real, no CORS).
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { MedicalPage } from "@/pages/MedicalPage";
import { setTokens } from "@/lib/auth-store";
import { apiRequest, schemas, ApiError } from "@/lib/api-client";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <MedicalPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("MedicalPage — flujo real de medical contra backend en 127.0.0.1:8000", () => {
  let setupDone = false;
  let adminTokens: { access_token: string; refresh_token: string };
  let patientName: string;

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

    patientName = `Paciente Medical ${Date.now()}`;
    await apiRequest("/contacts", { method: "POST", body: { name: patientName, is_patient: true } });
  });

  it("agenda una cita, la confirma, y registra una consulta desde la UI", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /nueva cita/i })).toBeInTheDocument(), {
      timeout: 15000,
    });
    await user.click(screen.getByRole("button", { name: /nueva cita/i }));

    await user.click(screen.getByRole("combobox", { name: "Paciente" }));
    await user.click(await screen.findByRole("option", { name: patientName }));

    await user.click(screen.getByRole("combobox", { name: "Profesional" }));
    await user.click((await screen.findAllByRole("option"))[0]);

    // Offset aleatorio de días (además de +1h) para no chocar con el
    // EXCLUDE USING gist real de bloqueo de horario (DED-26) si este test
    // se corre varias veces seguidas contra la misma base persistente —
    // mismo profesional + misma ventana de tiempo = 409 Conflict legítimo,
    // no un bug de la app.
    const start = new Date(Date.now() + 3600_000 + Math.floor(Math.random() * 90) * 86_400_000);
    const localValue = new Date(start.getTime() - start.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
    const startInput = screen.getByLabelText("Fecha y hora");
    await user.clear(startInput);
    await user.type(startInput, localValue);

    await user.click(screen.getByRole("button", { name: /^agendar cita$/i }));

    await waitFor(() => expect(screen.getAllByText(patientName).length).toBeGreaterThan(0), { timeout: 10000 });

    // Abrir el detalle, confirmar, registrar consulta. La fila de la cita
    // es un <button> — se apunta por rol para evitar ambigüedad con otras
    // apariciones del nombre del paciente en la página (ej. el selector
    // del Expediente Clínico).
    let appointmentRow: HTMLElement | undefined;
    await waitFor(() => {
      appointmentRow = screen.queryByRole("button", { name: `Cita de ${patientName}` }) ?? undefined;
      expect(appointmentRow).toBeTruthy();
    }, { timeout: 10000 });
    await user.click(appointmentRow!);
    const dialog = await screen.findByRole("dialog");
    await user.click(await within(dialog).findByRole("button", { name: /^confirmar$/i }));
    await waitFor(() => expect(within(dialog).getByRole("button", { name: /registrar consulta/i })).toBeInTheDocument());

    await user.click(within(dialog).getByRole("button", { name: /registrar consulta/i }));
    const diagnosisText = `Diagnóstico de prueba ${Date.now()}`;
    await user.type(within(dialog).getByLabelText("Diagnóstico"), diagnosisText);
    await user.click(within(dialog).getByRole("button", { name: /^guardar consulta$/i }));

    await waitFor(() => expect(within(dialog).getByText(new RegExp(diagnosisText))).toBeInTheDocument(), { timeout: 10000 });

    // Verificación real contra el backend: el diagnóstico viaja cifrado en
    // reposo pero descifrado en la respuesta de la API (comportamiento
    // esperado, no un leak — ver DED-24).
    const appointments = await apiRequest<Array<{ id: number; patient_contact_id: number }>>("/medical/appointments");
    const patients = await apiRequest<Array<{ id: number; name: string }>>("/contacts", { query: { search: patientName } });
    const patientId = patients.find((p) => p.name === patientName)?.id;
    const appointment = appointments.find((a) => a.patient_contact_id === patientId);
    expect(appointment).toBeTruthy();

    const consultation = await apiRequest<{ diagnosis_text: string | null }>(
      `/medical/appointments/${appointment!.id}/consultation`
    );
    expect(consultation.diagnosis_text).toBe(diagnosisText);

    // Módulo 10 — Recetas: emitir una receta con un medicamento desde la
    // sección "Recetas" que aparece dentro del mismo diálogo una vez que
    // hay consulta registrada, y luego anularla.
    await user.click(within(dialog).getByRole("button", { name: /^nueva receta$/i }));
    const medicationName = `Amoxicilina ${Date.now()}`;
    await user.type(within(dialog).getByPlaceholderText("Medicamento"), medicationName);
    await user.type(within(dialog).getByPlaceholderText("Dosis (ej. 500mg)"), "500mg");
    await user.type(within(dialog).getByPlaceholderText("Vía (ej. oral)"), "oral");
    await user.type(within(dialog).getByPlaceholderText("Frecuencia"), "cada 8 horas");
    await user.type(within(dialog).getByPlaceholderText("Duración"), "7 días");
    await user.click(within(dialog).getByRole("button", { name: /^emitir receta$/i }));

    await waitFor(() => expect(within(dialog).getByText(new RegExp(medicationName))).toBeInTheDocument(), { timeout: 10000 });

    // Verificación real: sin paquete 'pharmacy' activo para esta compañía
    // de prueba, dispensing_status debe caer en 'not_applicable' (DED-30).
    const prescriptions = await apiRequest<Array<{ consultation_id: number; lines: Array<{ medication_name: string; dispensing_status: string }> }>>(
      `/medical/patients/${patientId}/prescriptions`
    );
    const prescription = prescriptions.find((p) => p.lines.some((l) => l.medication_name === medicationName));
    expect(prescription).toBeTruthy();
    expect(prescription!.lines[0].dispensing_status).toBe("not_applicable");

    // Anular la receta desde la UI y verificar que persiste contra el backend.
    await user.type(within(dialog).getByPlaceholderText("Motivo de anulación"), "Emitida por error en esta prueba");
    await user.click(within(dialog).getByRole("button", { name: /^anular$/i }));
    await waitFor(() => expect(within(dialog).getByText(/anulada/i)).toBeInTheDocument(), { timeout: 10000 });

    // Módulo 11 — Laboratorio: ordenar una prueba, cargar resultado
    // marcado como crítico, y verificar contra el backend.
    await user.click(within(dialog).getByRole("button", { name: /^nueva orden$/i }));
    await user.type(within(dialog).getByPlaceholderText(/nombre de la prueba/i), "Glucosa en ayunas");
    await user.click(within(dialog).getByRole("button", { name: /^ordenar$/i }));

    await waitFor(() => expect(within(dialog).getByText("Glucosa en ayunas")).toBeInTheDocument(), { timeout: 10000 });

    await user.click(within(dialog).getByRole("button", { name: /^cargar resultado$/i }));
    await user.type(within(dialog).getByPlaceholderText("Valor"), "280");
    await user.type(within(dialog).getByPlaceholderText("Unidad"), "mg/dL");
    await user.type(within(dialog).getByPlaceholderText(/rango de referencia/i), "70-100 mg/dL");
    await user.click(within(dialog).getByRole("checkbox", { name: /marcar como valor crítico/i }));
    await user.click(within(dialog).getByRole("button", { name: /^guardar resultado$/i }));

    await waitFor(() => expect(within(dialog).getByText(/280 mg\/dL/)).toBeInTheDocument(), { timeout: 10000 });
    expect(within(dialog).getByText("Crítico")).toBeInTheDocument();

    const labOrders = await apiRequest<Array<{ consultation_id: number; tests: Array<{ test_name: string; is_critical: boolean; status: string }> }>>(
      `/medical/patients/${patientId}/lab-orders`
    );
    const labOrder = labOrders.find((o) => o.tests.some((t) => t.test_name === "Glucosa en ayunas"));
    expect(labOrder).toBeTruthy();
    const glucoseTest = labOrder!.tests.find((t) => t.test_name === "Glucosa en ayunas")!;
    expect(glucoseTest.is_critical).toBe(true);
    expect(glucoseTest.status).toBe("resulted");

    // RBAC clínico "own patients", verificado real: un usuario con
    // medical:consultation:read-own-patients (sin -all) que NUNCA atendió
    // a este paciente recibe 403 al pedir la consulta directamente.
    const roleSuffix = Date.now();
    const role = await apiRequest<{ id: number }>("/roles", {
      method: "POST",
      body: { name: `Medical Limitado Test ${roleSuffix}`, permission_ids: await resolvePermissionIds() },
    });
    const limitedEmail = `medical.limitado.${roleSuffix}@elroble.hn`;
    await apiRequest("/users", {
      method: "POST",
      body: { email: limitedEmail, full_name: "Medical Limitado", password: "SuperSegura123", role_ids: [role.id] },
    });
    const limitedTokens = await apiRequest<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      auth: false,
      body: { email: limitedEmail, password: "SuperSegura123" },
      responseSchema: schemas.TokenResponse,
    });
    setTokens(limitedTokens.access_token, limitedTokens.refresh_token);

    await expect(apiRequest(`/medical/appointments/${appointment!.id}/consultation`)).rejects.toSatisfy(
      (err: unknown) => err instanceof ApiError && err.status === 403
    );

    // Restaurar sesión de admin para no afectar el resto del proceso.
    setTokens(adminTokens.access_token, adminTokens.refresh_token);
  }, 30000);
});

// Los permisos medical:* se crean con ids consecutivos por el bootstrap del
// entorno de test (ver scripts/bootstrap_admin.py) — se resuelven por
// código en vez de asumir ids fijos, mismo patrón que el test de hr.
async function resolvePermissionIds(): Promise<number[]> {
  const roles = await apiRequest<Array<{ id: number; permissions: Array<{ id: number; code: string }> }>>("/roles");
  const adminRole = roles.find((r) => r.permissions.some((p) => p.code === "medical:consultation:read-own-patients"));
  const wanted = ["medical:appointment:list", "medical:appointment:read", "medical:consultation:read-own-patients"];
  const ids = wanted
    .map((code) => adminRole?.permissions.find((p) => p.code === code)?.id)
    .filter((id): id is number => id !== undefined);
  return ids;
}
