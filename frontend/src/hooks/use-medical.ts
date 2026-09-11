import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, apiUploadFile, apiDownloadFile, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";

type ClinicalRecordEntryRead = components["schemas"]["ClinicalRecordEntryRead"];
type AppointmentRead = components["schemas"]["AppointmentRead"];
type ConsultationRead = components["schemas"]["ConsultationRead"];

type ClinicalRecordEntryCreate = z.infer<typeof schemas.ClinicalRecordEntryCreate>;
type AppointmentCreate = z.infer<typeof schemas.AppointmentCreate>;
type AppointmentReschedule = z.infer<typeof schemas.AppointmentReschedule>;
type AppointmentCancel = z.infer<typeof schemas.AppointmentCancel>;
type ConsultationCreate = z.infer<typeof schemas.ConsultationCreate>;
type ConsultationCorrect = z.infer<typeof schemas.ConsultationCorrect>;

// ---------------------------------------------------------------------------
// Expediente Clínico
// ---------------------------------------------------------------------------
export function usePatientRecords(patientContactId: number | null) {
  return useQuery({
    queryKey: ["medical", "records", patientContactId],
    queryFn: () =>
      apiRequest<ClinicalRecordEntryRead[]>(`/medical/patients/${patientContactId}/records`, {
        responseSchema: schemas.ClinicalRecordEntryRead.array(),
      }),
    enabled: patientContactId !== null,
  });
}

export function useCreateRecordEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ClinicalRecordEntryCreate) =>
      apiRequest<ClinicalRecordEntryRead>("/medical/records", {
        method: "POST",
        body: payload,
        responseSchema: schemas.ClinicalRecordEntryRead,
      }),
    onSuccess: (entry) => qc.invalidateQueries({ queryKey: ["medical", "records", entry.patient_contact_id] }),
  });
}

// ---------------------------------------------------------------------------
// Agenda Médica
// ---------------------------------------------------------------------------
export function useAppointments(filters?: { professional_user_id?: number; patient_contact_id?: number }) {
  return useQuery({
    queryKey: ["medical", "appointments", filters ?? {}],
    queryFn: () =>
      apiRequest<AppointmentRead[]>("/medical/appointments", {
        query: filters,
        responseSchema: schemas.AppointmentRead.array(),
      }),
  });
}

export function useAppointment(appointmentId: number | null) {
  return useQuery({
    queryKey: ["medical", "appointments", "detail", appointmentId],
    queryFn: () => apiRequest<AppointmentRead>(`/medical/appointments/${appointmentId}`, { responseSchema: schemas.AppointmentRead }),
    enabled: appointmentId !== null,
  });
}

export function useCreateAppointment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AppointmentCreate) =>
      apiRequest<AppointmentRead>("/medical/appointments", { method: "POST", body: payload, responseSchema: schemas.AppointmentRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["medical", "appointments"] }),
  });
}

export function useConfirmAppointment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (appointmentId: number) =>
      apiRequest<AppointmentRead>(`/medical/appointments/${appointmentId}/confirm`, { method: "POST", responseSchema: schemas.AppointmentRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["medical", "appointments"] }),
  });
}

export function useRescheduleAppointment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ appointmentId, payload }: { appointmentId: number; payload: AppointmentReschedule }) =>
      apiRequest<AppointmentRead>(`/medical/appointments/${appointmentId}/reschedule`, {
        method: "POST",
        body: payload,
        responseSchema: schemas.AppointmentRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["medical", "appointments"] }),
  });
}

export function useCancelAppointment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ appointmentId, payload }: { appointmentId: number; payload: AppointmentCancel }) =>
      apiRequest<AppointmentRead>(`/medical/appointments/${appointmentId}/cancel`, {
        method: "POST",
        body: payload,
        responseSchema: schemas.AppointmentRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["medical", "appointments"] }),
  });
}

