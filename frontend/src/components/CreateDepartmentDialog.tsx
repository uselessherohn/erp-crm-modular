import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useCreateDepartment, useDepartments } from "@/hooks/use-hr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";

interface FormValues {
  name: string;
  parent_department_id: string;
}

export function CreateDepartmentDialog() {
  const [open, setOpen] = useState(false);
  const { data: departments } = useDepartments();
  const createDepartment = useCreateDepartment();
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { control, handleSubmit, register, reset, formState: { errors } } = useForm<FormValues>();

  const onSubmit = async (values: FormValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.DepartmentCreate.parse({
        name: values.name,
        parent_department_id: values.parent_department_id ? Number(values.parent_department_id) : null,
      });
      await createDepartment.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos del departamento");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nuevo departamento
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Nuevo departamento</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" {...register("name", { required: true })} />
            {errors.name && <p className="text-sm text-destructive">Ingresá un nombre</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Departamento padre (opcional)</Label>
            <Controller
              control={control}
              name="parent_department_id"
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger aria-label="Departamento padre"><SelectValue placeholder="Ninguno" /></SelectTrigger>
                  <SelectContent>
                    {departments?.map((d) => <SelectItem key={d.id} value={String(d.id)}>{d.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear departamento"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
