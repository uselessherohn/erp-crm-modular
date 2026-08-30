import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { schemas } from "@/lib/generated/schemas";
import { useWarehouses, useCreateWarehouse } from "@/hooks/use-inventory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ApiError } from "@/lib/api-client";
import { Warehouse as WarehouseIcon, Plus } from "lucide-react";
import type { z } from "zod";

type WarehouseCreateValues = z.infer<typeof schemas.WarehouseCreate>;

function CreateWarehouseDialog() {
  const [open, setOpen] = useState(false);
  const createWarehouse = useCreateWarehouse();
  const { register, handleSubmit, reset, formState: { errors, isSubmitting }, setError } = useForm<WarehouseCreateValues>({
    resolver: zodResolver(schemas.WarehouseCreate),
  });

  const onSubmit = async (values: WarehouseCreateValues) => {
    try {
      await createWarehouse.mutateAsync(values);
      reset();
      setOpen(false);
    } catch (err) {
      setError("root", { message: err instanceof ApiError ? err.message : "No se pudo crear el almacén" });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nuevo almacén
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo almacén</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="wh-name">Nombre</Label>
            <Input id="wh-name" {...register("name")} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="wh-address">Dirección</Label>
            <Input id="wh-address" {...register("address")} />
          </div>
          {errors.root && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{errors.root.message}</p>}
          <Button type="submit" disabled={isSubmitting}>{isSubmitting ? "Creando…" : "Crear almacén"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function WarehousesPage() {
  const { data, isLoading, error } = useWarehouses();

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Almacenes</h1>
          <p className="text-sm text-muted-foreground">Bodegas y sucursales donde se guarda inventario.</p>
        </div>
        <CreateWarehouseDialog />
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}
      {!isLoading && !error && (data?.length ?? 0) === 0 && <p className="text-sm text-muted-foreground">Todavía no hay almacenes.</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((w) => (
          <Card key={w.id}>
            <CardHeader className="flex-row items-center gap-2 space-y-0">
              <WarehouseIcon className="size-4 text-muted-foreground" />
              <CardTitle className="text-base">{w.name}</CardTitle>
            </CardHeader>
            {w.address && <CardContent className="text-sm text-muted-foreground">{w.address}</CardContent>}
          </Card>
        ))}
      </div>
    </div>
  );
}
