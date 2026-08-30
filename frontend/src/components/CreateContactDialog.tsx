import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { schemas } from "@/lib/generated/schemas";
import { useCreateContact } from "@/hooks/use-contacts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { ApiError } from "@/lib/api-client";
import { UserRoundPlus } from "lucide-react";
import type { z } from "zod";

type ContactCreateValues = z.input<typeof schemas.ContactCreate>;

const ROLE_FIELDS = [
  { key: "is_customer", label: "Cliente" },
  { key: "is_vendor", label: "Proveedor" },
  { key: "is_patient", label: "Paciente" },
  { key: "is_lead", label: "Prospecto" },
] as const;

export function CreateContactDialog() {
  const [open, setOpen] = useState(false);
  const createContact = useCreateContact();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<ContactCreateValues>({
    resolver: zodResolver(schemas.ContactCreate),
    defaultValues: {
      is_customer: false,
      is_vendor: false,
      is_patient: false,
      is_lead: false,
    },
  });

  const onSubmit = async (values: ContactCreateValues) => {
    try {
      // RHF con zodResolver entrega en runtime el output ya parseado
      // (defaults aplicados), pero react-hook-form tipa el callback con el
      // tipo "input" genéricamente — se re-parsea acá para que el tipo que
      // llega a la mutación sea el output real (mismatch conocido de
      // RHF+Zod cuando hay .default(), no un error de lógica).
      const parsed = schemas.ContactCreate.parse(values);
      await createContact.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setError("root", { message: err.message });
      } else {
        setError("root", { message: "No se pudo crear el contacto" });
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <UserRoundPlus className="size-4" />
          Nuevo contacto
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo contacto</DialogTitle>
          <DialogDescription>Un contacto puede ser cliente, proveedor, paciente y/o prospecto a la vez.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" {...register("name")} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Rol</Label>
            <div className="flex flex-wrap gap-3">
              {ROLE_FIELDS.map(({ key, label }) => (
                <label key={key} className="flex items-center gap-1.5 text-sm">
                  <input type="checkbox" {...register(key)} />
                  {label}
                </label>
              ))}
            </div>
            {/* El error del model_validator del backend (Zod generado no
                replica validadores custom de Pydantic — solo la forma de
                los campos) aparece acá como error de servidor, no de
                cliente. Ver errors.root abajo. */}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">Correo</Label>
              <Input id="email" type="email" {...register("email")} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="phone">Teléfono</Label>
              <Input id="phone" {...register("phone")} />
            </div>
          </div>

          {errors.root && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errors.root.message}
            </p>
          )}

          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creando…" : "Crear contacto"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
