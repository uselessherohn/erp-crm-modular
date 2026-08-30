import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  usePurchaseOrder,
  useConfirmPurchaseOrder,
  useCancelPurchaseOrder,
  useClosePurchaseOrder,
  useReceivePurchaseOrder,
} from "@/hooks/use-purchasing";
import { useProducts } from "@/hooks/use-inventory";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = {
  draft: "Borrador",
  confirmed: "Confirmada",
  received: "Recibida",
  closed: "Cerrada",
  cancelled: "Cancelada",
};

export function PurchaseOrderDetailDialog({ poId, onOpenChange }: { poId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data: po, isLoading, error } = usePurchaseOrder(poId);
  const { data: products } = useProducts();
  const confirmPO = useConfirmPurchaseOrder();
  const cancelPO = useCancelPurchaseOrder();
  const closePO = useClosePurchaseOrder();
  const receivePO = useReceivePurchaseOrder();
  const [receiveQty, setReceiveQty] = useState<Record<number, string>>({});
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

  const handleReceiveLine = async (lineId: number) => {
    const qty = Number(receiveQty[lineId]);
    if (!qty || qty <= 0 || !poId) return;
    await handleAction(async () => {
      await receivePO.mutateAsync({ poId, payload: { lines: [{ line_id: lineId, quantity: qty }] } });
      setReceiveQty((prev) => ({ ...prev, [lineId]: "" }));
    });
  };

  return (
    <Dialog open={poId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{po?.number ?? "Orden de compra"}</DialogTitle>
          <DialogDescription>{po && STATUS_LABELS[po.status]}</DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}

        {po && (
          <div className="flex flex-col gap-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1 font-medium">Producto</th>
                  <th className="py-1 font-medium">Ordenado</th>
                  <th className="py-1 font-medium">Recibido</th>
                  {po.status === "confirmed" && <th className="py-1 font-medium">Recibir ahora</th>}
                </tr>
              </thead>
              <tbody>
                {po.lines.map((line) => (
                  <tr key={line.id} className="border-b border-border">
                    <td className="py-1.5">{productName(line.product_id)}</td>
                    <td className="py-1.5">{line.quantity_ordered}</td>
                    <td className="py-1.5">{line.quantity_received}</td>
                    {po.status === "confirmed" && (
                      <td className="py-1.5">
                        {line.quantity_received < line.quantity_ordered ? (
                          <div className="flex gap-1">
                            <Input
                              type="number"
                              step="0.0001"
                              className="h-8 w-20"
                              value={receiveQty[line.id] ?? ""}
                              onChange={(e) => setReceiveQty((prev) => ({ ...prev, [line.id]: e.target.value }))}
                            />
                            <Button size="sm" className="h-8" onClick={() => handleReceiveLine(line.id)}>
                              Recibir
                            </Button>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">Completa</span>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>

            {actionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{actionError}</p>}

            <div className="flex gap-2">
              {po.status === "draft" && (
                <>
                  <Button size="sm" onClick={() => handleAction(() => confirmPO.mutateAsync(po.id))}>Confirmar</Button>
                  <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelPO.mutateAsync(po.id))}>Cancelar</Button>
                </>
              )}
              {po.status === "confirmed" && (
                <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelPO.mutateAsync(po.id))}>Cancelar</Button>
              )}
              {po.status === "received" && (
                <Button size="sm" onClick={() => handleAction(() => closePO.mutateAsync(po.id))}>Cerrar</Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
