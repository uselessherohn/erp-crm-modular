import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { usePayment, usePostPayment, useCancelPayment } from "@/hooks/use-accounting";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = { draft: "Borrador", posted: "Contabilizado", cancelled: "Cancelado" };

export function PaymentDetailDialog({ paymentId, onOpenChange }: { paymentId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data: payment, isLoading, error } = usePayment(paymentId);
  const postPayment = usePostPayment();
  const cancelPayment = useCancelPayment();
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
    <Dialog open={paymentId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{payment?.number ?? "Pago"}</DialogTitle>
          <DialogDescription>
            {payment ? `${STATUS_LABELS[payment.status]} — ${payment.payment_date} — ${payment.amount}` : ""}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}

        {payment && (
          <div className="flex flex-col gap-4">
            {payment.allocations.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="py-1 font-medium">Factura</th>
                    <th className="py-1 font-medium">Monto aplicado</th>
                  </tr>
                </thead>
                <tbody>
                  {payment.allocations.map((a) => (
                    <tr key={a.id} className="border-b border-border">
                      <td className="py-1.5">#{a.invoice_id}</td>
                      <td className="py-1.5">{a.amount_applied}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {payment.allocations.length === 0 && (
              <p className="text-xs text-muted-foreground">Sin facturas asignadas — pago sin aplicar.</p>
            )}

            {actionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{actionError}</p>}

            {payment.status === "draft" && (
              <div className="flex gap-2">
                <Button size="sm" onClick={() => handleAction(() => postPayment.mutateAsync(payment.id))}>Contabilizar</Button>
                <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelPayment.mutateAsync(payment.id))}>Cancelar</Button>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
