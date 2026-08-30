import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { schemas } from "@/lib/generated/schemas";
import { useCreateUser } from "@/hooks/use-core-data";
import { useRoles } from "@/hooks/use-core-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { ApiError } from "@/lib/api-client";
import { UserPlus } from "lucide-react";
import type { z } from "zod";

type UserCreateValues = z.infer<typeof schemas.UserCreate>;

export function CreateUserDialog() {
  const [open, setOpen] = useState(false);
  const createUser = useCreateUser();
  const { data: roles } = useRoles();

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<UserCreateValues>({
    resolver: zodResolver(schemas.UserCreate),
    defaultValues: { role_ids: [] },
  });

  const onSubmit = async (values: UserCreateValues) => {
    try {
      await createUser.mutateAsync(values);
      reset();
      setOpen(false);
    } catch (err) {
      if (err instanceof ApiError) {
        setError("root", { message: err.message });
      } else {
        setError("root", { message: "No se pudo crear el usuario" });
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <UserPlus className="size-4" />
          Nuevo usuario
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo usuario</DialogTitle>
          <DialogDescription>Se crea con acceso inmediato a esta empresa.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="full_name">Nombre completo</Label>
            <Input id="full_name" {...register("full_name")} />
            {errors.full_name && <p className="text-sm text-destructive">{errors.full_name.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Correo</Label>
            <Input id="email" type="email" {...register("email")} />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Contraseña temporal</Label>
            <Input id="password" type="password" {...register("password")} />
            {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
          </div>

          {roles && roles.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label>Roles</Label>
              <Controller
                control={control}
                name="role_ids"
                render={({ field }) => (
                  <div className="flex flex-wrap gap-3">
                    {roles.map((role) => (
                      <label key={role.id} className="flex items-center gap-1.5 text-sm">
                        <input
                          type="checkbox"
                          checked={field.value?.includes(role.id) ?? false}
                          onChange={(e) => {
                            const current = field.value ?? [];
                            field.onChange(
                              e.target.checked ? [...current, role.id] : current.filter((id) => id !== role.id)
                            );
                          }}
                        />
                        {role.name}
                      </label>
                    ))}
                  </div>
                )}
              />
            </div>
          )}

          {errors.root && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errors.root.message}
            </p>
          )}

          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creando…" : "Crear usuario"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
