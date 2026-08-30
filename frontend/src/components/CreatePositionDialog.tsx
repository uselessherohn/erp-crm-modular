import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useCreatePosition, useDepartments } from "@/hooks/use-hr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";

interface FormValues {
  title: string;
  department_id: number;
}

export function CreatePositionDialog() {
  const [open, setOpen] = useState(false);
  const { data: departments } = useDepartments();
  const createPosition = useCreatePosition();
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { control, handleSubmit, register, reset, formState: { errors } } = useForm<FormValues>();

  const onSubmit = async (values: FormValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.PositionCreate.parse({
        title: values.title,
        department_id: Number(values.department_id),
      });
      await createPosition.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos del puesto");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nuevo puesto
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Nuevo puesto</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="title">Título</Label>
            <Input id="title" {...register("title", { required: true })} />
            {errors.title && <p className="text-sm text-destructive">Ingresá un título</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Departamento</Label>
            <Controller
              control={control}
              name="department_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Departamento"><SelectValue placeholder="Elegir departamento…" /></SelectTrigger>
                  <SelectContent>
                    {departments?.map((d) => <SelectItem key={d.id} value={String(d.id)}>{d.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.department_id && <p className="text-sm text-destructive">Elegí un departamento</p>}
            {(departments?.length ?? 0) === 0 && (
              <p className="text-xs text-muted-foreground">No hay departamentos todavía — creá uno primero.</p>
            )}
          </div>
          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear puesto"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
