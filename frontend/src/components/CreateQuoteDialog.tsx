import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useCreateQuote } from "@/hooks/use-sales";
import { useContacts } from "@/hooks/use-contacts";
import { useProducts } from "@/hooks/use-inventory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus, Trash2 } from "lucide-react";

interface LineDraft {
  product_id: string;
  quantity: string;
  unit_price: string;
}

const emptyLine: LineDraft = { product_id: "", quantity: "", unit_price: "" };

interface HeaderValues {
  customer_id: number;
  valid_until: string;
}

export function CreateQuoteDialog() {
  const [open, setOpen] = useState(false);
  const { data: contacts } = useContacts("");
  const customers = contacts?.filter((c) => c.is_customer) ?? [];
  const { data: products } = useProducts();
  const createQuote = useCreateQuote();

  const [lines, setLines] = useState<LineDraft[]>([{ ...emptyLine }]);
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { control, handleSubmit, register, reset, formState: { errors } } = useForm<HeaderValues>();

  const updateLine = (index: number, field: keyof LineDraft, value: string) => {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));
  };

  const onSubmit = async (header: HeaderValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.QuoteCreate.parse({
        customer_id: header.customer_id,
        valid_until: header.valid_until,
        lines: lines.map((l) => ({ product_id: Number(l.product_id), quantity: l.quantity, unit_price: l.unit_price })),
      });
      await createQuote.mutateAsync(parsed);
      reset();
      setLines([{ ...emptyLine }]);
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos de la cotización");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nueva cotización
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Nueva cotización</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Cliente</Label>
            <Controller
              control={control}
              name="customer_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Cliente"><SelectValue placeholder="Elegir cliente…" /></SelectTrigger>
                  <SelectContent>
                    {customers.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.customer_id && <p className="text-sm text-destructive">Elegí un cliente</p>}
            {customers.length === 0 && (
              <p className="text-xs text-muted-foreground">No hay contactos con el flag "Cliente" activo — creá uno primero en Contactos.</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="valid_until">Válida hasta</Label>
            <Input id="valid_until" type="date" {...register("valid_until", { required: true })} />
            {errors.valid_until && <p className="text-sm text-destructive">Elegí una fecha</p>}
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
                  <Input type="number" step="0.0001" className="w-24" value={line.quantity} onChange={(e) => updateLine(index, "quantity", e.target.value)} />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Precio unit.</Label>
                  <Input type="number" step="0.01" className="w-24" value={line.unit_price} onChange={(e) => updateLine(index, "unit_price", e.target.value)} />
                </div>
                <Button type="button" size="sm" variant="ghost" onClick={() => setLines((prev) => prev.filter((_, i) => i !== index))} disabled={lines.length === 1}>
                  <Trash2 className="size-4" />
                </Button>
              </div>
            ))}
          </div>

          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear cotización"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
