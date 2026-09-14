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
    // is_customer=true además de is_patient=true: la compañía de prueba
    // compartida ("El Roble") ya tiene el paquete 'administrative' activo
    // (bootstrap_admin.py), así que Facturación Médica Básica toma el
    // camino real de accounting_invoice (DED-42) — y ese motor exige el
    // flag is_customer en el contacto, igual que cualquier otra factura.
    await apiRequest("/contacts", { method: "POST", body: { name: patientName, is_patient: true, is_customer: true } });

    // Plan de cuentas + mapeo mínimo para poder contabilizar una factura
    // de venta — no hay ningún seed automático en el proyecto (DED-10:
    // nunca se hardcodea una cuenta), así que se crea acá, con códigos
    // únicos por corrida para no chocar con una ejecución previa contra
    // la misma base persistente.
    const acctSuffix = Date.now().toString().slice(-8);
    for (const [role, code, name] of [
      ["receivable", "REC", "Cuentas por Cobrar"],
      ["income", "INC", "Ingresos"],
      ["tax", "TAX", "Impuestos por Pagar"],
    ] as const) {
      const account = await apiRequest<{ id: number }>("/accounting/accounts", {
        method: "POST", body: { code: `M${code}${acctSuffix}`, name, account_type: role },
      });
      try {
        await apiRequest("/accounting/document-account-mappings", {
          method: "POST", body: { document_type: "sales_invoice", role, account_id: account.id },
        });
      } catch (err) {
        // Ya existe un mapeo para (sales_invoice, role) de una corrida
        // previa contra esta misma compañía persistente — el mapeo
        // existente sirve igual, no hace falta que apunte a esta cuenta.
        if (!(err instanceof ApiError) || err.status !== 409) throw err;
      }
    }
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

    // Se resuelven acá (antes que en el cierre original) porque el flujo
    // de Teleconsulta que sigue ya necesita el id real de la cita.
    const appointments = await apiRequest<Array<{ id: number; patient_contact_id: number }>>("/medical/appointments");
    const patients = await apiRequest<Array<{ id: number; name: string }>>("/contacts", { query: { search: patientName } });
    const patientId = patients.find((p) => p.name === patientName)?.id;
    const appointment = appointments.find((a) => a.patient_contact_id === patientId);
    expect(appointment).toBeTruthy();

    // Módulo 12 — Teleconsulta: crear sala, iniciarla, y finalizarla,
    // verificando cada transición real contra el backend (la sección
    // aparece independiente de si ya hay consulta registrada — está
    // vinculada a la cita, no a la consulta).
    await user.click(within(dialog).getByRole("button", { name: /crear sala de videollamada/i }));
    await waitFor(() => expect(within(dialog).getByText(/sala creada/i)).toBeInTheDocument(), { timeout: 10000 });
    expect(within(dialog).getByRole("link", { name: /abrir sala/i })).toHaveAttribute("href", expect.stringContaining("teleconsulta.local"));

    await user.click(within(dialog).getByRole("button", { name: /^iniciar$/i }));
    await waitFor(() => expect(within(dialog).getByText(/en curso/i)).toBeInTheDocument(), { timeout: 10000 });

    await user.click(within(dialog).getByRole("button", { name: /^finalizar$/i }));
    await waitFor(() => expect(within(dialog).getByText(/finalizada/i)).toBeInTheDocument(), { timeout: 10000 });

    const teleconsultation = await apiRequest<{ status: string; started_at: string | null; ended_at: string | null }>(
      `/medical/appointments/${appointment!.id}/teleconsultation`
    );
    expect(teleconsultation.status).toBe("ended");
    expect(teleconsultation.started_at).toBeTruthy();
    expect(teleconsultation.ended_at).toBeTruthy();

    await user.click(within(dialog).getByRole("button", { name: /registrar consulta/i }));
    const diagnosisText = `Diagnóstico de prueba ${Date.now()}`;
    await user.type(within(dialog).getByLabelText("Diagnóstico"), diagnosisText);
    await user.click(within(dialog).getByRole("button", { name: /^guardar consulta$/i }));

    await waitFor(() => expect(within(dialog).getByText(new RegExp(diagnosisText))).toBeInTheDocument(), { timeout: 10000 });

    // Verificación real contra el backend: el diagnóstico viaja cifrado en
    // reposo pero descifrado en la respuesta de la API (comportamiento
    // esperado, no un leak — ver DED-24).

    const consultation = await apiRequest<{ id: number; diagnosis_text: string | null }>(
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

    // Verificación real: con el paquete 'pharmacy' activo para esta
    // compañía de prueba (desde el cierre del módulo 16), dispensing_
    // status debe caer en 'pending' (DED-30) — todavía no se dispensó
    // desde `pharmacy`, solo se emitió la receta acá.
    const prescriptions = await apiRequest<Array<{ consultation_id: number; lines: Array<{ medication_name: string; dispensing_status: string }> }>>(
      `/medical/patients/${patientId}/prescriptions`
    );
    const prescription = prescriptions.find((p) => p.lines.some((l) => l.medication_name === medicationName));
    expect(prescription).toBeTruthy();
    expect(prescription!.lines[0].dispensing_status).toBe("pending");

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

    // Módulo 13 — Facturación Médica Básica: emitir un comprobante (sin
    // el paquete 'administrative' activo en esta compañía de prueba, cae
    // en modo "recibo simple", verificado real contra el backend) y
    // anularlo.
    await user.click(within(dialog).getByRole("button", { name: /^emitir comprobante$/i }));
    await user.type(within(dialog).getByPlaceholderText(/monto/i), "450.00");
    await user.click(within(dialog).getByRole("button", { name: /^emitir$/i }));

    await waitFor(() => expect(within(dialog).getByText(/factura contabilizada/i)).toBeInTheDocument(), { timeout: 10000 });

    const billing = await apiRequest<{ billing_mode: string; invoice_id: number | null; status: string }>(
      `/medical/consultations/${consultation.id}/billing`
    );
    expect(billing.billing_mode).toBe("accounting_invoice");
    expect(billing.invoice_id).toBeTruthy();
    expect(billing.status).toBe("issued");

    await user.type(within(dialog).getByPlaceholderText(/motivo de anulación/i), "Monto incorrecto en esta prueba");
    await user.click(within(dialog).getByRole("button", { name: /^anular$/i }));
    await waitFor(async () => {
      const cancelledBilling = await apiRequest<{ status: string }>(`/medical/consultations/${consultation.id}/billing`);
      expect(cancelledBilling.status).toBe("cancelled");
    }, { timeout: 10000 });

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

  it("envía un mensaje al profesional en nombre del paciente, verifica la notificación real, y lo marca leído", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(screen.getByLabelText("Paciente")).toBeInTheDocument(), { timeout: 15000 });
    await user.click(screen.getByLabelText("Paciente"));
    await user.click(await screen.findByRole("option", { name: patientName }));

    await waitFor(() => expect(screen.getByText("Mensajes")).toBeInTheDocument(), { timeout: 10000 });

    await user.click(screen.getByLabelText("Profesional"));
    await user.click((await screen.findAllByRole("option"))[0]);

    await user.click(screen.getByLabelText("Remitente"));
    await user.click(await screen.findByRole("option", { name: /de parte del paciente/i }));

    const messageBody = `Doctor, sigo con molestias ${Date.now()}`;
    await user.type(screen.getByPlaceholderText("Mensaje…"), messageBody);
    await user.click(screen.getByRole("button", { name: /^enviar$/i }));

    await waitFor(() => expect(screen.getByText(messageBody)).toBeInTheDocument(), { timeout: 10000 });

    // Verificación real: DED-43 — como notifications es Transversal en
    // este proyecto (siempre disponible), el mensaje del paciente debió
    // generar una notificación in-app real para el profesional elegido.
    const patients = await apiRequest<Array<{ id: number; name: string }>>("/contacts", { query: { search: patientName } });
    const patientId = patients.find((p) => p.name === patientName)?.id;
    const messages = await apiRequest<Array<{ id: number; body: string; sender_role: string; professional_user_id: number; read_at: string | null }>>(
      `/medical/patients/${patientId}/messages`
    );
    const sentMessage = messages.find((m) => m.body === messageBody);
    expect(sentMessage).toBeTruthy();
    expect(sentMessage!.sender_role).toBe("patient");
    expect(sentMessage!.read_at).toBeNull();

    const notifications = await apiRequest<Array<{ title: string; recipient_user_id: number }>>("/notifications");
    const messageNotification = notifications.find(
      (n) => n.title === "Nuevo mensaje de paciente" && n.recipient_user_id === sentMessage!.professional_user_id
    );
    expect(messageNotification).toBeTruthy();

    // Marcar leído desde la UI y verificar que persiste.
    await user.click(screen.getByRole("button", { name: /marcar leído/i }));
    await waitFor(async () => {
      const refreshed = await apiRequest<Array<{ id: number; read_at: string | null }>>(`/medical/patients/${patientId}/messages`);
      const found = refreshed.find((m) => m.id === sentMessage!.id);
      expect(found?.read_at).not.toBeNull();
    }, { timeout: 10000 });
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
