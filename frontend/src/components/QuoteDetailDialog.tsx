import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { useQuote, useSendQuote, useAcceptQuote, useCancelQuote, useConvertQuote } from "@/hooks/use-sales";
import { useProducts, useWarehouses } from "@/hooks/use-inventory";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = {
  draft: "Borrador",
  sent: "Enviada",
  accepted: "Aceptada",
  expired: "Vencida",
  cancelled: "Cancelada",
  converted: "Convertida",
};

export function QuoteDetailDialog({ quoteId, onOpenChange }: { quoteId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data: quote, isLoading, error } = useQuote(quoteId);
  const { data: products } = useProducts();
  const { data: warehouses } = useWarehouses();
  const sendQuote = useSendQuote();
  const acceptQuote = useAcceptQuote();
  const cancelQuote = useCancelQuote();
  const convertQuote = useConvertQuote();
  const [convertWarehouseId, setConvertWarehouseId] = useState("");
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

  return (
    <Dialog open={quoteId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{quote?.number ?? "Cotización"}</DialogTitle>
          <DialogDescription>
            {quote ? `${STATUS_LABELS[quote.status]} — válida hasta ${quote.valid_until}` : ""}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}

        {quote && (
          <div className="flex flex-col gap-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1 font-medium">Producto</th>
                  <th className="py-1 font-medium">Cantidad</th>
                  <th className="py-1 font-medium">Precio</th>
                </tr>
              </thead>
              <tbody>
                {quote.lines.map((line) => (
                  <tr key={line.id} className="border-b border-border">
                    <td className="py-1.5">{productName(line.product_id)}</td>
                    <td className="py-1.5">{line.quantity}</td>
                    <td className="py-1.5">{line.unit_price}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {actionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{actionError}</p>}

            <div className="flex flex-wrap items-end gap-2">
              {quote.status === "draft" && (
                <>
                  <Button size="sm" onClick={() => handleAction(() => sendQuote.mutateAsync(quote.id))}>Enviar</Button>
                  <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelQuote.mutateAsync(quote.id))}>Cancelar</Button>
                </>
              )}
              {quote.status === "sent" && (
                <>
                  <Button size="sm" onClick={() => handleAction(() => acceptQuote.mutateAsync(quote.id))}>Aceptar</Button>
                  <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelQuote.mutateAsync(quote.id))}>Cancelar</Button>
                </>
              )}
              {quote.status === "accepted" && (
                <div className="flex items-end gap-2">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-muted-foreground">Almacén para la orden</label>
                    <Select value={convertWarehouseId} onValueChange={setConvertWarehouseId}>
                      <SelectTrigger aria-label="Almacén conversión" className="w-40"><SelectValue placeholder="Almacén…" /></SelectTrigger>
                      <SelectContent>
                        {warehouses?.map((w) => <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    size="sm"
                    disabled={!convertWarehouseId}
                    onClick={() => handleAction(() => convertQuote.mutateAsync({ quoteId: quote.id, warehouseId: Number(convertWarehouseId) }))}
                  >
                    Convertir a orden
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
