import { useState, useEffect } from "react";
import { useEcommerceSettings, useCreateEcommerceSettings, useUpdateEcommerceSettings } from "@/hooks/use-ecommerce";
import { useWarehouses } from "@/hooks/use-inventory";
import { usePriceLists } from "@/hooks/use-sales";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";

const SELECT_CLASS =
  "flex h-9 w-full rounded-md border border-input bg-card px-3 py-1 text-sm";

export function EcommercePage() {
  const { data: settings, isLoading, error } = useEcommerceSettings();
  const createSettings = useCreateEcommerceSettings();
  const updateSettings = useUpdateEcommerceSettings();
  const { data: warehouses } = useWarehouses();
  const { data: priceLists } = usePriceLists();

  const [warehouseId, setWarehouseId] = useState<string>("");
  const [priceListId, setPriceListId] = useState<string>("");
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (settings) {
      setWarehouseId(settings.default_warehouse_id?.toString() ?? "");
      setPriceListId(settings.default_price_list_id?.toString() ?? "");
    }
  }, [settings]);

  const save = async () => {
    setSaveError(null);
    try {
      await updateSettings.mutateAsync({
        default_warehouse_id: warehouseId ? Number(warehouseId) : null,
        default_price_list_id: priceListId ? Number(priceListId) : null,
      });
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "No se pudo guardar la configuración");
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-display text-2xl font-medium text-foreground">Ecommerce</h1>
        <p className="text-sm text-muted-foreground">
          Configuración mínima para que el checkout del storefront público funcione. El catálogo,
          carrito y checkout en sí viven en un frontend separado (el storefront), no en este panel.
        </p>
      </header>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.code === "PERMISSION_DENIED" ? "No tenés permiso para ver esta configuración." : error.message}
        </p>
      )}

      {!isLoading && !error && settings === null && (
        <div className="flex flex-col gap-3 rounded-md border border-border p-4">
          <p className="text-sm text-muted-foreground">
            Ecommerce todavía no tiene configuración inicial para esta compañía.
          </p>
          <Button
            size="sm"
            className="w-fit"
            onClick={() => createSettings.mutate()}
            disabled={createSettings.isPending}
          >
            Crear configuración
          </Button>
        </div>
      )}

      {!isLoading && !error && settings && (
        <div className="flex flex-col gap-4 rounded-md border border-border p-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ecommerce-warehouse">Almacén por defecto</Label>
              <select
                id="ecommerce-warehouse"
                className={SELECT_CLASS}
                value={warehouseId}
                onChange={(e) => setWarehouseId(e.target.value)}
              >
                <option value="">Sin configurar</option>
                {(warehouses ?? []).map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="ecommerce-price-list">Lista de precios por defecto</Label>
              <select
                id="ecommerce-price-list"
                className={SELECT_CLASS}
                value={priceListId}
                onChange={(e) => setPriceListId(e.target.value)}
              >
                <option value="">Usar la lista marcada "por defecto"</option>
                {(priceLists ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {saveError && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {saveError}
            </p>
          )}
          {!warehouseId && (
            <p className="text-sm text-muted-foreground">
              Sin almacén configurado, el checkout del storefront fallará con un error explícito
              hasta que se configure uno.
            </p>
          )}

          <Button size="sm" className="w-fit" onClick={save} disabled={updateSettings.isPending}>
            Guardar
          </Button>
        </div>
      )}
    </div>
  );
}
