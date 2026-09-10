import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useAppointment,
  useConfirmAppointment,
  useRescheduleAppointment,
  useCancelAppointment,
  useConsultationForAppointment,
  useCreateConsultation,
  useCorrectConsultation,
  usePrescriptionsForPatient,
  useCreatePrescription,
  useVoidPrescription,
  useLabOrdersForPatient,
  useCreateLabOrder,
  useEnterLabOrderTestResult,
  useLabOrderTestAttachments,
  useUploadLabOrderTestAttachment,
  downloadMedicalAttachment,
} from "@/hooks/use-medical";
import { useContacts } from "@/hooks/use-contacts";
import { useUsers } from "@/hooks/use-core-data";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = {
  scheduled: "Agendada",
  confirmed: "Confirmada",
  completed: "Completada",
  cancelled: "Cancelada",
  no_show: "No asistió",
};

interface ConsultationFormState {
  physical_exam: string;
  diagnosis_cie10: string;
  diagnosis_text: string;
  treatment_plan: string;
}

const EMPTY_CONSULTATION_FORM: ConsultationFormState = {
  physical_exam: "",
  diagnosis_cie10: "",
  diagnosis_text: "",
  treatment_plan: "",
};

export function AppointmentDetailDialog({ appointmentId, onOpenChange }: { appointmentId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data: appointment, isLoading, error } = useAppointment(appointmentId);
  const { data: consultation } = useConsultationForAppointment(appointmentId);
  const { data: contacts } = useContacts("");
  const { data: users } = useUsers();

  const confirmAppointment = useConfirmAppointment();
  const rescheduleAppointment = useRescheduleAppointment();
  const cancelAppointment = useCancelAppointment();
  const createConsultation = useCreateConsultation();
  const correctConsultation = useCorrectConsultation();

  const [actionError, setActionError] = useState<string | null>(null);
  const [rescheduleStart, setRescheduleStart] = useState("");
  const [rescheduleReason, setRescheduleReason] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [showConsultationForm, setShowConsultationForm] = useState(false);
  const [correctingConsultation, setCorrectingConsultation] = useState(false);
  const [consultationForm, setConsultationForm] = useState<ConsultationFormState>(EMPTY_CONSULTATION_FORM);

  const handleAction = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "No se pudo completar la acción");
    }
  };

  const contactName = (id: number) => contacts?.find((c) => c.id === id)?.name ?? `#${id}`;
  const professionalName = (id: number) => {
    const u = users?.find((u) => u.id === id);
    return u?.full_name ?? u?.email ?? `#${id}`;
  };

  const submitConsultation = async () => {
    if (!appointment) return;
    const payload = {
      physical_exam: consultationForm.physical_exam || null,
      diagnosis_cie10: consultationForm.diagnosis_cie10 || null,
      diagnosis_text: consultationForm.diagnosis_text || null,
      treatment_plan: consultationForm.treatment_plan || null,
    };
    await handleAction(async () => {
      if (correctingConsultation && consultation) {
        await correctConsultation.mutateAsync({ consultationId: consultation.id, payload });
      } else {
        await createConsultation.mutateAsync({ appointment_id: appointment.id, ...payload });
      }
      setShowConsultationForm(false);
      setCorrectingConsultation(false);
      setConsultationForm(EMPTY_CONSULTATION_FORM);
    });
  };

  const startCorrection = () => {
    if (!consultation) return;
    setConsultationForm({
      physical_exam: consultation.physical_exam ?? "",
      diagnosis_cie10: consultation.diagnosis_cie10 ?? "",
      diagnosis_text: consultation.diagnosis_text ?? "",
      treatment_plan: consultation.treatment_plan ?? "",
    });
    setCorrectingConsultation(true);
    setShowConsultationForm(true);
  };

  return (
    <Dialog open={appointmentId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{appointment ? contactName(appointment.patient_contact_id) : "Cita"}</DialogTitle>
          <DialogDescription>
            {appointment
              ? `${STATUS_LABELS[appointment.status]} — ${professionalName(appointment.professional_user_id)} — ${new Date(appointment.scheduled_start).toLocaleString()}`
              : ""}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}

        {appointment && (
          <div className="flex flex-col gap-4">
            {appointment.reason && <p className="text-sm">Motivo: {appointment.reason}</p>}
            {appointment.cancellation_reason && (
              <p className="text-sm text-muted-foreground">Cancelada: {appointment.cancellation_reason}</p>
            )}

            {actionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{actionError}</p>}

            {appointment.status === "scheduled" && (
              <Button size="sm" onClick={() => handleAction(() => confirmAppointment.mutateAsync(appointment.id))}>
                Confirmar
              </Button>
            )}

            {(appointment.status === "scheduled" || appointment.status === "confirmed") && (
              <div className="flex flex-col gap-2 rounded-md border border-border p-3">
                <p className="text-xs font-medium text-muted-foreground">Reprogramar</p>
                <Input type="datetime-local" value={rescheduleStart} onChange={(e) => setRescheduleStart(e.target.value)} />
                <Input placeholder="Motivo de la reprogramación" value={rescheduleReason} onChange={(e) => setRescheduleReason(e.target.value)} />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!rescheduleStart || !rescheduleReason}
                  onClick={() =>
                    handleAction(async () => {
                      const start = new Date(rescheduleStart);
                      const durationMs = new Date(appointment.scheduled_end).getTime() - new Date(appointment.scheduled_start).getTime();
                      const end = new Date(start.getTime() + durationMs);
                      await rescheduleAppointment.mutateAsync({
                        appointmentId: appointment.id,
                        payload: { scheduled_start: start.toISOString(), scheduled_end: end.toISOString(), reason: rescheduleReason },
                      });
                      setRescheduleStart("");
                      setRescheduleReason("");
                    })
                  }
                >
                  Reprogramar
                </Button>

                <p className="mt-2 text-xs font-medium text-muted-foreground">Cancelar</p>
                <Input placeholder="Motivo de cancelación" value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} />
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={!cancelReason}
                  onClick={() =>
                    handleAction(async () => {
                      await cancelAppointment.mutateAsync({ appointmentId: appointment.id, payload: { cancellation_reason: cancelReason } });
                      setCancelReason("");
                    })
                  }
                >
                  Cancelar cita
                </Button>
              </div>
            )}

            <div className="flex flex-col gap-2 rounded-md border border-border p-3">
              <p className="text-xs font-medium text-muted-foreground">Consulta</p>

              {consultation && !showConsultationForm && (
                <div className="flex flex-col gap-1 text-sm">
                  {consultation.diagnosis_cie10 && <p><span className="text-muted-foreground">CIE-10:</span> {consultation.diagnosis_cie10}</p>}
                  {consultation.diagnosis_text && <p><span className="text-muted-foreground">Diagnóstico:</span> {consultation.diagnosis_text}</p>}
                  {consultation.treatment_plan && <p><span className="text-muted-foreground">Plan:</span> {consultation.treatment_plan}</p>}
                  {consultation.physical_exam && <p><span className="text-muted-foreground">Examen físico:</span> {consultation.physical_exam}</p>}
                  <Button size="sm" variant="outline" className="mt-1 w-fit" onClick={startCorrection}>
                    Corregir
                  </Button>
                </div>
              )}

              {!consultation && !showConsultationForm && (appointment.status === "scheduled" || appointment.status === "confirmed") && (
                <Button size="sm" variant="outline" className="w-fit" onClick={() => setShowConsultationForm(true)}>
                  Registrar consulta
                </Button>
              )}

              {!consultation && !showConsultationForm && appointment.status !== "scheduled" && appointment.status !== "confirmed" && (
                <p className="text-xs text-muted-foreground">Sin consulta registrada.</p>
              )}

              {showConsultationForm && (
                <div className="flex flex-col gap-2">
                  {correctingConsultation && (
                    <p className="text-xs text-muted-foreground">
                      Esto crea una versión corregida — la anterior queda en el historial, no se sobrescribe.
                    </p>
                  )}
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="physical_exam">Examen físico</Label>
                    <Input
                      id="physical_exam"
                      value={consultationForm.physical_exam}
                      onChange={(e) => setConsultationForm((f) => ({ ...f, physical_exam: e.target.value }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="diagnosis_cie10">Diagnóstico CIE-10 (opcional)</Label>
                    <Input
                      id="diagnosis_cie10"
                      value={consultationForm.diagnosis_cie10}
                      onChange={(e) => setConsultationForm((f) => ({ ...f, diagnosis_cie10: e.target.value }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="diagnosis_text">Diagnóstico</Label>
                    <Input
                      id="diagnosis_text"
                      value={consultationForm.diagnosis_text}
                      onChange={(e) => setConsultationForm((f) => ({ ...f, diagnosis_text: e.target.value }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="treatment_plan">Plan de tratamiento</Label>
                    <Input
                      id="treatment_plan"
                      value={consultationForm.treatment_plan}
                      onChange={(e) => setConsultationForm((f) => ({ ...f, treatment_plan: e.target.value }))}
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={submitConsultation}>
                      {correctingConsultation ? "Guardar corrección" : "Guardar consulta"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setShowConsultationForm(false);
                        setCorrectingConsultation(false);
                        setConsultationForm(EMPTY_CONSULTATION_FORM);
                      }}
                    >
                      Cancelar
                    </Button>
                  </div>
                </div>
              )}
            </div>

            {consultation && (
              <PrescriptionsSection consultation={consultation} patientContactId={appointment.patient_contact_id} />
            )}

            {consultation && (
              <LabOrdersSection consultation={consultation} patientContactId={appointment.patient_contact_id} />
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Módulo 10 — Recetas
// ---------------------------------------------------------------------------
interface PrescriptionLineFormState {
  medication_name: string;
  dosage: string;
  route: string;
  frequency: string;
  duration: string;
}

const EMPTY_LINE: PrescriptionLineFormState = { medication_name: "", dosage: "", route: "", frequency: "", duration: "" };

function PrescriptionsSection({ consultation, patientContactId }: { consultation: { id: number }; patientContactId: number }) {
  const { data: allPrescriptions } = usePrescriptionsForPatient(patientContactId);
  const createPrescription = useCreatePrescription();
  const voidPrescription = useVoidPrescription();

  const [showForm, setShowForm] = useState(false);
  const [lines, setLines] = useState<PrescriptionLineFormState[]>([{ ...EMPTY_LINE }]);
  const [prescriptionError, setPrescriptionError] = useState<string | null>(null);
  const [voidReasonByPrescription, setVoidReasonByPrescription] = useState<Record<number, string>>({});

  const prescriptions = (allPrescriptions ?? []).filter((p) => p.consultation_id === consultation.id);

  const updateLine = (index: number, patch: Partial<PrescriptionLineFormState>) => {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  };

  const submitPrescription = async () => {
    setPrescriptionError(null);
    try {
      await createPrescription.mutateAsync({
        consultation_id: consultation.id,
        lines: lines as Parameters<typeof createPrescription.mutateAsync>[0]["lines"],
      });
      setLines([{ ...EMPTY_LINE }]);
      setShowForm(false);
    } catch (err) {
      setPrescriptionError(err instanceof ApiError ? err.message : "No se pudo emitir la receta");
    }
  };

  const submitVoid = async (prescriptionId: number) => {
    const reason = voidReasonByPrescription[prescriptionId];
    if (!reason) return;
    try {
      await voidPrescription.mutateAsync({ prescriptionId, payload: { void_reason: reason } });
      setVoidReasonByPrescription((prev) => ({ ...prev, [prescriptionId]: "" }));
    } catch (err) {
      setPrescriptionError(err instanceof ApiError ? err.message : "No se pudo anular la receta");
    }
  };

  const linesComplete = lines.every((l) => l.medication_name && l.dosage && l.route && l.frequency && l.duration);

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3">
      <p className="text-xs font-medium text-muted-foreground">Recetas</p>

      {prescriptions.map((p) => (
        <div key={p.id} className="flex flex-col gap-1 rounded-md border border-border p-2 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">{new Date(p.issued_at).toLocaleString()}</span>
            {p.voided_at ? (
              <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">
                Anulada
              </span>
            ) : null}
          </div>
          <ul className="flex flex-col gap-0.5">
            {p.lines.map((line) => (
              <li key={line.id}>
                {line.medication_name} — {line.dosage}, {line.route}, {line.frequency}, {line.duration}
              </li>
            ))}
          </ul>
          {p.voided_at && p.void_reason && <p className="text-xs text-muted-foreground">Motivo: {p.void_reason}</p>}
          {!p.voided_at && (
            <div className="flex gap-2">
              <Input
                placeholder="Motivo de anulación"
                value={voidReasonByPrescription[p.id] ?? ""}
                onChange={(e) => setVoidReasonByPrescription((prev) => ({ ...prev, [p.id]: e.target.value }))}
              />
              <Button size="sm" variant="destructive" disabled={!voidReasonByPrescription[p.id]} onClick={() => submitVoid(p.id)}>
                Anular
              </Button>
            </div>
          )}
        </div>
      ))}

      {!showForm && (
        <Button size="sm" variant="outline" className="w-fit" onClick={() => setShowForm(true)}>
          Nueva receta
        </Button>
      )}

      {showForm && (
        <div className="flex flex-col gap-2">
          {lines.map((line, i) => (
            <div key={i} className="flex flex-col gap-1 rounded-md border border-border p-2">
              <Input placeholder="Medicamento" value={line.medication_name} onChange={(e) => updateLine(i, { medication_name: e.target.value })} />
              <div className="grid grid-cols-2 gap-1">
                <Input placeholder="Dosis (ej. 500mg)" value={line.dosage} onChange={(e) => updateLine(i, { dosage: e.target.value })} />
                <Input placeholder="Vía (ej. oral)" value={line.route} onChange={(e) => updateLine(i, { route: e.target.value })} />
                <Input placeholder="Frecuencia" value={line.frequency} onChange={(e) => updateLine(i, { frequency: e.target.value })} />
                <Input placeholder="Duración" value={line.duration} onChange={(e) => updateLine(i, { duration: e.target.value })} />
              </div>
              {lines.length > 1 && (
                <Button size="sm" variant="ghost" className="w-fit" onClick={() => setLines((prev) => prev.filter((_, idx) => idx !== i))}>
                  Quitar medicamento
                </Button>
              )}
            </div>
          ))}
          <Button size="sm" variant="ghost" className="w-fit" onClick={() => setLines((prev) => [...prev, { ...EMPTY_LINE }])}>
            + Agregar medicamento
          </Button>
          {prescriptionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{prescriptionError}</p>}
          <div className="flex gap-2">
            <Button size="sm" disabled={!linesComplete} onClick={submitPrescription}>
              Emitir receta
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setShowForm(false); setLines([{ ...EMPTY_LINE }]); }}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Módulo 11 — Laboratorio
// ---------------------------------------------------------------------------
function LabOrdersSection({ consultation, patientContactId }: { consultation: { id: number }; patientContactId: number }) {
  const { data: allLabOrders } = useLabOrdersForPatient(patientContactId);
  const createLabOrder = useCreateLabOrder();

  const [showForm, setShowForm] = useState(false);
  const [testNames, setTestNames] = useState<string[]>([""]);
  const [labOrderError, setLabOrderError] = useState<string | null>(null);

  const labOrders = (allLabOrders ?? []).filter((o) => o.consultation_id === consultation.id);

  const submitLabOrder = async () => {
    setLabOrderError(null);
    try {
      await createLabOrder.mutateAsync({
        consultation_id: consultation.id,
        tests: testNames.filter((n) => n.trim()).map((n) => ({ test_name: n })),
      });
      setTestNames([""]);
      setShowForm(false);
    } catch (err) {
      setLabOrderError(err instanceof ApiError ? err.message : "No se pudo crear la orden de laboratorio");
    }
  };

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3">
      <p className="text-xs font-medium text-muted-foreground">Laboratorio</p>

      {labOrders.map((order) => (
        <div key={order.id} className="flex flex-col gap-2 rounded-md border border-border p-2 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">{new Date(order.ordered_at).toLocaleString()}</span>
            <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-secondary-foreground">
              {order.status === "completed" ? "Completada" : order.status === "cancelled" ? "Cancelada" : "Ordenada"}
            </span>
          </div>
          {order.tests.map((test) => (
            <LabOrderTestRow key={test.id} test={test} patientContactId={patientContactId} />
          ))}
        </div>
      ))}

      {!showForm && (
        <Button size="sm" variant="outline" className="w-fit" onClick={() => setShowForm(true)}>
          Nueva orden
        </Button>
      )}

      {showForm && (
        <div className="flex flex-col gap-2">
          {testNames.map((name, i) => (
            <div key={i} className="flex gap-1">
              <Input
                placeholder="Nombre de la prueba (ej. Hemograma completo)"
                value={name}
                onChange={(e) => setTestNames((prev) => prev.map((n, idx) => (idx === i ? e.target.value : n)))}
              />
              {testNames.length > 1 && (
                <Button size="sm" variant="ghost" onClick={() => setTestNames((prev) => prev.filter((_, idx) => idx !== i))}>
                  Quitar
                </Button>
              )}
            </div>
          ))}
          <Button size="sm" variant="ghost" className="w-fit" onClick={() => setTestNames((prev) => [...prev, ""])}>
            + Agregar prueba
          </Button>
          {labOrderError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{labOrderError}</p>}
          <div className="flex gap-2">
            <Button size="sm" disabled={!testNames.some((n) => n.trim())} onClick={submitLabOrder}>
              Ordenar
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setShowForm(false); setTestNames([""]); }}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function LabOrderTestRow({
  test, patientContactId,
}: {
  test: { id: number; test_name: string; status: string; result_value: string | null; result_unit: string | null; reference_range_text: string | null; is_critical: boolean };
  patientContactId: number;
}) {
  const enterResult = useEnterLabOrderTestResult(patientContactId);
  const { data: attachments } = useLabOrderTestAttachments(test.id);
  const uploadAttachment = useUploadLabOrderTestAttachment();

  const [showResultForm, setShowResultForm] = useState(false);
  const [resultValue, setResultValue] = useState("");
  const [resultUnit, setResultUnit] = useState("");
  const [referenceRange, setReferenceRange] = useState("");
  const [isCritical, setIsCritical] = useState(false);
  const [resultError, setResultError] = useState<string | null>(null);

  const submitResult = async () => {
    setResultError(null);
    try {
      await enterResult.mutateAsync({
        labOrderTestId: test.id,
        payload: { result_value: resultValue, result_unit: resultUnit || null, reference_range_text: referenceRange || null, is_critical: isCritical },
      });
      setShowResultForm(false);
    } catch (err) {
      setResultError(err instanceof ApiError ? err.message : "No se pudo cargar el resultado");
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadAttachment.mutateAsync({ labOrderTestId: test.id, file });
    e.target.value = "";
  };

  return (
    <div className="flex flex-col gap-1 border-t border-border pt-1 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between">
        <span>{test.test_name}</span>
        {test.is_critical && (
          <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">Crítico</span>
        )}
      </div>

      {test.status === "resulted" ? (
        <p className="text-xs text-muted-foreground">
          {test.result_value} {test.result_unit ?? ""}
          {test.reference_range_text ? ` (ref: ${test.reference_range_text})` : ""}
        </p>
      ) : !showResultForm ? (
        <Button size="sm" variant="outline" className="w-fit" onClick={() => setShowResultForm(true)}>
          Cargar resultado
        </Button>
      ) : (
        <div className="flex flex-col gap-1">
          <div className="grid grid-cols-2 gap-1">
            <Input placeholder="Valor" value={resultValue} onChange={(e) => setResultValue(e.target.value)} />
            <Input placeholder="Unidad" value={resultUnit} onChange={(e) => setResultUnit(e.target.value)} />
          </div>
          <Input placeholder="Rango de referencia (ej. 70-100 mg/dL)" value={referenceRange} onChange={(e) => setReferenceRange(e.target.value)} />
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" checked={isCritical} onChange={(e) => setIsCritical(e.target.checked)} />
            Marcar como valor crítico
          </label>
          {resultError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{resultError}</p>}
          <div className="flex gap-2">
            <Button size="sm" disabled={!resultValue} onClick={submitResult}>Guardar resultado</Button>
            <Button size="sm" variant="ghost" onClick={() => setShowResultForm(false)}>Cancelar</Button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {(attachments ?? []).map((a) => (
          <button
            key={a.id}
            className="text-xs text-primary underline"
            onClick={() => downloadMedicalAttachment(a.id, a.filename)}
          >
            {a.filename}
          </button>
        ))}
        <label className="cursor-pointer text-xs text-muted-foreground underline">
          Adjuntar archivo
          <input type="file" className="hidden" onChange={handleFileChange} />
        </label>
      </div>
    </div>
  );
}
