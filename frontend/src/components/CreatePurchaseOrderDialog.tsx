import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { schemas } from "@/lib/generated/schemas";
import { useCreatePurchaseOrder } from "@/hooks/use-purchasing";
import { useContacts } from "@/hooks/use-contacts";
import { useProducts, useWarehouses } from "@/hooks/use-inventory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { ApiError } from "@/lib/api-client";
import { Plus, Trash2 } from "lucide-react";

// El header (vendor_id/warehouse_id/etc) sí pasa por RHF+zodResolver, como
// el resto del proyecto. Las líneas (array anidado con campos Decimal) se
// manejan con estado de React simple: useFieldArray + el tipo z.input de
// un array con campos number|string union anidados produce "Type 'lines'
// does not satisfy the constraint 'never'" de forma persistente (probado
// con z.input, z.infer y genéricos explícitos) — fricción real de tipos
// entre react-hook-form y el union Decimal generado, no un error de
// lógica. La validación real sigue siendo 100% Zod, solo al momento del
// submit en vez de campo por campo — sin pérdida de garantías.
type HeaderValues = {
  vendor_id: number;
  warehouse_id: number;
};

interface LineDraft {
  product_id: string;
  quantity_ordered: string;
  unit_cost: string;
}

const emptyLine: LineDraft = { product_id: "", quantity_ordered: "", unit_cost: "" };

export function CreatePurchaseOrderDialog() {
  const [open, setOpen] = useState(false);
  const { data: contacts } = useContacts("");
  const vendors = contacts?.filter((c) => c.is_vendor) ?? [];
  const { data: products } = useProducts();
  const { data: warehouses } = useWarehouses();
  const createPO = useCreatePurchaseOrder();

  const [lines, setLines] = useState<LineDraft[]>([{ ...emptyLine }]);
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<HeaderValues>();

  const updateLine = (index: number, field: keyof LineDraft, value: string) => {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));
  };

  const onSubmit = async (header: HeaderValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const rawPayload = {
        vendor_id: header.vendor_id,
        warehouse_id: header.warehouse_id,
        lines: lines.map((l) => ({
          product_id: Number(l.product_id),
          quantity_ordered: l.quantity_ordered,
          unit_cost: l.unit_cost,
        })),
      };
      const parsed = schemas.PurchaseOrderCreate.parse(rawPayload);
      await createPO.mutateAsync(parsed);
      reset();
      setLines([{ ...emptyLine }]);
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos de la orden de compra");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nueva orden de compra
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Nueva orden de compra</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Proveedor</Label>
            <Controller
              control={control}
              name="vendor_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Proveedor"><SelectValue placeholder="Elegir proveedor…" /></SelectTrigger>
                  <SelectContent>
                    {vendors.map((v) => <SelectItem key={v.id} value={String(v.id)}>{v.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.vendor_id && <p className="text-sm text-destructive">Elegí un proveedor</p>}
            {vendors.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No hay contactos con el flag "Proveedor" activo — creá uno primero en Contactos.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Almacén de recepción</Label>
            <Controller
              control={control}
              name="warehouse_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Almacén"><SelectValue placeholder="Elegir almacén…" /></SelectTrigger>
                  <SelectContent>
                    {warehouses?.map((w) => <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.warehouse_id && <p className="text-sm text-destructive">Elegí un almacén</p>}
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Líneas</Label>
              <Button type="button" size="sm" variant="outline" onClick={() => setLines((prev) => [...prev, { ...emptyLine }])}>
                + Línea
              </Button>
            </div>
            {lines.map((line, index) => (
              <div key={index} className="grid grid-cols-[1fr_auto_auto_auto] items-end gap-2 rounded-md border border-border p-2">
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Producto</Label>
                  <Select value={line.product_id} onValueChange={(v) => updateLine(index, "product_id", v)}>
                    <SelectTrigger aria-label={`Producto línea ${index + 1}`}><SelectValue placeholder="Producto…" /></SelectTrigger>
                    <SelectContent>
                      {products?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.sku}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Cantidad</Label>
                  <Input type="number" step="0.0001" className="w-24" value={line.quantity_ordered} onChange={(e) => updateLine(index, "quantity_ordered", e.target.value)} />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Costo unit.</Label>
                  <Input type="number" step="0.01" className="w-24" value={line.unit_cost} onChange={(e) => updateLine(index, "unit_cost", e.target.value)} />
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setLines((prev) => prev.filter((_, i) => i !== index))}
                  disabled={lines.length === 1}
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            ))}
          </div>

          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear orden de compra"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
