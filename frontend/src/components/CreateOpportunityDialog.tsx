import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useCreateOpportunity, useStages } from "@/hooks/use-pipeline";
import { useContacts } from "@/hooks/use-contacts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";

interface FormValues {
  contact_id: number;
  stage_id: number;
  name: string;
  amount: string;
  expected_close_date: string;
}

export function CreateOpportunityDialog() {
  const [open, setOpen] = useState(false);
  const { data: contacts } = useContacts("");
  const { data: stages } = useStages();
  const createOpportunity = useCreateOpportunity();
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { control, handleSubmit, register, reset, formState: { errors } } = useForm<FormValues>();

  const openStages = (stages ?? []).filter((s) => !s.is_won && !s.is_lost);

  const onSubmit = async (values: FormValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.OpportunityCreate.parse({
        contact_id: values.contact_id,
        stage_id: values.stage_id,
        name: values.name,
        amount: values.amount || null,
        expected_close_date: values.expected_close_date || null,
      });
      await createOpportunity.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos de la oportunidad");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nueva oportunidad
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Nueva oportunidad</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" {...register("name", { required: true })} />
            {errors.name && <p className="text-sm text-destructive">Ingresá un nombre</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Contacto</Label>
            <Controller
              control={control}
              name="contact_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Contacto"><SelectValue placeholder="Elegir contacto…" /></SelectTrigger>
                  <SelectContent>
                    {contacts?.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.contact_id && <p className="text-sm text-destructive">Elegí un contacto</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Etapa inicial</Label>
            <Controller
              control={control}
              name="stage_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Etapa inicial"><SelectValue placeholder="Elegir etapa…" /></SelectTrigger>
                  <SelectContent>
                    {openStages.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.stage_id && <p className="text-sm text-destructive">Elegí una etapa</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="amount">Monto estimado</Label>
            <Input id="amount" type="number" step="0.01" {...register("amount")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="expected_close_date">Cierre estimado</Label>
            <Input id="expected_close_date" type="date" {...register("expected_close_date")} />
          </div>
          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear oportunidad"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
