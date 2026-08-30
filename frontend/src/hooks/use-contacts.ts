import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";

type ContactRead = components["schemas"]["ContactRead"];
type ContactCreate = components["schemas"]["ContactCreate"];

export function useContacts(search: string) {
  return useQuery({
    queryKey: ["contacts", search],
    queryFn: () =>
      apiRequest<ContactRead[]>("/contacts", {
        query: { search: search || undefined },
        responseSchema: schemas.ContactRead.array(),
      }),
  });
}

export function useContact(contactId: number | null) {
  return useQuery({
    queryKey: ["contacts", "detail", contactId],
    queryFn: () => apiRequest<ContactRead>(`/contacts/${contactId}`, { responseSchema: schemas.ContactRead }),
    enabled: contactId !== null,
  });
}

export function useCreateContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ContactCreate) =>
      apiRequest<ContactRead>("/contacts", { method: "POST", body: payload, responseSchema: schemas.ContactRead }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });
}
