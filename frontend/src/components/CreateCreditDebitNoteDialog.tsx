import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { useCreateCreditDebitNote, useInvoices, useTaxRates } from "@/hooks/use-accounting";
import { useContacts } from "@/hooks/use-contacts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { schemas } from "@/lib/generated/schemas";
import { ApiError } from "@/lib/api-client";
import { Plus, Trash2 } from "lucide-react";

interface LineDraft {
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate_id: string;
}

const emptyLine: LineDraft = { description: "", quantity: "1", unit_price: "", tax_rate_id: "" };

interface HeaderValues {
  note_type: "credit" | "debit";
  direction: "sale" | "purchase";
  contact_id: number;
  invoice_id: string;
  reason: string;
  issue_date: string;
}

export function CreateCreditDebitNoteDialog() {
  const [open, setOpen] = useState(false);
  const { data: contacts } = useContacts("");
  const { data: invoices } = useInvoices();
  const { data: taxRates } = useTaxRates();
  const createNote = useCreateCreditDebitNote();

  const [lines, setLines] = useState<LineDraft[]>([{ ...emptyLine }]);
  const [rootError, setRootError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const { control, handleSubmit, register, reset, watch, formState: { errors } } = useForm<HeaderValues>({
    defaultValues: { note_type: "credit", direction: "sale" },
  });
  const direction = watch("direction");
  const contactId = watch("contact_id");
  const eligibleContacts = contacts?.filter((c) => (direction === "sale" ? c.is_customer : c.is_vendor)) ?? [];
  const eligibleInvoices = (invoices ?? []).filter(
    (inv) => inv.direction === direction && inv.contact_id === Number(contactId)
  );

  const updateLine = (index: number, field: keyof LineDraft, value: string) => {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));
  };

  const onSubmit = async (header: HeaderValues) => {
    setRootError(null);
    setSubmitting(true);
    try {
      const parsed = schemas.CreditDebitNoteCreate.parse({
        note_type: header.note_type,
        direction: header.direction,
        contact_id: header.contact_id,
        invoice_id: header.invoice_id ? Number(header.invoice_id) : null,
        reason: header.reason,
        issue_date: header.issue_date,
        lines: lines.map((l) => ({
          description: l.description,
          quantity: l.quantity,
          unit_price: l.unit_price,
          tax_rate_id: l.tax_rate_id ? Number(l.tax_rate_id) : null,
        })),
      });
      await createNote.mutateAsync(parsed);
      reset();
      setLines([{ ...emptyLine }]);
      setOpen(false);
    } catch (err) {
      setRootError(err instanceof ApiError ? err.message : "Revisá los datos de la nota");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="size-4" />
          Nueva nota
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Nueva nota de crédito/débito</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Tipo de nota</Label>
              <Controller
                control={control}
                name="note_type"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger aria-label="Tipo de nota"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="credit">Crédito</SelectItem>
                      <SelectItem value="debit">Débito</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Origen</Label>
              <Controller
                control={control}
                name="direction"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger aria-label="Origen"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sale">Venta</SelectItem>
                      <SelectItem value="purchase">Proveedor</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
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

          <div className="flex flex-col gap-1.5">
            <Label>Factura relacionada (opcional)</Label>
            <Controller
              control={control}
              name="invoice_id"
              render={({ field }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger aria-label="Factura relacionada"><SelectValue placeholder="Sin factura relacionada" /></SelectTrigger>
                  <SelectContent>
                    {eligibleInvoices.map((inv) => <SelectItem key={inv.id} value={String(inv.id)}>{inv.number}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reason">Motivo</Label>
            <Input id="reason" {...register("reason", { required: true })} />
            {errors.reason && <p className="text-sm text-destructive">Ingresá un motivo</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="issue_date">Fecha de emisión</Label>
            <Input id="issue_date" type="date" {...register("issue_date", { required: true })} />
            {errors.issue_date && <p className="text-sm text-destructive">Elegí una fecha</p>}
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label>Líneas</Label>
              <Button type="button" size="sm" variant="outline" onClick={() => setLines((prev) => [...prev, { ...emptyLine }])}>
                + Línea
              </Button>
            </div>
            {lines.map((line, index) => (
              <div key={index} className="flex flex-col gap-2 rounded-md border border-border p-2">
                <Input
                  placeholder="Descripción"
                  value={line.description}
                  onChange={(e) => updateLine(index, "description", e.target.value)}
                />
                <div className="grid grid-cols-[1fr_1fr_1fr_auto] items-end gap-2">
                  <div className="flex flex-col gap-1">
                    <Label className="text-xs">Cantidad</Label>
                    <Input type="number" step="0.0001" value={line.quantity} onChange={(e) => updateLine(index, "quantity", e.target.value)} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label className="text-xs">Precio unit.</Label>
                    <Input type="number" step="0.01" value={line.unit_price} onChange={(e) => updateLine(index, "unit_price", e.target.value)} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label className="text-xs">Impuesto</Label>
                    <Select value={line.tax_rate_id} onValueChange={(v) => updateLine(index, "tax_rate_id", v)}>
                      <SelectTrigger aria-label={`Impuesto línea ${index + 1}`}><SelectValue placeholder="Sin impuesto" /></SelectTrigger>
                      <SelectContent>
                        {taxRates?.map((t) => <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setLines((prev) => prev.filter((_, i) => i !== index))} disabled={lines.length === 1}>
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>

          {rootError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{rootError}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Creando…" : "Crear nota"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
