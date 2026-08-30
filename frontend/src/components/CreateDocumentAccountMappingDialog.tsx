import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useAccounts, useUpsertDocumentAccountMapping } from "@/hooks/use-accounting";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus } from "lucide-react";

const DOCUMENT_TYPES = [
  { value: "sales_invoice", label: "Factura de venta" },
  { value: "purchase_invoice", label: "Factura de proveedor" },
  { value: "sales_credit_note", label: "Nota de crédito (venta)" },
  { value: "sales_debit_note", label: "Nota de débito (venta)" },
  { value: "purchase_credit_note", label: "Nota de crédito (proveedor)" },
  { value: "purchase_debit_note", label: "Nota de débito (proveedor)" },
  { value: "payment_received", label: "Cobro" },
  { value: "payment_made", label: "Pago" },
];

const ACCOUNT_TYPES = [
  { value: "receivable", label: "Cuentas por cobrar" },
  { value: "payable", label: "Cuentas por pagar" },
  { value: "income", label: "Ingresos" },
  { value: "tax", label: "Impuestos" },
  { value: "cash_bank", label: "Caja/Banco" },
  { value: "adjustment", label: "Ajuste" },
];

interface FormValues {
  document_type: string;
  role: string;
  account_id: number;
}

export function CreateDocumentAccountMappingDialog() {
  const [open, setOpen] = useState(false);
  const { data: accounts } = useAccounts();
  const upsertMapping = useUpsertDocumentAccountMapping();
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { control, handleSubmit, reset, watch, formState: { errors } } = useForm<FormValues>();

  const selectedRole = watch("role");
  const compatibleAccounts = accounts?.filter((a) => a.account_type === selectedRole) ?? [];

  const onSubmit = async (values: FormValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.DocumentAccountMappingCreate.parse({
        document_type: values.document_type,
        role: values.role,
        account_id: Number(values.account_id),
      });
      await upsertMapping.mutateAsync(parsed);
      reset();
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos del mapeo");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nuevo mapeo
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Mapear documento a cuenta</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Documento</Label>
            <Controller
              control={control}
              name="document_type"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger aria-label="Documento"><SelectValue placeholder="Elegir documento…" /></SelectTrigger>
                  <SelectContent>
                    {DOCUMENT_TYPES.map((d) => <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.document_type && <p className="text-sm text-destructive">Elegí un documento</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Rol</Label>
            <Controller
              control={control}
              name="role"
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
            {errors.role && <p className="text-sm text-destructive">Elegí un rol</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Cuenta</Label>
            <Controller
              control={control}
              name="account_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Cuenta"><SelectValue placeholder="Elegir cuenta…" /></SelectTrigger>
                  <SelectContent>
                    {compatibleAccounts.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.code} — {a.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.account_id && <p className="text-sm text-destructive">Elegí una cuenta</p>}
            {selectedRole && compatibleAccounts.length === 0 && (
              <p className="text-xs text-muted-foreground">No hay cuentas del rol elegido todavía — creá una primero.</p>
            )}
          </div>
          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Guardando…" : "Guardar mapeo"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
