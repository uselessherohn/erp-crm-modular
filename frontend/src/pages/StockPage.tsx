import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { schemas } from "@/lib/generated/schemas";
import { useProducts, useWarehouses, useStockLevels, useCreateStockMovement, useCreateTransfer } from "@/hooks/use-inventory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";
import { ArrowRightLeft, PackagePlus } from "lucide-react";
import type { z } from "zod";

type StockMovementValues = z.input<typeof schemas.StockMovementCreate>;
type TransferValues = z.input<typeof schemas.TransferCreate>;

const MOVEMENT_LABELS: Record<string, string> = { entrada: "Entrada", salida: "Salida", ajuste: "Ajuste (baja)" };

function RecordMovementDialog() {
  const [open, setOpen] = useState(false);
  const { data: products } = useProducts();
  const { data: warehouses } = useWarehouses();
  const createMovement = useCreateStockMovement();

  const { register, handleSubmit, control, reset, watch, formState: { errors, isSubmitting }, setError } = useForm<StockMovementValues>({
    resolver: zodResolver(schemas.StockMovementCreate),
    // Los <Select> de Radix son "controlados" (value=field.value) —
    // sin defaultValues, RHF entrega `undefined` en el primer render y
    // luego un valor real al elegir, lo que React reporta como el warning
    // "changing from uncontrolled to controlled". Encontrado al correr el
    // test de integración real (no aparece con solo tsc/build).
    defaultValues: { product_id: undefined, warehouse_id: undefined, movement_type: undefined, quantity: undefined },
  });

  const selectedProductId = watch("product_id");
  const selectedProduct = products?.find((p) => p.id === Number(selectedProductId));

  const onSubmit = async (values: StockMovementValues) => {
    try {
      const parsed = schemas.StockMovementCreate.parse(values);
      await createMovement.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setError("root", { message: err instanceof ApiError ? err.message : "No se pudo registrar el movimiento" });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <PackagePlus className="size-4" />
          Registrar movimiento
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Registrar movimiento de stock</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Producto</Label>
            <Controller
              control={control}
              name="product_id"
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Producto"><SelectValue placeholder="Elegir producto…" /></SelectTrigger>
                  <SelectContent>
                    {products?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.sku} — {p.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Almacén</Label>
            <Controller
              control={control}
              name="warehouse_id"
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Almacén"><SelectValue placeholder="Elegir almacén…" /></SelectTrigger>
                  <SelectContent>
                    {warehouses?.map((w) => <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Tipo</Label>
              <Controller
                control={control}
                name="movement_type"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger aria-label="Tipo de movimiento"><SelectValue placeholder="Tipo…" /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(MOVEMENT_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="quantity">Cantidad</Label>
              <Input id="quantity" type="number" step="0.0001" {...register("quantity")} />
              {errors.quantity && <p className="text-sm text-destructive">{errors.quantity.message}</p>}
            </div>
          </div>

          {selectedProduct?.tracks_lots && (
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="lot_number">Lote</Label>
                <Input id="lot_number" {...register("lot_number")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="expiry_date">Vencimiento</Label>
                <Input id="expiry_date" type="date" {...register("expiry_date")} />
              </div>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reference">Referencia</Label>
            <Input id="reference" {...register("reference")} />
          </div>

          {errors.root && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{errors.root.message}</p>}
          <Button type="submit" disabled={isSubmitting}>{isSubmitting ? "Registrando…" : "Registrar"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TransferDialog() {
  const [open, setOpen] = useState(false);
  const { data: products } = useProducts();
  const { data: warehouses } = useWarehouses();
  const createTransfer = useCreateTransfer();

  const { register, handleSubmit, control, reset, formState: { errors, isSubmitting }, setError } = useForm<TransferValues>({
    resolver: zodResolver(schemas.TransferCreate),
  });

  const onSubmit = async (values: TransferValues) => {
    try {
      const parsed = schemas.TransferCreate.parse(values);
      await createTransfer.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setError("root", { message: err instanceof ApiError ? err.message : "No se pudo transferir" });
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="gap-2">
          <ArrowRightLeft className="size-4" />
          Transferir
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Transferir stock entre almacenes</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Producto</Label>
            <Controller
              control={control}
              name="product_id"
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Producto"><SelectValue placeholder="Elegir producto…" /></SelectTrigger>
                  <SelectContent>
                    {products?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.sku} — {p.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Origen</Label>
              <Controller
                control={control}
                name="source_warehouse_id"
                render={({ field }) => (
                  <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                    <SelectTrigger aria-label="Almacén de origen"><SelectValue placeholder="Origen…" /></SelectTrigger>
                    <SelectContent>
                      {warehouses?.map((w) => <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Destino</Label>
              <Controller
                control={control}
                name="destination_warehouse_id"
                render={({ field }) => (
                  <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                    <SelectTrigger aria-label="Almacén de destino"><SelectValue placeholder="Destino…" /></SelectTrigger>
                    <SelectContent>
                      {warehouses?.map((w) => <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="t-quantity">Cantidad</Label>
            <Input id="t-quantity" type="number" step="0.0001" {...register("quantity")} />
            {errors.quantity && <p className="text-sm text-destructive">{errors.quantity.message}</p>}
          </div>

          {errors.root && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{errors.root.message}</p>}
          <Button type="submit" disabled={isSubmitting}>{isSubmitting ? "Transfiriendo…" : "Transferir"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function StockPage() {
  const { data: levels, isLoading, error } = useStockLevels();
  const { data: products } = useProducts();
  const { data: warehouses } = useWarehouses();

  const productName = (id: number) => products?.find((p) => p.id === id)?.name ?? `#${id}`;
  const warehouseName = (id: number) => warehouses?.find((w) => w.id === id)?.name ?? `#${id}`;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Stock</h1>
          <p className="text-sm text-muted-foreground">Saldos actuales por producto y almacén.</p>
        </div>
        <div className="flex gap-2">
          <TransferDialog />
          <RecordMovementDialog />
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}
      {!isLoading && !error && (levels?.length ?? 0) === 0 && <p className="text-sm text-muted-foreground">Sin movimientos todavía.</p>}

      {!isLoading && !error && (levels?.length ?? 0) > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Producto</TableHead>
              <TableHead>Almacén</TableHead>
              <TableHead>Cantidad</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {levels?.map((lvl) => (
              <TableRow key={`${lvl.product_id}-${lvl.warehouse_id}-${lvl.lot_id ?? "sin-lote"}`}>
                <TableCell>{productName(lvl.product_id)}</TableCell>
                <TableCell>{warehouseName(lvl.warehouse_id)}</TableCell>
                <TableCell className={Number(lvl.quantity) === 0 ? "text-muted-foreground" : ""}>{lvl.quantity}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
