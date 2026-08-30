import { useAccounts, useTaxRates, useDocumentAccountMappings } from "@/hooks/use-accounting";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CreateAccountDialog } from "@/components/CreateAccountDialog";
import { CreateTaxRateDialog } from "@/components/CreateTaxRateDialog";
import { CreateDocumentAccountMappingDialog } from "@/components/CreateDocumentAccountMappingDialog";
import { ApiError } from "@/lib/api-client";

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  receivable: "Cuentas por cobrar",
  payable: "Cuentas por pagar",
  income: "Ingresos",
  tax: "Impuestos",
  cash_bank: "Caja/Banco",
  adjustment: "Ajuste",
};

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  sales_invoice: "Factura de venta",
  purchase_invoice: "Factura de proveedor",
  sales_credit_note: "Nota de crédito (venta)",
  sales_debit_note: "Nota de débito (venta)",
  purchase_credit_note: "Nota de crédito (proveedor)",
  purchase_debit_note: "Nota de débito (proveedor)",
  payment_received: "Cobro",
  payment_made: "Pago",
};

export function AccountsPage() {
  const { data: accounts, isLoading: loadingAccounts, error: accountsError } = useAccounts();
  const { data: taxRates, isLoading: loadingTaxRates, error: taxRatesError } = useTaxRates();
  const { data: mappings, isLoading: loadingMappings, error: mappingsError } = useDocumentAccountMappings();

  const accountLabel = (id: number) => {
    const acc = accounts?.find((a) => a.id === id);
    return acc ? `${acc.code} — ${acc.name}` : `#${id}`;
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Contabilidad — Configuración</h1>
        <p className="text-sm text-muted-foreground">
          Plan de cuentas mínimo, tasas de impuesto y mapeo de cada tipo de documento a sus cuentas contables.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Plan de cuentas</CardTitle>
          <CreateAccountDialog />
        </CardHeader>
        <CardContent>
          {loadingAccounts && <p className="text-sm text-muted-foreground">Cargando…</p>}
          {accountsError instanceof ApiError && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{accountsError.message}</p>
          )}
          {!loadingAccounts && !accountsError && (accounts?.length ?? 0) === 0 && (
            <p className="text-sm text-muted-foreground">Todavía no hay cuentas — creá al menos una por cada rol antes de facturar.</p>
          )}
          {(accounts?.length ?? 0) > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1 font-medium">Código</th>
                  <th className="py-1 font-medium">Nombre</th>
                  <th className="py-1 font-medium">Rol</th>
                  <th className="py-1 font-medium">Por defecto</th>
                </tr>
              </thead>
              <tbody>
                {accounts?.map((a) => (
                  <tr key={a.id} className="border-b border-border last:border-0">
                    <td className="py-1.5">{a.code}</td>
                    <td className="py-1.5">{a.name}</td>
                    <td className="py-1.5 text-muted-foreground">{ACCOUNT_TYPE_LABELS[a.account_type]}</td>
                    <td className="py-1.5">{a.is_default ? "Sí" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Tasas de impuesto</CardTitle>
          <CreateTaxRateDialog />
        </CardHeader>
        <CardContent>
          {loadingTaxRates && <p className="text-sm text-muted-foreground">Cargando…</p>}
          {taxRatesError instanceof ApiError && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{taxRatesError.message}</p>
          )}
          {!loadingTaxRates && !taxRatesError && (taxRates?.length ?? 0) === 0 && (
            <p className="text-sm text-muted-foreground">Todavía no hay tasas de impuesto.</p>
          )}
          {(taxRates?.length ?? 0) > 0 && (
            <table className="w-full text-sm">
              <tbody>
                {taxRates?.map((t) => (
                  <tr key={t.id} className="border-b border-border last:border-0">
                    <td className="py-1.5">{t.name}</td>
                    <td className="py-1.5 text-right font-medium">{t.rate}%</td>
                    <td className="py-1.5 text-right text-muted-foreground">{t.is_default ? "Por defecto" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Mapeo documento → cuentas</CardTitle>
          <CreateDocumentAccountMappingDialog />
        </CardHeader>
        <CardContent>
          <p className="mb-3 text-xs text-muted-foreground">
            Cada tipo de documento necesita una cuenta configurada por rol antes de poder contabilizarse.
          </p>
          {loadingMappings && <p className="text-sm text-muted-foreground">Cargando…</p>}
          {mappingsError instanceof ApiError && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{mappingsError.message}</p>
          )}
          {!loadingMappings && !mappingsError && (mappings?.length ?? 0) === 0 && (
            <p className="text-sm text-muted-foreground">Todavía no hay mapeos configurados.</p>
          )}
          {(mappings?.length ?? 0) > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1 font-medium">Documento</th>
                  <th className="py-1 font-medium">Rol</th>
                  <th className="py-1 font-medium">Cuenta</th>
                </tr>
              </thead>
              <tbody>
                {mappings?.map((m) => (
                  <tr key={m.id} className="border-b border-border last:border-0">
                    <td className="py-1.5">{DOCUMENT_TYPE_LABELS[m.document_type]}</td>
                    <td className="py-1.5 text-muted-foreground">{ACCOUNT_TYPE_LABELS[m.role]}</td>
                    <td className="py-1.5">{accountLabel(m.account_id)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
