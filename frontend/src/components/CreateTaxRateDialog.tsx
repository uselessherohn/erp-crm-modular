import { useState } from "react";
import { useForm } from "react-hook-form";
import { useCreateTaxRate } from "@/hooks/use-accounting";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";

interface FormValues {
  name: string;
  rate: string;
  is_default: boolean;
}

export function CreateTaxRateDialog() {
  const [open, setOpen] = useState(false);
  const createTaxRate = useCreateTaxRate();
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { register, handleSubmit, reset, formState: { errors } } = useForm<FormValues>();

  const onSubmit = async (values: FormValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.TaxRateCreate.parse({
        name: values.name,
        rate: values.rate,
        is_default: values.is_default ?? false,
      });
      await createTaxRate.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos de la tasa");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nueva tasa
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Nueva tasa de impuesto</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" placeholder="ISV 15%" {...register("name", { required: true })} />
            {errors.name && <p className="text-sm text-destructive">Ingresá un nombre</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rate">Porcentaje</Label>
            <Input id="rate" type="number" step="0.01" min="0" max="100" {...register("rate", { required: true })} />
            {errors.rate && <p className="text-sm text-destructive">Ingresá un porcentaje</p>}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...register("is_default")} />
            Usar como tasa por defecto
          </label>
          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear tasa"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
