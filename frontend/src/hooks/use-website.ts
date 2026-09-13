import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api-client";
import {
  WebsitePageRead,
  WebsiteFormSubmissionRead,
  type WebsitePageCreate,
  type WebsitePageUpdate,
} from "@/lib/website-temp-contract";

export function useWebsitePages(status?: "draft" | "published") {
  return useQuery({
    queryKey: ["website", "pages", status ?? "all"],
    queryFn: () =>
      apiRequest<WebsitePageRead[]>("/website/pages", {
        query: { status },
        responseSchema: WebsitePageRead.array(),
      }),
  });
}

export function useCreateWebsitePage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: WebsitePageCreate) =>
      apiRequest<WebsitePageRead>("/website/pages", {
        method: "POST",
        body: payload,
        responseSchema: WebsitePageRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["website", "pages"] }),
  });
}

export function useUpdateWebsitePage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ pageId, payload }: { pageId: number; payload: WebsitePageUpdate }) =>
      apiRequest<WebsitePageRead>(`/website/pages/${pageId}`, {
        method: "PATCH",
        body: payload,
        responseSchema: WebsitePageRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["website", "pages"] }),
  });
}

export function usePublishWebsitePage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pageId: number) =>
      apiRequest<WebsitePageRead>(`/website/pages/${pageId}/publish`, {
        method: "POST",
        responseSchema: WebsitePageRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["website", "pages"] }),
  });
}

export function useUnpublishWebsitePage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pageId: number) =>
      apiRequest<WebsitePageRead>(`/website/pages/${pageId}/unpublish`, {
        method: "POST",
        responseSchema: WebsitePageRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["website", "pages"] }),
  });
}

export function useWebsiteFormSubmissions() {
  return useQuery({
    queryKey: ["website", "form-submissions"],
    queryFn: () =>
      apiRequest<WebsiteFormSubmissionRead[]>("/website/form-submissions", {
        responseSchema: WebsiteFormSubmissionRead.array(),
      }),
  });
}
