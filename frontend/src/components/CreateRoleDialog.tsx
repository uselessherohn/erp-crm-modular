import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { schemas } from "@/lib/generated/schemas";
import { useCreateRole } from "@/hooks/use-core-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { ApiError } from "@/lib/api-client";
import { ShieldPlus } from "lucide-react";
import type { z } from "zod";

type RoleCreateValues = z.infer<typeof schemas.RoleCreate>;

export function CreateRoleDialog() {
  const [open, setOpen] = useState(false);
  const createRole = useCreateRole();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<RoleCreateValues>({
    resolver: zodResolver(schemas.RoleCreate),
    defaultValues: { permission_ids: [] },
  });

  const onSubmit = async (values: RoleCreateValues) => {
    try {
      await createRole.mutateAsync(values);
      reset();
      setOpen(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setError("root", { message: err.message });
      } else {
        setError("root", { message: "No se pudo crear el rol" });
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <ShieldPlus className="size-4" />
          Nuevo rol
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo rol</DialogTitle>
          <DialogDescription>Los permisos se asignan después de crearlo.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" {...register("name")} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="description">Descripción</Label>
            <Input id="description" {...register("description")} />
          </div>

          {errors.root && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errors.root.message}
            </p>
          )}

          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creando…" : "Crear rol"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
