import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api-client";
import {
  AuditLogRead,
  AuditRetentionPolicyRead,
  AuditPurgeEligibleCount,
  type AuditRetentionPolicyUpdate,
} from "@/lib/audit-temp-contract";

export interface AuditLogFilters {
  entity_type?: string;
  event?: string;
  user_id?: number;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export function useAuditLogs(filters: AuditLogFilters) {
  return useQuery({
    queryKey: ["audit", "logs", filters],
    queryFn: () =>
      apiRequest<AuditLogRead[]>("/audit/logs", {
        query: { ...filters },
        responseSchema: AuditLogRead.array(),
      }),
  });
}

export function useRetentionPolicy() {
  return useQuery({
    queryKey: ["audit", "retention-policy"],
    queryFn: () => apiRequest<AuditRetentionPolicyRead>("/audit/retention-policy", { responseSchema: AuditRetentionPolicyRead }),
  });
}

export function useUpdateRetentionPolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AuditRetentionPolicyUpdate) =>
      apiRequest<AuditRetentionPolicyRead>("/audit/retention-policy", {
        method: "PUT", body: payload, responseSchema: AuditRetentionPolicyRead,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["audit", "retention-policy"] });
      qc.invalidateQueries({ queryKey: ["audit", "purge-eligible"] });
    },
  });
}

export function usePurgeEligibleCount() {
  return useQuery({
    queryKey: ["audit", "purge-eligible"],
    queryFn: () =>
      apiRequest<AuditPurgeEligibleCount>("/audit/retention-policy/purge-eligible", { responseSchema: AuditPurgeEligibleCount }),
  });
}
