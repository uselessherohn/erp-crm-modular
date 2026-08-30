import { useState } from "react";
import { useForm } from "react-hook-form";
import { useCreatePriceList } from "@/hooks/use-sales";
import { useProducts } from "@/hooks/use-inventory";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus, Trash2 } from "lucide-react";

interface ItemDraft {
  product_id: string;
  unit_price: string;
  min_quantity: string;
}

const emptyItem: ItemDraft = { product_id: "", unit_price: "", min_quantity: "1" };

export function CreatePriceListDialog() {
  const [open, setOpen] = useState(false);
  const { data: products } = useProducts();
  const createPriceList = useCreatePriceList();
  const [items, setItems] = useState<ItemDraft[]>([{ ...emptyItem }]);
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { register, handleSubmit, reset, formState: { errors } } = useForm<{ name: string }>();

  const updateItem = (index: number, field: keyof ItemDraft, value: string) => {
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, [field]: value } : it)));
  };

  const onSubmit = async ({ name }: { name: string }) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.PriceListCreate.parse({
        name,
        items: items
          .filter((it) => it.product_id)
          .map((it) => ({ product_id: Number(it.product_id), unit_price: it.unit_price, min_quantity: it.min_quantity || "1" })),
      });
      await createPriceList.mutateAsync(parsed);
      reset();
      setItems([{ ...emptyItem }]);
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "No se pudo crear la lista de precios");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nueva lista de precios
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Nueva lista de precios</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="pl-name">Nombre</Label>
            <Input id="pl-name" {...register("name", { required: true })} />
            {errors.name && <p className="text-sm text-destructive">Ingresá un nombre</p>}
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Precios por producto</Label>
              <Button type="button" size="sm" variant="outline" onClick={() => setItems((prev) => [...prev, { ...emptyItem }])}>
                + Precio
              </Button>
            </div>
            {items.map((item, index) => (
              <div key={index} className="grid grid-cols-[1fr_auto_auto_auto] items-end gap-2 rounded-md border border-border p-2">
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Producto</Label>
                  <Select value={item.product_id} onValueChange={(v) => updateItem(index, "product_id", v)}>
                    <SelectTrigger aria-label={`Producto precio ${index + 1}`}><SelectValue placeholder="Producto…" /></SelectTrigger>
                    <SelectContent>
                      {products?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.sku}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Precio</Label>
                  <Input type="number" step="0.01" className="w-24" value={item.unit_price} onChange={(e) => updateItem(index, "unit_price", e.target.value)} />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Desde cant.</Label>
                  <Input type="number" step="1" className="w-20" value={item.min_quantity} onChange={(e) => updateItem(index, "min_quantity", e.target.value)} />
                </div>
                <Button type="button" size="sm" variant="ghost" onClick={() => setItems((prev) => prev.filter((_, i) => i !== index))} disabled={items.length === 1}>
                  <Trash2 className="size-4" />
                </Button>
              </div>
            ))}
          </div>

          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear lista de precios"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
