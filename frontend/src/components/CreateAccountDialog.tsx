import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useCreateAccount } from "@/hooks/use-accounting";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";

const ACCOUNT_TYPES = [
  { value: "receivable", label: "Cuentas por cobrar" },
  { value: "payable", label: "Cuentas por pagar" },
  { value: "income", label: "Ingresos" },
  { value: "tax", label: "Impuestos" },
  { value: "cash_bank", label: "Caja/Banco" },
  { value: "adjustment", label: "Ajuste" },
];

interface FormValues {
  code: string;
  name: string;
  account_type: string;
}

export function CreateAccountDialog() {
  const [open, setOpen] = useState(false);
  const createAccount = useCreateAccount();
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { control, handleSubmit, register, reset, formState: { errors } } = useForm<FormValues>();

  const onSubmit = async (values: FormValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.AccountCreate.parse({
        code: values.code,
        name: values.name,
        account_type: values.account_type,
      });
      await createAccount.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos de la cuenta");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nueva cuenta
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Nueva cuenta contable</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="code">Código</Label>
            <Input id="code" {...register("code", { required: true })} />
            {errors.code && <p className="text-sm text-destructive">Ingresá un código</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="name">Nombre</Label>
            <Input id="name" {...register("name", { required: true })} />
            {errors.name && <p className="text-sm text-destructive">Ingresá un nombre</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Rol</Label>
            <Controller
              control={control}
              name="account_type"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger aria-label="Rol"><SelectValue placeholder="Elegir rol…" /></SelectTrigger>
                  <SelectContent>
                    {ACCOUNT_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.account_type && <p className="text-sm text-destructive">Elegí un rol</p>}
          </div>
          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear cuenta"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
