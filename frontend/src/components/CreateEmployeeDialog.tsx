import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useCreateEmployee, usePositions, useEmployees } from "@/hooks/use-hr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";

interface FormValues {
  first_name: string;
  last_name: string;
  position_id: string;
  manager_employee_id: string;
  hire_date: string;
  salary: string;
}

export function CreateEmployeeDialog() {
  const [open, setOpen] = useState(false);
  const { data: positions } = usePositions();
  const { data: employees } = useEmployees();
  const createEmployee = useCreateEmployee();
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { control, handleSubmit, register, reset, formState: { errors } } = useForm<FormValues>();

  const activeEmployees = (employees ?? []).filter((e) => e.status === "active");

  const onSubmit = async (values: FormValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.EmployeeCreate.parse({
        first_name: values.first_name,
        last_name: values.last_name,
        position_id: values.position_id ? Number(values.position_id) : null,
        manager_employee_id: values.manager_employee_id ? Number(values.manager_employee_id) : null,
        hire_date: values.hire_date,
        salary: values.salary || null,
      });
      await createEmployee.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos del empleado");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nuevo empleado
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Nuevo empleado</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="first_name">Nombre</Label>
            <Input id="first_name" {...register("first_name", { required: true })} />
            {errors.first_name && <p className="text-sm text-destructive">Ingresá un nombre</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="last_name">Apellido</Label>
            <Input id="last_name" {...register("last_name", { required: true })} />
            {errors.last_name && <p className="text-sm text-destructive">Ingresá un apellido</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Puesto (opcional)</Label>
            <Controller
              control={control}
              name="position_id"
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger aria-label="Puesto"><SelectValue placeholder="Sin puesto" /></SelectTrigger>
                  <SelectContent>
                    {positions?.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.title}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Gerente (opcional)</Label>
            <Controller
              control={control}
              name="manager_employee_id"
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger aria-label="Gerente"><SelectValue placeholder="Sin gerente" /></SelectTrigger>
                  <SelectContent>
                    {activeEmployees.map((e) => (
                      <SelectItem key={e.id} value={String(e.id)}>{e.first_name} {e.last_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="hire_date">Fecha de contratación</Label>
            <Input id="hire_date" type="date" {...register("hire_date", { required: true })} />
            {errors.hire_date && <p className="text-sm text-destructive">Elegí una fecha</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="salary">Salario (opcional)</Label>
            <Input id="salary" type="number" step="0.01" {...register("salary")} />
          </div>
          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear empleado"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
