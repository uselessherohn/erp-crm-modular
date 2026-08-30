import { useState } from "react";
import { useForm } from "react-hook-form";
import { useCreateStage } from "@/hooks/use-pipeline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";

interface FormValues {
  name: string;
  sort_order: string;
  is_won: boolean;
  is_lost: boolean;
}

export function CreateStageDialog() {
  const [open, setOpen] = useState(false);
  const createStage = useCreateStage();
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { register, handleSubmit, reset, watch, formState: { errors } } = useForm<FormValues>({
    defaultValues: { sort_order: "0" },
  });
  const isWon = watch("is_won");
  const isLost = watch("is_lost");

  const onSubmit = async (values: FormValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.StageCreate.parse({
        name: values.name,
        sort_order: Number(values.sort_order),
        is_won: values.is_won ?? false,
        is_lost: values.is_lost ?? false,
      });
      await createStage.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos de la etapa");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="gap-2">
          <Plus className="size-4" />
          Nueva etapa
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Nueva etapa</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" placeholder="Negociación" {...register("name", { required: true })} />
            {errors.name && <p className="text-sm text-destructive">Ingresá un nombre</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="sort_order">Orden</Label>
            <Input id="sort_order" type="number" {...register("sort_order", { required: true })} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" disabled={isLost} {...register("is_won")} />
            Es una etapa "ganada" (terminal)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" disabled={isWon} {...register("is_lost")} />
            Es una etapa "perdida" (terminal)
          </label>
          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear etapa"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
