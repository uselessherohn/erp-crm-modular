import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";

type UserRead = components["schemas"]["UserRead"];
type RoleRead = components["schemas"]["RoleRead"];
type UserCreate = components["schemas"]["UserCreate"];
type RoleCreate = components["schemas"]["RoleCreate"];

export function useUsers() {
  return useQuery({
    queryKey: ["users"],
    queryFn: () => apiRequest<UserRead[]>("/users", { responseSchema: schemas.UserRead.array() }),
  });
}

export function useUser(userId: number | null) {
  return useQuery({
    queryKey: ["users", userId],
    queryFn: () => apiRequest<UserRead>(`/users/${userId}`, { responseSchema: schemas.UserRead }),
    enabled: userId !== null,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserCreate) =>
      apiRequest<UserRead>("/users", { method: "POST", body: payload, responseSchema: schemas.UserRead }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useRoles() {
  return useQuery({
    queryKey: ["roles"],
    queryFn: () => apiRequest<RoleRead[]>("/roles", { responseSchema: schemas.RoleRead.array() }),
  });
}

export function useCreateRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoleCreate) =>
      apiRequest<RoleRead>("/roles", { method: "POST", body: payload, responseSchema: schemas.RoleRead }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["roles"] });
    },
  });
}
