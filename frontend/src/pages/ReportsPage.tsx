import { useState } from "react";
import { useMetrics, useMetricData, exportMetric, useDashboards, useCreateDashboard, useDeleteDashboard } from "@/hooks/use-reports";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";

const SELECT_CLASS = "flex h-9 w-full rounded-md border border-input bg-card px-3 py-1 text-sm";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}
function firstOfMonthIso() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}

export function ReportsPage() {
  return (
    <div className="flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-medium text-foreground">Reportes</h1>
        <p className="text-sm text-muted-foreground">Reportes cruzados sobre ventas, cuentas por cobrar e inventario.</p>
      </header>
      <MetricExplorer />
      <DashboardsSection />
    </div>
  );
}

function MetricExplorer() {
  const { data: metrics, isLoading: loadingMetrics, error: metricsError } = useMetrics();
  const [metricKey, setMetricKey] = useState<string>("");
  const [dateFrom, setDateFrom] = useState(firstOfMonthIso());
  const [dateTo, setDateTo] = useState(todayIso());
  const { data: result, isFetching, error: dataError } = useMetricData(metricKey || null, dateFrom, dateTo);
  const [exportError, setExportError] = useState<string | null>(null);

  const runExport = async (format: "csv" | "xlsx" | "pdf") => {
    setExportError(null);
    try {
      await exportMetric(metricKey, dateFrom, dateTo, format);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "No se pudo exportar");
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-display text-lg font-medium text-foreground">Explorar métricas</h2>

      {loadingMetrics && <p className="text-sm text-muted-foreground">Cargando métricas…</p>}
      {metricsError instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {metricsError.code === "PERMISSION_DENIED" ? "No tenés permiso para ver reportes." : metricsError.message}
        </p>
      )}

      {!loadingMetrics && !metricsError && (
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="metric-select">Métrica</Label>
            <select id="metric-select" className={SELECT_CLASS} value={metricKey} onChange={(e) => setMetricKey(e.target.value)}>
              <option value="">Elegí una métrica</option>
              {(metrics ?? []).map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="date-from">Desde</Label>
            <Input id="date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="date-to">Hasta</Label>
            <Input id="date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          {metricKey && (
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => runExport("csv")}>
                Exportar CSV
              </Button>
              <Button size="sm" variant="ghost" onClick={() => runExport("xlsx")}>
                Exportar XLSX
              </Button>
              <Button size="sm" variant="ghost" onClick={() => runExport("pdf")}>
                Exportar PDF
              </Button>
            </div>
          )}
        </div>
      )}

      {exportError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {exportError}
        </p>
      )}

      {isFetching && <p className="text-sm text-muted-foreground">Calculando…</p>}
      {dataError instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {dataError.message}
        </p>
      )}

      {result && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
              <tr>
                {result.columns.map((col) => (
                  <th key={col} className="whitespace-nowrap px-3 py-2">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i} className="border-t border-border">
                  {result.columns.map((col) => (
                    <td key={col} className="whitespace-nowrap px-3 py-2">
                      {String(row[col] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
              {result.rows.length === 0 && (
                <tr>
                  <td colSpan={result.columns.length} className="px-3 py-4 text-center text-muted-foreground">
                    Sin datos para el rango elegido.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DashboardsSection() {
  const { data: dashboards, isLoading, error } = useDashboards();
  const { data: metrics } = useMetrics();
  const createDashboard = useCreateDashboard();
  const deleteDashboard = useDeleteDashboard();

  const [name, setName] = useState("");
  const [widgetMetric, setWidgetMetric] = useState("");

  const create = async () => {
    if (!name || !widgetMetric) return;
    const metricLabel = metrics?.find((m) => m.key === widgetMetric)?.label ?? widgetMetric;
    await createDashboard.mutateAsync({
      name,
      widgets: [{ widget_type: "table", metric_key: widgetMetric, title: metricLabel }],
    });
    setName("");
    setWidgetMetric("");
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-display text-lg font-medium text-foreground">Dashboards</h2>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.message}
        </p>
      )}

      {!isLoading && !error && (
        <ul className="flex flex-col gap-2">
          {(dashboards ?? []).map((d) => (
            <li key={d.id} className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
              <span>
                {d.name} <span className="text-muted-foreground">({d.widgets.length} widget{d.widgets.length === 1 ? "" : "s"})</span>
              </span>
              <Button size="sm" variant="ghost" onClick={() => deleteDashboard.mutate(d.id)}>
                Eliminar
              </Button>
            </li>
          ))}
          {(dashboards ?? []).length === 0 && <p className="text-sm text-muted-foreground">Todavía no hay dashboards.</p>}
        </ul>
      )}

      <div className="flex flex-wrap items-end gap-3 rounded-md border border-border p-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="dashboard-name">Nombre del dashboard</Label>
          <Input id="dashboard-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ventas del mes" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="dashboard-widget-metric">Primer widget (métrica)</Label>
          <select
            id="dashboard-widget-metric"
            className={SELECT_CLASS}
            value={widgetMetric}
            onChange={(e) => setWidgetMetric(e.target.value)}
          >
            <option value="">Elegí una métrica</option>
            {(metrics ?? []).map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <Button size="sm" onClick={create} disabled={!name || !widgetMetric || createDashboard.isPending}>
          Crear dashboard
        </Button>
      </div>
    </section>
  );
}