// ---------------------------------------------------------------------------
// Consulta
// ---------------------------------------------------------------------------
export function useConsultationForAppointment(appointmentId: number | null) {
  return useQuery({
    queryKey: ["medical", "appointments", "consultation", appointmentId],
    queryFn: () =>
      apiRequest<ConsultationRead | null>(`/medical/appointments/${appointmentId}/consultation`, {
        responseSchema: schemas.ConsultationRead.nullable(),
      }),
    enabled: appointmentId !== null,
  });
}

export function useConsultation(consultationId: number | null) {
  return useQuery({
    queryKey: ["medical", "consultations", consultationId],
    queryFn: () => apiRequest<ConsultationRead>(`/medical/consultations/${consultationId}`, { responseSchema: schemas.ConsultationRead }),
    enabled: consultationId !== null,
  });
}

export function useCreateConsultation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ConsultationCreate) =>
      apiRequest<ConsultationRead>("/medical/consultations", { method: "POST", body: payload, responseSchema: schemas.ConsultationRead }),
    onSuccess: (consultation) => {
      qc.invalidateQueries({ queryKey: ["medical", "appointments"] });
      qc.invalidateQueries({ queryKey: ["medical", "consultations", consultation.id] });
      qc.invalidateQueries({ queryKey: ["medical", "appointments", "consultation", consultation.appointment_id] });
    },
  });
}

export function useCorrectConsultation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ consultationId, payload }: { consultationId: number; payload: ConsultationCorrect }) =>
      apiRequest<ConsultationRead>(`/medical/consultations/${consultationId}/correct`, {
        method: "POST",
        body: payload,
        responseSchema: schemas.ConsultationRead,
      }),
    onSuccess: (consultation) => {
      qc.invalidateQueries({ queryKey: ["medical", "consultations"] });
      qc.invalidateQueries({ queryKey: ["medical", "consultations", consultation.id] });
      qc.invalidateQueries({ queryKey: ["medical", "appointments", "consultation", consultation.appointment_id] });
    },
  });
}

// ---------------------------------------------------------------------------
// Módulo 10 — Recetas
// ---------------------------------------------------------------------------
type PrescriptionRead = components["schemas"]["PrescriptionRead"];
type PrescriptionCreate = z.infer<typeof schemas.PrescriptionCreate>;
type PrescriptionVoid = z.infer<typeof schemas.PrescriptionVoid>;

export function usePrescriptionsForPatient(patientContactId: number | null) {
  return useQuery({
    queryKey: ["medical", "prescriptions", "patient", patientContactId],
    queryFn: () =>
      apiRequest<PrescriptionRead[]>(`/medical/patients/${patientContactId}/prescriptions`, {
        responseSchema: schemas.PrescriptionRead.array(),
      }),
    enabled: patientContactId !== null,
  });
}

export function useCreatePrescription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PrescriptionCreate) =>
      apiRequest<PrescriptionRead>("/medical/prescriptions", { method: "POST", body: payload, responseSchema: schemas.PrescriptionRead }),
    onSuccess: (prescription) =>
      qc.invalidateQueries({ queryKey: ["medical", "prescriptions", "patient", prescription.patient_contact_id] }),
  });
}

export function useVoidPrescription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ prescriptionId, payload }: { prescriptionId: number; payload: PrescriptionVoid }) =>
      apiRequest<PrescriptionRead>(`/medical/prescriptions/${prescriptionId}/void`, {
        method: "POST",
        body: payload,
        responseSchema: schemas.PrescriptionRead,
      }),
    onSuccess: (prescription) =>
      qc.invalidateQueries({ queryKey: ["medical", "prescriptions", "patient", prescription.patient_contact_id] }),
  });
}

// ---------------------------------------------------------------------------
// Módulo 11 — Laboratorio
// ---------------------------------------------------------------------------
type LabOrderRead = components["schemas"]["LabOrderRead"];
type LabOrderCreate = z.infer<typeof schemas.LabOrderCreate>;
type LabOrderTestResult = z.infer<typeof schemas.LabOrderTestResult>;
type AttachmentRead = components["schemas"]["AttachmentRead"];

