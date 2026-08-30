import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";

type StageRead = components["schemas"]["StageRead"];
type OpportunityRead = components["schemas"]["OpportunityRead"];
type ActivityRead = components["schemas"]["ActivityRead"];

type StageCreate = z.infer<typeof schemas.StageCreate>;
type OpportunityCreate = z.infer<typeof schemas.OpportunityCreate>;
type OpportunityMoveStage = z.infer<typeof schemas.OpportunityMoveStage>;
type OpportunityCloseLost = z.infer<typeof schemas.OpportunityCloseLost>;
type ActivityCreate = z.infer<typeof schemas.ActivityCreate>;

// ---------------------------------------------------------------------------
// Stages
// ---------------------------------------------------------------------------

export function useStages() {
  return useQuery({
    queryKey: ["pipeline", "stages"],
    queryFn: () => apiRequest<StageRead[]>("/pipeline/stages", { responseSchema: schemas.StageRead.array() }),
  });
}

export function useCreateStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: StageCreate) =>
      apiRequest<StageRead>("/pipeline/stages", { method: "POST", body: payload, responseSchema: schemas.StageRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline", "stages"] }),
  });
}

// ---------------------------------------------------------------------------
// Opportunities
// ---------------------------------------------------------------------------

export function useOpportunities() {
  return useQuery({
    queryKey: ["pipeline", "opportunities"],
    queryFn: () =>
      apiRequest<OpportunityRead[]>("/pipeline/opportunities", { responseSchema: schemas.OpportunityRead.array() }),
  });
}

export function useOpportunity(id: number | null) {
  return useQuery({
    queryKey: ["pipeline", "opportunities", id],
    queryFn: () =>
      apiRequest<OpportunityRead>(`/pipeline/opportunities/${id}`, { responseSchema: schemas.OpportunityRead }),
    enabled: id !== null,
  });
}

export function useCreateOpportunity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: OpportunityCreate) =>
      apiRequest<OpportunityRead>("/pipeline/opportunities", {
        method: "POST",
        body: payload,
        responseSchema: schemas.OpportunityRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline", "opportunities"] }),
  });
}

export function useMoveOpportunityStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ opportunityId, payload }: { opportunityId: number; payload: OpportunityMoveStage }) =>
      apiRequest<OpportunityRead>(`/pipeline/opportunities/${opportunityId}/move-stage`, {
        method: "POST",
        body: payload,
        responseSchema: schemas.OpportunityRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline", "opportunities"] }),
  });
}

export function useCloseOpportunityWon() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (opportunityId: number) =>
      apiRequest<OpportunityRead>(`/pipeline/opportunities/${opportunityId}/close-won`, {
        method: "POST",
        responseSchema: schemas.OpportunityRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline", "opportunities"] }),
  });
}

export function useCloseOpportunityLost() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ opportunityId, payload }: { opportunityId: number; payload: OpportunityCloseLost }) =>
      apiRequest<OpportunityRead>(`/pipeline/opportunities/${opportunityId}/close-lost`, {
        method: "POST",
        body: payload,
        responseSchema: schemas.OpportunityRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline", "opportunities"] }),
  });
}

export function useReopenOpportunity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (opportunityId: number) =>
      apiRequest<OpportunityRead>(`/pipeline/opportunities/${opportunityId}/reopen`, {
        method: "POST",
        responseSchema: schemas.OpportunityRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline", "opportunities"] }),
  });
}

// ---------------------------------------------------------------------------
// Activities
// ---------------------------------------------------------------------------

export function useActivities() {
  return useQuery({
    queryKey: ["pipeline", "activities"],
    queryFn: () =>
      apiRequest<ActivityRead[]>("/pipeline/activities", { responseSchema: schemas.ActivityRead.array() }),
  });
}

export function useCreateActivity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ActivityCreate) =>
      apiRequest<ActivityRead>("/pipeline/activities", {
        method: "POST",
        body: payload,
        responseSchema: schemas.ActivityRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline", "activities"] }),
  });
}

export function useCompleteActivity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (activityId: number) =>
      apiRequest<ActivityRead>(`/pipeline/activities/${activityId}/complete`, {
        method: "POST",
        responseSchema: schemas.ActivityRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipeline", "activities"] }),
  });
}
