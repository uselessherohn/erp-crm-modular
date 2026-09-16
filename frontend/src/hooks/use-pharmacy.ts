import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";

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
