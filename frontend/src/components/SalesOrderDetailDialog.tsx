import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useSalesOrder,
  useConfirmSalesOrder,
  useStartPreparationSalesOrder,
  useShipSalesOrder,
  useInvoiceSalesOrder,
  useCancelSalesOrder,
} from "@/hooks/use-sales";
import { useProducts } from "@/hooks/use-inventory";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = {
  draft: "Borrador",
  confirmed: "Confirmada",
  en_preparacion: "En preparación",
  enviado: "Enviada",
  facturado: "Facturada",
  cancelado: "Cancelada",
};

export function SalesOrderDetailDialog({ orderId, onOpenChange }: { orderId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data: order, isLoading, error } = useSalesOrder(orderId);
  const { data: products } = useProducts();
  const confirmOrder = useConfirmSalesOrder();
  const startPreparation = useStartPreparationSalesOrder();
  const shipOrder = useShipSalesOrder();
  const invoiceOrder = useInvoiceSalesOrder();
  const cancelOrder = useCancelSalesOrder();
  const [shipQty, setShipQty] = useState<Record<number, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const productName = (id: number) => products?.find((p) => p.id === id)?.name ?? `#${id}`;

  const handleAction = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "No se pudo completar la acción");
    }
  };

  const handleShipLine = async (lineId: number) => {
    const qty = Number(shipQty[lineId]);
    if (!qty || qty <= 0 || !orderId) return;
    await handleAction(async () => {
      await shipOrder.mutateAsync({ orderId, payload: { lines: [{ line_id: lineId, quantity: qty }] } });
      setShipQty((prev) => ({ ...prev, [lineId]: "" }));
    });
  };

  const canShip = order?.status === "confirmed" || order?.status === "en_preparacion";

  return (
    <Dialog open={orderId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{order?.number ?? "Orden de venta"}</DialogTitle>
          <DialogDescription>{order ? STATUS_LABELS[order.status] : ""}</DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}

        {order && (
          <div className="flex flex-col gap-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1 font-medium">Producto</th>
                  <th className="py-1 font-medium">Cantidad</th>
                  <th className="py-1 font-medium">Enviado</th>
                  {canShip && <th className="py-1 font-medium">Enviar ahora</th>}
                </tr>
              </thead>
              <tbody>
                {order.lines.map((line) => (
                  <tr key={line.id} className="border-b border-border">
                    <td className="py-1.5">{productName(line.product_id)}</td>
                    <td className="py-1.5">{line.quantity}</td>
                    <td className="py-1.5">{line.quantity_shipped}</td>
                    {canShip && (
                      <td className="py-1.5">
                        {line.quantity_shipped < line.quantity ? (
                          <div className="flex gap-1">
                            <Input
                              type="number"
                              step="0.0001"
                              className="h-8 w-20"
                              value={shipQty[line.id] ?? ""}
                              onChange={(e) => setShipQty((prev) => ({ ...prev, [line.id]: e.target.value }))}
                            />
                            <Button size="sm" className="h-8" onClick={() => handleShipLine(line.id)}>
                              Enviar
                            </Button>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">Completo</span>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>

            {actionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{actionError}</p>}

            <div className="flex gap-2">
              {order.status === "draft" && (
                <>
                  <Button size="sm" onClick={() => handleAction(() => confirmOrder.mutateAsync(order.id))}>Confirmar</Button>
                  <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelOrder.mutateAsync(order.id))}>Cancelar</Button>
                </>
              )}
              {order.status === "confirmed" && (
                <>
                  <Button size="sm" onClick={() => handleAction(() => startPreparation.mutateAsync(order.id))}>Pasar a preparación</Button>
                  <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelOrder.mutateAsync(order.id))}>Cancelar</Button>
                </>
              )}
              {order.status === "en_preparacion" && (
                <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelOrder.mutateAsync(order.id))}>Cancelar</Button>
              )}
              {order.status === "enviado" && (
                <Button size="sm" onClick={() => handleAction(() => invoiceOrder.mutateAsync(order.id))}>Facturar</Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
