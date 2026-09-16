import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";
import {
  MtmSessionRead,
  MtmBillingRecordRead,
  type MtmSessionCreate,
  type MtmSessionCancel,
  type MtmSessionClose,
} from "@/lib/pharmacy-mtm-temp-contract";
import {
  ReorderPointRead,
  ReorderSuggestionRead,
  type ReorderPointUpsert,
  type ReorderPurchaseOrderGenerate,
} from "@/lib/pharmacy-reorder-temp-contract";

type DispensationOrderRead = components["schemas"]["DispensationOrderRead"];
type DispensationOrderCreate = z.infer<typeof schemas.DispensationOrderCreate>;
type DispensationVoid = z.infer<typeof schemas.DispensationVoid>;
type ControlledSubstanceProductRead = components["schemas"]["ControlledSubstanceProductRead"];
type ControlledSubstanceLogEntryRead = components["schemas"]["ControlledSubstanceLogEntryRead"];
type ProductActiveIngredientRead = components["schemas"]["ProductActiveIngredientRead"];
type ProductActiveIngredientSet = z.infer<typeof schemas.ProductActiveIngredientSet>;
type InteractionCheckRequest = z.infer<typeof schemas.InteractionCheckRequest>;
type InteractionCheckResult = components["schemas"]["InteractionCheckResult"];

export function useDispensationsForPatient(patientContactId: number | null) {
  return useQuery({
    queryKey: ["pharmacy", "dispensations", "patient", patientContactId],
    queryFn: () =>
      apiRequest<DispensationOrderRead[]>(`/pharmacy/patients/${patientContactId}/dispensations`, {
        responseSchema: schemas.DispensationOrderRead.array(),
      }),
    enabled: patientContactId !== null,
  });
}

export function useCreateDispensation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DispensationOrderCreate) =>
      apiRequest<DispensationOrderRead>("/pharmacy/dispensations", {
        method: "POST", body: payload, responseSchema: schemas.DispensationOrderRead,
      }),
    onSuccess: (order) => qc.invalidateQueries({ queryKey: ["pharmacy", "dispensations", "patient", order.patient_contact_id] }),
  });
}

export function useVoidDispensation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, payload }: { orderId: number; payload: DispensationVoid }) =>
      apiRequest<DispensationOrderRead>(`/pharmacy/dispensations/${orderId}/void`, {
        method: "POST", body: payload, responseSchema: schemas.DispensationOrderRead,
      }),
    onSuccess: (order) => qc.invalidateQueries({ queryKey: ["pharmacy", "dispensations", "patient", order.patient_contact_id] }),
  });
}

export function useControlledSubstances() {
  return useQuery({
    queryKey: ["pharmacy", "controlled-substances"],
    queryFn: () =>
      apiRequest<ControlledSubstanceProductRead[]>("/pharmacy/controlled-substances", {
        responseSchema: schemas.ControlledSubstanceProductRead.array(),
      }),
  });
}

export function useMarkControlledSubstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (productId: number) =>
      apiRequest<ControlledSubstanceProductRead>("/pharmacy/controlled-substances", {
        method: "POST", body: { product_id: productId }, responseSchema: schemas.ControlledSubstanceProductRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pharmacy", "controlled-substances"] }),
  });
}

