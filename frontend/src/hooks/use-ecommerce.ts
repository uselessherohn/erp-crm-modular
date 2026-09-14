import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, ApiError } from "@/lib/api-client";
import {
  EcommerceSettingsRead,
  EcommerceSettingsCreated,
  type EcommerceSettingsUpdate,
} from "@/lib/ecommerce-temp-contract";

export function useEcommerceSettings() {
  return useQuery({
    queryKey: ["ecommerce", "settings"],
    queryFn: async () => {
      try {
        return await apiRequest<EcommerceSettingsRead>("/ecommerce/settings", {
          responseSchema: EcommerceSettingsRead,
        });
      } catch (err) {
        // Sin configuración todavía (compañía nueva, bootstrap no
        // aplicado) — se trata como "no configurado", no como un error
        // de carga, para que la página muestre el botón de creación en
        // vez de un mensaje de error.
        if (err instanceof ApiError && err.status === 422) return null;
        throw err;
      }
    },
  });
}

export function useCreateEcommerceSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<EcommerceSettingsCreated>("/ecommerce/settings", {
        method: "POST",
        responseSchema: EcommerceSettingsCreated,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ecommerce", "settings"] }),
  });
}

export function useUpdateEcommerceSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EcommerceSettingsUpdate) =>
      apiRequest<EcommerceSettingsRead>("/ecommerce/settings", {
        method: "PATCH",
        body: payload,
        responseSchema: EcommerceSettingsRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ecommerce", "settings"] }),
  });
}
