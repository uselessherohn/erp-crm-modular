import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { apiRequest, schemas } from "@/lib/api-client";
import { getRefreshToken, setTokens, clearTokens, isAuthenticated, subscribe } from "@/lib/auth-store";
import type { components } from "@/lib/generated/api-types";

type LoginRequest = components["schemas"]["LoginRequest"];
type UserRead = components["schemas"]["UserRead"];

export function useIsAuthenticated() {
  return useSyncExternalStore(subscribe, isAuthenticated);
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: LoginRequest) => {
      const data = await apiRequest("/auth/login", {
        method: "POST",
        body: payload,
        auth: false,
        responseSchema: schemas.TokenResponse,
      });
      const tokens = data as { access_token: string; refresh_token: string };
      setTokens(tokens.access_token, tokens.refresh_token);
      return tokens;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const raw = getRefreshToken();
      if (raw) {
        await apiRequest("/auth/logout", { method: "POST", query: { raw_refresh_token: raw } });
      }
    },
    onSettled: () => {
      clearTokens();
      queryClient.clear();
    },
  });
}

export function useCurrentUser() {
  const authenticated = useIsAuthenticated();
  return useQuery({
    queryKey: ["me"],
    queryFn: () => apiRequest<UserRead>("/users/me", { responseSchema: schemas.UserRead }),
    enabled: authenticated,
    retry: false,
  });
}
