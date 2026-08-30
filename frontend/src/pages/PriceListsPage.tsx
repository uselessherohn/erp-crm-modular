import { usePriceLists } from "@/hooks/use-sales";
import { useProducts } from "@/hooks/use-inventory";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CreatePriceListDialog } from "@/components/CreatePriceListDialog";
import { ApiError } from "@/lib/api-client";

export function PriceListsPage() {
  const { data, isLoading, error } = usePriceLists();
  const { data: products } = useProducts();

  const productSku = (id: number) => products?.find((p) => p.id === id)?.sku ?? `#${id}`;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Listas de precios</h1>
          <p className="text-sm text-muted-foreground">Precios por producto, con quiebres de volumen.</p>
        </div>
        <CreatePriceListDialog />
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}
      {!isLoading && !error && (data?.length ?? 0) === 0 && <p className="text-sm text-muted-foreground">Todavía no hay listas de precios.</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((pl) => (
          <Card key={pl.id}>
            <CardHeader>
              <CardTitle className="text-base">{pl.name}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{pl.currency_code}</p>
              <table className="w-full text-sm">
                <tbody>
                  {pl.items.map((item) => (
                    <tr key={item.id} className="border-b border-border last:border-0">
                      <td className="py-1">{productSku(item.product_id)}</td>
                      <td className="py-1 text-muted-foreground">desde {item.min_quantity}</td>
                      <td className="py-1 text-right font-medium">{item.unit_price}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {pl.items.length === 0 && <p className="text-xs text-muted-foreground">Sin precios cargados todavía.</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
