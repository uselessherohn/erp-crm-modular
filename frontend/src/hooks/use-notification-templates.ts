import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";

type NotificationTemplateRead = components["schemas"]["NotificationTemplateRead"];
type NotificationRead = components["schemas"]["NotificationRead"];
type NotificationTemplateCreate = z.infer<typeof schemas.NotificationTemplateCreate>;
type NotificationTemplateUpdate = z.infer<typeof schemas.NotificationTemplateUpdate>;
type NotificationSend = z.infer<typeof schemas.NotificationSend>;

export function useNotificationTemplates() {
  return useQuery({
    queryKey: ["notifications", "templates"],
    queryFn: () => apiRequest<NotificationTemplateRead[]>("/notifications/templates", { responseSchema: schemas.NotificationTemplateRead.array() }),
  });
}

export function useCreateNotificationTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: NotificationTemplateCreate) =>
      apiRequest<NotificationTemplateRead>("/notifications/templates", { method: "POST", body: payload, responseSchema: schemas.NotificationTemplateRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications", "templates"] }),
  });
}

export function useUpdateNotificationTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ code, payload }: { code: string; payload: NotificationTemplateUpdate }) =>
      apiRequest<NotificationTemplateRead>(`/notifications/templates/${encodeURIComponent(code)}`, {
        method: "PATCH",
        body: payload,
        responseSchema: schemas.NotificationTemplateRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications", "templates"] }),
  });
}

export function useSendNotification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: NotificationSend) =>
      apiRequest<NotificationRead>("/notifications/send", { method: "POST", body: payload, responseSchema: schemas.NotificationRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}