export function useUnmarkControlledSubstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (productId: number) => apiRequest(`/pharmacy/controlled-substances/${productId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pharmacy", "controlled-substances"] }),
  });
}

export function useControlledSubstanceLog() {
  return useQuery({
    queryKey: ["pharmacy", "controlled-substances", "log"],
    queryFn: () =>
      apiRequest<ControlledSubstanceLogEntryRead[]>("/pharmacy/controlled-substances/log", {
        responseSchema: schemas.ControlledSubstanceLogEntryRead.array(),
      }),
  });
}

// Módulo 17 — Interacciones [extendido]. Ver DED-51 a DED-54 (backend).
export function useProductActiveIngredients() {
  return useQuery({
    queryKey: ["pharmacy", "active-ingredients"],
    queryFn: () =>
      apiRequest<ProductActiveIngredientRead[]>("/pharmacy/products/active-ingredients", {
        responseSchema: schemas.ProductActiveIngredientRead.array(),
      }),
  });
}

export function useSetProductActiveIngredient() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProductActiveIngredientSet) =>
      apiRequest<ProductActiveIngredientRead>(`/pharmacy/products/${payload.product_id}/active-ingredient`, {
        method: "PUT", body: payload, responseSchema: schemas.ProductActiveIngredientRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pharmacy", "active-ingredients"] }),
  });
}

export function useCheckInteractions() {
  return useMutation({
    mutationFn: (payload: InteractionCheckRequest) =>
      apiRequest<InteractionCheckResult>("/pharmacy/interactions/check", {
        method: "POST", body: payload, responseSchema: schemas.InteractionCheckResult,
      }),
  });
}

// Módulo 18 — Aseguradoras [extendido]. Ver DED-62 a DED-64 (backend).
type InsuranceProviderRead = components["schemas"]["InsuranceProviderRead"];
type InsuranceProviderCreate = z.infer<typeof schemas.InsuranceProviderCreate>;
type PatientInsurancePolicyRead = components["schemas"]["PatientInsurancePolicyRead"];
type PatientInsurancePolicyCreate = z.infer<typeof schemas.PatientInsurancePolicyCreate>;
type InsuranceClaimRead = components["schemas"]["InsuranceClaimRead"];
type InsuranceClaimCreate = z.infer<typeof schemas.InsuranceClaimCreate>;
type InsuranceClaimReject = z.infer<typeof schemas.InsuranceClaimReject>;
type InsuranceClaimPay = z.infer<typeof schemas.InsuranceClaimPay>;

export function useInsuranceProviders() {
  return useQuery({
    queryKey: ["pharmacy", "insurance-providers"],
    queryFn: () =>
      apiRequest<InsuranceProviderRead[]>("/pharmacy/insurance-providers", {
        responseSchema: schemas.InsuranceProviderRead.array(),
      }),
  });
}

export function useCreateInsuranceProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: InsuranceProviderCreate) =>
      apiRequest<InsuranceProviderRead>("/pharmacy/insurance-providers", {
        method: "POST", body: payload, responseSchema: schemas.InsuranceProviderRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pharmacy", "insurance-providers"] }),
  });
}

export function usePatientInsurancePolicies(patientContactId: number | null) {
  return useQuery({
    queryKey: ["pharmacy", "insurance-policies", patientContactId],
    queryFn: () =>
      apiRequest<PatientInsurancePolicyRead[]>(`/pharmacy/insurance-policies/patient/${patientContactId}`, {
        responseSchema: schemas.PatientInsurancePolicyRead.array(),
      }),
    enabled: patientContactId != null,
  });
}

export function useCreatePatientInsurancePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PatientInsurancePolicyCreate) =>
      apiRequest<PatientInsurancePolicyRead>("/pharmacy/insurance-policies", {
        method: "POST", body: payload, responseSchema: schemas.PatientInsurancePolicyRead,
      }),
    onSuccess: (_data, variables) =>
      qc.invalidateQueries({ queryKey: ["pharmacy", "insurance-policies", variables.patient_contact_id] }),
  });
}

export function useInsuranceClaims() {
  return useQuery({
    queryKey: ["pharmacy", "insurance-claims"],
    queryFn: () =>
      apiRequest<InsuranceClaimRead[]>("/pharmacy/insurance-claims", {
        responseSchema: schemas.InsuranceClaimRead.array(),
      }),
  });
}

export function useCreateInsuranceClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: InsuranceClaimCreate) =>
      apiRequest<InsuranceClaimRead>("/pharmacy/insurance-claims", {
        method: "POST", body: payload, responseSchema: schemas.InsuranceClaimRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pharmacy", "insurance-claims"] }),
  });
}

function useClaimTransition(action: "submit" | "approve") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: number) =>
      apiRequest<InsuranceClaimRead>(`/pharmacy/insurance-claims/${claimId}/${action}`, {
        method: "POST", responseSchema: schemas.InsuranceClaimRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pharmacy", "insurance-claims"] }),
  });
}

export const useSubmitInsuranceClaim = () => useClaimTransition("submit");
export const useApproveInsuranceClaim = () => useClaimTransition("approve");

export function useRejectInsuranceClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, payload }: { claimId: number; payload: InsuranceClaimReject }) =>
      apiRequest<InsuranceClaimRead>(`/pharmacy/insurance-claims/${claimId}/reject`, {
        method: "POST", body: payload, responseSchema: schemas.InsuranceClaimRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pharmacy", "insurance-claims"] }),
  });
}

export function usePayInsuranceClaim() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, payload }: { claimId: number; payload: InsuranceClaimPay }) =>
      apiRequest<InsuranceClaimRead>(`/pharmacy/insurance-claims/${claimId}/pay`, {
        method: "POST", body: payload, responseSchema: schemas.InsuranceClaimRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pharmacy", "insurance-claims"] }),
  });
}

// ---------------------------------------------------------------------------
// Módulo 21 — MTM / Consulta Farmacéutica (contrato temporal, ver
// pharmacy-mtm-temp-contract.ts)
// ---------------------------------------------------------------------------
export function useMtmSessionsForPatient(patientContactId: number | null) {
  return useQuery({
    queryKey: ["pharmacy", "mtm-sessions", "patient", patientContactId],
    queryFn: () =>
      apiRequest<MtmSessionRead[]>(`/pharmacy/patients/${patientContactId}/mtm-sessions`, {
        responseSchema: MtmSessionRead.array(),
      }),
    enabled: patientContactId !== null,
  });
}

export function useMtmSessionBilling(sessionId: number | null) {
  return useQuery({
    queryKey: ["pharmacy", "mtm-sessions", sessionId, "billing"],
    queryFn: () =>
      apiRequest<MtmBillingRecordRead | null>(`/pharmacy/mtm-sessions/${sessionId}/billing`, {
        responseSchema: MtmBillingRecordRead.nullable(),
      }),
    enabled: sessionId !== null,
  });
}

export function useCreateMtmSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: MtmSessionCreate) =>
      apiRequest<MtmSessionRead>("/pharmacy/mtm-sessions", {
        method: "POST", body: payload, responseSchema: MtmSessionRead,
      }),
    onSuccess: (session) => qc.invalidateQueries({ queryKey: ["pharmacy", "mtm-sessions", "patient", session.patient_contact_id] }),
  });
}

export function useCancelMtmSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, payload }: { sessionId: number; payload: MtmSessionCancel }) =>
      apiRequest<MtmSessionRead>(`/pharmacy/mtm-sessions/${sessionId}/cancel`, {
        method: "POST", body: payload, responseSchema: MtmSessionRead,
      }),
    onSuccess: (session) => qc.invalidateQueries({ queryKey: ["pharmacy", "mtm-sessions", "patient", session.patient_contact_id] }),
  });
}

export function useCloseMtmSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, payload }: { sessionId: number; payload: MtmSessionClose }) =>
      apiRequest<MtmBillingRecordRead>(`/pharmacy/mtm-sessions/${sessionId}/close`, {
        method: "POST", body: payload, responseSchema: MtmBillingRecordRead,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pharmacy", "mtm-sessions"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Módulo 20 — Reposición a Droguerías (contrato temporal, ver
// pharmacy-reorder-temp-contract.ts)
// ---------------------------------------------------------------------------
export function useReorderPoints(warehouseId: number | null) {
  return useQuery({
    queryKey: ["pharmacy", "reorder-points", warehouseId],
    queryFn: () =>
      apiRequest<ReorderPointRead[]>("/pharmacy/reorder-points", {
        query: { warehouse_id: warehouseId ?? undefined }, responseSchema: ReorderPointRead.array(),
      }),
    enabled: warehouseId !== null,
  });
}

export function useReorderSuggestions(warehouseId: number | null) {
  return useQuery({
    queryKey: ["pharmacy", "reorder-suggestions", warehouseId],
    queryFn: () =>
      apiRequest<ReorderSuggestionRead[]>("/pharmacy/reorder-suggestions", {
        query: { warehouse_id: warehouseId ?? undefined }, responseSchema: ReorderSuggestionRead.array(),
      }),
    enabled: warehouseId !== null,
  });
}

export function useUpsertReorderPoint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReorderPointUpsert) =>
      apiRequest<ReorderPointRead>("/pharmacy/reorder-points", {
        method: "PUT", body: payload, responseSchema: ReorderPointRead,
      }),
    onSuccess: (point) => {
      qc.invalidateQueries({ queryKey: ["pharmacy", "reorder-points", point.warehouse_id] });
      qc.invalidateQueries({ queryKey: ["pharmacy", "reorder-suggestions", point.warehouse_id] });
    },
  });
}

export function useDeleteReorderPoint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reorderPointId: number) => apiRequest(`/pharmacy/reorder-points/${reorderPointId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pharmacy", "reorder-points"] });
      qc.invalidateQueries({ queryKey: ["pharmacy", "reorder-suggestions"] });
    },
  });
}

export function useGeneratePurchaseOrderFromSuggestions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReorderPurchaseOrderGenerate) =>
      apiRequest("/pharmacy/reorder-suggestions/generate-purchase-order", { method: "POST", body: payload }),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["pharmacy", "reorder-suggestions", variables.warehouse_id] });
    },
  });
}
