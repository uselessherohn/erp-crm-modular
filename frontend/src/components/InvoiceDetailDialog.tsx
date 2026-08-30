import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useInvoice, usePostInvoice, useCancelInvoice } from "@/hooks/use-accounting";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = {
  draft: "Borrador",
  posted: "Contabilizada",
  partially_paid: "Pago parcial",
  paid: "Pagada",
  cancelled: "Cancelada",
};

export function InvoiceDetailDialog({ invoiceId, onOpenChange }: { invoiceId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data: invoice, isLoading, error } = useInvoice(invoiceId);
  const postInvoice = usePostInvoice();
  const cancelInvoice = useCancelInvoice();
  const [actionError, setActionError] = useState<string | null>(null);

  const handleAction = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "No se pudo completar la acción");
    }
  };

  return (
    <Dialog open={invoiceId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{invoice?.number ?? "Factura"}</DialogTitle>
          <DialogDescription>
            {invoice ? `${STATUS_LABELS[invoice.status]} — emitida ${invoice.issue_date}` : ""}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}

        {invoice && (
          <div className="flex flex-col gap-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1 font-medium">Descripción</th>
                  <th className="py-1 font-medium">Cant.</th>
                  <th className="py-1 font-medium">Precio</th>
                  <th className="py-1 font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {invoice.lines.map((line) => (
                  <tr key={line.id} className="border-b border-border">
                    <td className="py-1.5">{line.description}</td>
                    <td className="py-1.5">{line.quantity}</td>
                    <td className="py-1.5">{line.unit_price}</td>
                    <td className="py-1.5">{line.line_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="flex justify-end gap-6 text-sm">
              <div className="text-right">
                <p className="text-muted-foreground">Subtotal</p>
                <p className="font-medium">{invoice.subtotal}</p>
              </div>
              <div className="text-right">
                <p className="text-muted-foreground">Impuesto</p>
                <p className="font-medium">{invoice.tax_amount}</p>
              </div>
              <div className="text-right">
                <p className="text-muted-foreground">Total</p>
                <p className="font-medium">{invoice.total}</p>
              </div>
              <div className="text-right">
                <p className="text-muted-foreground">Saldo</p>
                <p className="font-medium">{invoice.balance_due}</p>
              </div>
            </div>

            {actionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{actionError}</p>}

            <div className="flex flex-wrap items-end gap-2">
              {invoice.status === "draft" && (
                <>
                  <Button size="sm" onClick={() => handleAction(() => postInvoice.mutateAsync(invoice.id))}>Contabilizar</Button>
                  <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelInvoice.mutateAsync(invoice.id))}>Cancelar</Button>
                </>
              )}
              {invoice.status !== "draft" && invoice.status !== "cancelled" && (
                <p className="text-xs text-muted-foreground">
                  Una factura contabilizada se revierte con una nota de crédito/débito, no se cancela directo.
                </p>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
