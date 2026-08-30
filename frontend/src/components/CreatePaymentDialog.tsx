import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useCreatePayment, useInvoices } from "@/hooks/use-accounting";
import { useContacts } from "@/hooks/use-contacts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus, Trash2 } from "lucide-react";

interface AllocationDraft {
  invoice_id: string;
  amount_applied: string;
}

const emptyAllocation: AllocationDraft = { invoice_id: "", amount_applied: "" };

const METHODS = [
  { value: "cash", label: "Efectivo" },
  { value: "bank_transfer", label: "Transferencia" },
  { value: "card", label: "Tarjeta" },
  { value: "check", label: "Cheque" },
  { value: "other", label: "Otro" },
];

interface HeaderValues {
  direction: "sale" | "purchase";
  contact_id: number;
  payment_date: string;
  method: string;
  amount: string;
  reference: string;
}

export function CreatePaymentDialog() {
  const [open, setOpen] = useState(false);
  const { data: contacts } = useContacts("");
  const { data: invoices } = useInvoices();
  const createPayment = useCreatePayment();

  const [allocations, setAllocations] = useState<AllocationDraft[]>([]);
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { control, handleSubmit, register, reset, watch, formState: { errors } } = useForm<HeaderValues>({
    defaultValues: { direction: "sale", method: "cash" },
  });
  const direction = watch("direction");
  const contactId = watch("contact_id");
  const eligibleContacts = contacts?.filter((c) => (direction === "sale" ? c.is_customer : c.is_vendor)) ?? [];
  const eligibleInvoices = (invoices ?? []).filter(
    (inv) => inv.direction === direction && inv.contact_id === Number(contactId) && (inv.status === "posted" || inv.status === "partially_paid")
  );

  const updateAllocation = (index: number, field: keyof AllocationDraft, value: string) => {
    setAllocations((prev) => prev.map((a, i) => (i === index ? { ...a, [field]: value } : a)));
  };

  const onSubmit = async (header: HeaderValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.PaymentCreate.parse({
        direction: header.direction,
        contact_id: header.contact_id,
        payment_date: header.payment_date,
        method: header.method,
        amount: header.amount,
        reference: header.reference || null,
        allocations: allocations
          .filter((a) => a.invoice_id && a.amount_applied)
          .map((a) => ({ invoice_id: Number(a.invoice_id), amount_applied: a.amount_applied })),
      });
      await createPayment.mutateAsync(parsed);
      reset();
      setAllocations([]);
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos del pago");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nuevo pago
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Nuevo pago/cobro</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Tipo</Label>
            <Controller
              control={control}
              name="direction"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger aria-label="Tipo"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="sale">Cobro (cliente)</SelectItem>
                    <SelectItem value="purchase">Pago (proveedor)</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>{direction === "sale" ? "Cliente" : "Proveedor"}</Label>
            <Controller
              control={control}
              name="contact_id"
              rules={{ required: true }}
              render={({ field }) => (
                <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                  <SelectTrigger aria-label="Contacto"><SelectValue placeholder="Elegir contacto…" /></SelectTrigger>
                  <SelectContent>
                    {eligibleContacts.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.contact_id && <p className="text-sm text-destructive">Elegí un contacto</p>}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="payment_date">Fecha</Label>
              <Input id="payment_date" type="date" {...register("payment_date", { required: true })} />
              {errors.payment_date && <p className="text-sm text-destructive">Elegí una fecha</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Método</Label>
              <Controller
                control={control}
                name="method"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger aria-label="Método"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {METHODS.map((m) => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="amount">Monto</Label>
            <Input id="amount" type="number" step="0.01" {...register("amount", { required: true })} />
            {errors.amount && <p className="text-sm text-destructive">Ingresá un monto</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reference">Referencia</Label>
            <Input id="reference" {...register("reference")} />
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Asignar a facturas (opcional)</Label>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!contactId}
                onClick={() => setAllocations((prev) => [...prev, { ...emptyAllocation }])}
              >
                + Factura
              </Button>
            </div>
            {!contactId && <p className="text-xs text-muted-foreground">Elegí un contacto para poder asignar el pago a sus facturas.</p>}
            {allocations.map((alloc, index) => (
              <div key={index} className="grid grid-cols-[1fr_auto_auto] items-end gap-2 rounded-md border border-border p-2">
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Factura</Label>
                  <Select value={alloc.invoice_id} onValueChange={(v) => updateAllocation(index, "invoice_id", v)}>
                    <SelectTrigger aria-label={`Factura línea ${index + 1}`}><SelectValue placeholder="Factura…" /></SelectTrigger>
                    <SelectContent>
                      {eligibleInvoices.map((inv) => (
                        <SelectItem key={inv.id} value={String(inv.id)}>{inv.number} (saldo {inv.balance_due})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Monto aplicado</Label>
                  <Input type="number" step="0.01" className="w-28" value={alloc.amount_applied} onChange={(e) => updateAllocation(index, "amount_applied", e.target.value)} />
                </div>
                <Button type="button" size="sm" variant="ghost" onClick={() => setAllocations((prev) => prev.filter((_, i) => i !== index))}>
                  <Trash2 className="size-4" />
                </Button>
              </div>
            ))}
          </div>

          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear pago"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