export function useLabOrdersForPatient(patientContactId: number | null) {
  return useQuery({
    queryKey: ["medical", "lab-orders", "patient", patientContactId],
    queryFn: () =>
      apiRequest<LabOrderRead[]>(`/medical/patients/${patientContactId}/lab-orders`, {
        responseSchema: schemas.LabOrderRead.array(),
      }),
    enabled: patientContactId !== null,
  });
}

export function useCreateLabOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LabOrderCreate) =>
      apiRequest<LabOrderRead>("/medical/lab-orders", { method: "POST", body: payload, responseSchema: schemas.LabOrderRead }),
    onSuccess: (labOrder) => qc.invalidateQueries({ queryKey: ["medical", "lab-orders", "patient", labOrder.patient_contact_id] }),
  });
}

export function useEnterLabOrderTestResult(patientContactId: number | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ labOrderTestId, payload }: { labOrderTestId: number; payload: LabOrderTestResult }) =>
      apiRequest(`/medical/lab-order-tests/${labOrderTestId}/result`, { method: "POST", body: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["medical", "lab-orders", "patient", patientContactId] }),
  });
}

export function useLabOrderTestAttachments(labOrderTestId: number | null) {
  return useQuery({
    queryKey: ["medical", "lab-order-tests", labOrderTestId, "attachments"],
    queryFn: () =>
      apiRequest<AttachmentRead[]>(`/medical/lab-order-tests/${labOrderTestId}/attachments`, {
        responseSchema: schemas.AttachmentRead.array(),
      }),
    enabled: labOrderTestId !== null,
  });
}

export function useUploadLabOrderTestAttachment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ labOrderTestId, file }: { labOrderTestId: number; file: File }) =>
      apiUploadFile<AttachmentRead>(`/medical/lab-order-tests/${labOrderTestId}/attachments`, file, {
        responseSchema: schemas.AttachmentRead,
      }),
    onSuccess: (_data, variables) =>
      qc.invalidateQueries({ queryKey: ["medical", "lab-order-tests", variables.labOrderTestId, "attachments"] }),
  });
}

export function downloadMedicalAttachment(attachmentId: number, filename: string) {
  return apiDownloadFile(`/medical/attachments/${attachmentId}/download`, filename);
}

// ---------------------------------------------------------------------------------
// Módulo 12 — Teleconsulta
// ---------------------------------------------------------------------------
type TeleconsultationSessionRead = components["schemas"]["TeleconsultationSessionRead"];
type TeleconsultationSessionCreate = z.infer<typeof schemas.TeleconsultationSessionCreate>;

export function useTeleconsultationForAppointment(appointmentId: number | null) {
  return useQuery({
    queryKey: ["medical", "appointments", "teleconsultation", appointmentId],
    queryFn: () =>
      apiRequest<TeleconsultationSessionRead | null>(`/medical/appointments/${appointmentId}/teleconsultation`, {
        responseSchema: schemas.TeleconsultationSessionRead.nullable(),
      }),
    enabled: appointmentId !== null,
  });
}

export function useCreateTeleconsultation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TeleconsultationSessionCreate) =>
      apiRequest<TeleconsultationSessionRead>("/medical/teleconsultations", {
        method: "POST", body: payload, responseSchema: schemas.TeleconsultationSessionRead,
      }),
    onSuccess: (session) =>
      qc.invalidateQueries({ queryKey: ["medical", "appointments", "teleconsultation", session.appointment_id] }),
  });
}

export function useStartTeleconsultation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: number) =>
      apiRequest<TeleconsultationSessionRead>(`/medical/teleconsultations/${sessionId}/start`, {
        method: "POST", responseSchema: schemas.TeleconsultationSessionRead,
      }),
    onSuccess: (session) =>
      qc.invalidateQueries({ queryKey: ["medical", "appointments", "teleconsultation", session.appointment_id] }),
  });
}

export function useEndTeleconsultation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: number) =>
      apiRequest<TeleconsultationSessionRead>(`/medical/teleconsultations/${sessionId}/end`, {
        method: "POST", responseSchema: schemas.TeleconsultationSessionRead,
      }),
    onSuccess: (session) =>
      qc.invalidateQueries({ queryKey: ["medical", "appointments", "teleconsultation", session.appointment_id] }),
  });
}
