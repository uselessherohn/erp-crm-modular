import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";

type NotificationRead = components["schemas"]["NotificationRead"];

export function useNotifications(options?: { unreadOnly?: boolean; pollMs?: number }) {
  return useQuery({
    queryKey: ["notifications", options?.unreadOnly ?? false],
    queryFn: () =>
      apiRequest<NotificationRead[]>("/notifications", {
        query: { unread_only: options?.unreadOnly ? "true" : undefined },
        responseSchema: schemas.NotificationRead.array(),
      }),
    refetchInterval: options?.pollMs,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: number) =>
      apiRequest<NotificationRead>(`/notifications/${notificationId}/read`, { method: "POST", responseSchema: schemas.NotificationRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiRequest<{ marked_read: number }>("/notifications/read-all", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}
