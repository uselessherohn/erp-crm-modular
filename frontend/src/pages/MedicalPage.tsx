import { useState } from "react";
import { useContacts } from "@/hooks/use-contacts";
import { useUsers } from "@/hooks/use-core-data";
import { useAppointments, usePatientRecords, useCreateRecordEntry, usePatientMessages, useSendPatientMessage, useMarkPatientMessageRead } from "@/hooks/use-medical";
import { CreateAppointmentDialog } from "@/components/CreateAppointmentDialog";
import { AppointmentDetailDialog } from "@/components/AppointmentDetailDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = {
  scheduled: "Agendada",
  confirmed: "Confirmada",
  completed: "Completada",
  cancelled: "Cancelada",
  no_show: "No asistió",
};

const STATUS_STYLES: Record<string, string> = {
  scheduled: "bg-secondary text-secondary-foreground",
  confirmed: "bg-primary/10 text-primary",
  completed: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-destructive/10 text-destructive",
  no_show: "bg-muted text-muted-foreground",
};

const ENTRY_TYPE_LABELS: Record<string, string> = {
  antecedent: "Antecedente",
  allergy: "Alergia",
  diagnosis: "Diagnóstico",
  note: "Nota",
};

export function MedicalPage() {
  const { data: contacts } = useContacts("");
  const { data: users } = useUsers();
  const { data: appointments, isLoading: appointmentsLoading, error: appointmentsError } = useAppointments();
  const [selectedAppointmentId, setSelectedAppointmentId] = useState<number | null>(null);

  const patients = (contacts ?? []).filter((c) => c.is_patient);
  const [selectedPatientId, setSelectedPatientId] = useState<number | null>(null);
  const { data: records, isLoading: recordsLoading } = usePatientRecords(selectedPatientId);
  const createRecordEntry = useCreateRecordEntry();

  const [entryType, setEntryType] = useState("note");
  const [entryContent, setEntryContent] = useState("");
  const [correctingEntryId, setCorrectingEntryId] = useState<number | null>(null);
  const [recordError, setRecordError] = useState<string | null>(null);

  const contactName = (id: number) => contacts?.find((c) => c.id === id)?.name ?? `#${id}`;
  const professionalName = (id: number) => {
    const u = users?.find((u) => u.id === id);
    return u?.full_name ?? u?.email ?? `#${id}`;
  };

  const submitEntry = async () => {
    if (!selectedPatientId || !entryContent.trim()) return;
    setRecordError(null);
    try {
      await createRecordEntry.mutateAsync({
        patient_contact_id: selectedPatientId,
        entry_type: entryType as "antecedent" | "allergy" | "diagnosis" | "note",
        content: entryContent,
        previous_entry_id: correctingEntryId,
      });
      setEntryContent("");
      setCorrectingEntryId(null);
    } catch (err) {
      setRecordError(err instanceof ApiError ? err.message : "No se pudo guardar la entrada");
    }
  };

  const sortedAppointments = [...(appointments ?? [])].sort(
    (a, b) => new Date(a.scheduled_start).getTime() - new Date(b.scheduled_start).getTime()
  );

  return (
    <div className="flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-medium text-foreground">Médico</h1>
        <p className="text-sm text-muted-foreground">Agenda de citas y Expediente Clínico.</p>
      </header>

      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium text-foreground">Agenda</h2>
          <CreateAppointmentDialog />
        </div>

        {appointmentsLoading && <p className="text-sm text-muted-foreground">Cargando citas…</p>}
        {appointmentsError instanceof ApiError && (
          <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {appointmentsError.message}
          </p>
        )}
        {!appointmentsLoading && sortedAppointments.length === 0 && (
          <p className="text-sm text-muted-foreground">Sin citas agendadas todavía.</p>
        )}

        <div className="flex flex-col divide-y divide-border rounded-md border border-border">
          {sortedAppointments.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelectedAppointmentId(a.id)}
              aria-label={`Cita de ${contactName(a.patient_contact_id)}`}
              className="flex items-center justify-between gap-4 px-4 py-3 text-left text-sm hover:bg-muted"
            >
              <div className="flex flex-col">
                <span className="font-medium text-foreground">{contactName(a.patient_contact_id)}</span>
                <span className="text-xs text-muted-foreground">
                  {professionalName(a.professional_user_id)} — {new Date(a.scheduled_start).toLocaleString()}
                </span>
              </div>
              <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", STATUS_STYLES[a.status])}>
                {STATUS_LABELS[a.status]}
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-medium text-foreground">Expediente Clínico</h2>

        <div className="max-w-xs">
          <Select value={selectedPatientId ? String(selectedPatientId) : ""} onValueChange={(v) => setSelectedPatientId(Number(v))}>
            <SelectTrigger aria-label="Paciente"><SelectValue placeholder="Elegí un paciente" /></SelectTrigger>
            <SelectContent>
              {patients.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {selectedPatientId && (
          <>
            {recordsLoading && <p className="text-sm text-muted-foreground">Cargando expediente…</p>}
            {!recordsLoading && (records ?? []).length === 0 && (
              <p className="text-sm text-muted-foreground">Sin entradas en el expediente todavía.</p>
            )}
            <div className="flex flex-col gap-3">
              {[...(records ?? [])].reverse().map((entry) => (
                <div key={entry.id} className="rounded-md border border-border p-3">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground">
                      {ENTRY_TYPE_LABELS[entry.entry_type]}
                    </span>
                    <span className="text-xs text-muted-foreground">{new Date(entry.created_at).toLocaleString()}</span>
                  </div>
                  <p className="text-sm text-foreground">{entry.content}</p>
                  {entry.previous_entry_id && (
                    <p className="mt-1 text-xs text-muted-foreground">Corrige la entrada #{entry.previous_entry_id}</p>
                  )}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="mt-1 h-auto p-0 text-xs"
                    onClick={() => {
                      setCorrectingEntryId(entry.id);
                      setEntryType(entry.entry_type);
                      setEntryContent(entry.content);
                    }}
                  >
                    Corregir
                  </Button>
                </div>
              ))}
            </div>

            <div className="flex flex-col gap-2 rounded-md border border-border p-3">
              <p className="text-xs font-medium text-muted-foreground">
                {correctingEntryId ? `Corrección de la entrada #${correctingEntryId}` : "Nueva entrada"}
              </p>
              <Select value={entryType} onValueChange={setEntryType}>
                <SelectTrigger aria-label="Tipo de entrada" className="max-w-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(ENTRY_TYPE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <textarea
                value={entryContent}
                onChange={(e) => setEntryContent(e.target.value)}
                placeholder="Contenido de la entrada…"
                rows={3}
                className="flex w-full rounded-md border border-input bg-card px-3 py-2 text-sm placeholder:text-muted-foreground"
              />
              {recordError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{recordError}</p>}
              <div className="flex gap-2">
                <Button size="sm" disabled={!entryContent.trim()} onClick={submitEntry}>
                  {correctingEntryId ? "Guardar corrección" : "Guardar entrada"}
                </Button>
                {correctingEntryId && (
                  <Button size="sm" variant="ghost" onClick={() => { setCorrectingEntryId(null); setEntryContent(""); }}>
                    Cancelar corrección
                  </Button>
                )}
              </div>
            </div>
          </>
        )}
      </section>

      {selectedPatientId && <MessagesSection patientContactId={selectedPatientId} />}

      <AppointmentDetailDialog appointmentId={selectedAppointmentId} onOpenChange={(open) => !open && setSelectedAppointmentId(null)} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Módulo 14 — Portal / Mensajería Paciente-Médico
// ---------------------------------------------------------------------------
function MessagesSection({ patientContactId }: { patientContactId: number }) {
  const { data: users } = useUsers();
  // Poll simple cada 30s, mismo criterio que la campana de notifications
  // (sin WebSocket/SSE en este cierre).
  const { data: messages, isLoading } = usePatientMessages(patientContactId, { pollMs: 30_000 });
  const sendMessage = useSendPatientMessage();
  const markRead = useMarkPatientMessageRead();

  const [professionalId, setProfessionalId] = useState("");
  const [senderRole, setSenderRole] = useState<"professional" | "patient">("professional");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const professionalName = (id: number) => {
    const u = users?.find((u) => u.id === id);
    return u?.full_name ?? u?.email ?? `#${id}`;
  };

  const submit = async () => {
    if (!professionalId || !body.trim()) return;
    setError(null);
    try {
      await sendMessage.mutateAsync({
        patient_contact_id: patientContactId, professional_user_id: Number(professionalId),
        sender_role: senderRole, body,
      });
      setBody("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo enviar el mensaje");
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-foreground">Mensajes</h2>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando mensajes…</p>}
      {!isLoading && (messages ?? []).length === 0 && <p className="text-sm text-muted-foreground">Sin mensajes todavía.</p>}

      <div className="flex flex-col gap-2">
        {(messages ?? []).map((m) => (
          <div
            key={m.id}
            className={cn(
              "flex max-w-md flex-col gap-0.5 rounded-md border border-border p-2 text-sm",
              m.sender_role === "patient" ? "self-start bg-secondary/50" : "self-end bg-primary/5"
            )}
          >
            <span className="text-xs font-medium text-muted-foreground">
              {m.sender_role === "patient" ? "Paciente" : professionalName(m.professional_user_id)}
            </span>
            <p>{m.body}</p>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-muted-foreground">{new Date(m.created_at).toLocaleString()}</span>
              {m.sender_role === "patient" && !m.read_at && (
                <button className="text-[10px] text-primary underline" onClick={() => markRead.mutate(m.id)}>
                  Marcar leído
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <div className="grid grid-cols-2 gap-2">
          <Select value={professionalId} onValueChange={setProfessionalId}>
            <SelectTrigger aria-label="Profesional"><SelectValue placeholder="Profesional" /></SelectTrigger>
            <SelectContent>
              {users?.map((u) => <SelectItem key={u.id} value={String(u.id)}>{u.full_name ?? u.email}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={senderRole} onValueChange={(v) => setSenderRole(v as "professional" | "patient")}>
            <SelectTrigger aria-label="Remitente"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="professional">De parte del profesional</SelectItem>
              <SelectItem value="patient">De parte del paciente (transcrito)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Input placeholder="Mensaje…" value={body} onChange={(e) => setBody(e.target.value)} />
        {error && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        <Button size="sm" className="w-fit" disabled={!professionalId || !body.trim()} onClick={submit}>
          Enviar
        </Button>
      </div>
    </section>
  );
}
