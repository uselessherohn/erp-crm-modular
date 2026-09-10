import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useCreateAppointment } from "@/hooks/use-medical";
import { useContacts } from "@/hooks/use-contacts";
import { useUsers } from "@/hooks/use-core-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";

interface FormValues {
  patient_contact_id: string;
  professional_user_id: string;
  scheduled_start: string;
  duration_minutes: string;
  reason: string;
}

export function CreateAppointmentDialog() {
  const [open, setOpen] = useState(false);
  const { data: contacts } = useContacts("");
  const { data: users } = useUsers();
  const createAppointment = useCreateAppointment();
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { control, handleSubmit, register, reset, formState: { errors } } = useForm<FormValues>({
    defaultValues: { duration_minutes: "30" },
  });

  const patients = (contacts ?? []).filter((c) => c.is_patient);

  const onSubmit = async (values: FormValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const start = new Date(values.scheduled_start);
      const end = new Date(start.getTime() + Number(values.duration_minutes) * 60_000);
      const parsed = schemas.AppointmentCreate.parse({
        patient_contact_id: Number(values.patient_contact_id),
        professional_user_id: Number(values.professional_user_id),
        scheduled_start: start.toISOString(),
        scheduled_end: end.toISOString(),
        reason: values.reason || null,
      });
      await createAppointment.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos de la cita");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nueva cita
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Nueva cita</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Paciente</Label>
            <Controller
              control={control}
              name="patient_contact_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger aria-label="Paciente"><SelectValue placeholder="Elegí un paciente" /></SelectTrigger>
                  <SelectContent>
                    {patients.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.patient_contact_id && <p className="text-sm text-destructive">Elegí un paciente</p>}
            {patients.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Sin contactos con el flag "paciente" activo — marcalo en Contactos primero.
              </p>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Profesional</Label>
            <Controller
              control={control}
              name="professional_user_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger aria-label="Profesional"><SelectValue placeholder="Elegí un profesional" /></SelectTrigger>
                  <SelectContent>
                    {users?.map((u) => <SelectItem key={u.id} value={String(u.id)}>{u.full_name ?? u.email}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.professional_user_id && <p className="text-sm text-destructive">Elegí un profesional</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="scheduled_start">Fecha y hora</Label>
            <Input id="scheduled_start" type="datetime-local" {...register("scheduled_start", { required: true })} />
            {errors.scheduled_start && <p className="text-sm text-destructive">Elegí fecha y hora</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="duration_minutes">Duración (minutos)</Label>
            <Input id="duration_minutes" type="number" min={5} step={5} {...register("duration_minutes", { required: true })} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reason">Motivo (opcional)</Label>
            <Input id="reason" {...register("reason")} />
          </div>
          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Agendando…" : "Agendar cita"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
