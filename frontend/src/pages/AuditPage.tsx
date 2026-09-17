import { useState, useEffect } from "react";
import { useAuditLogs, useRetentionPolicy, useUpdateRetentionPolicy, usePurgeEligibleCount, type AuditLogFilters } from "@/hooks/use-audit";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";

export function AuditPage() {
  return (
    <div className="flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-medium text-foreground">Auditoría</h1>
        <p className="text-sm text-muted-foreground">
          Registro de actividad, control de cambios y política de retención (módulo 25).
        </p>
      </header>
      <RetentionSection />
      <LogsSection />
    </div>
  );
}

function RetentionSection() {
  const { data: policy, isLoading, error } = useRetentionPolicy();
  const { data: purgeEligible } = usePurgeEligibleCount();
  const updatePolicy = useUpdateRetentionPolicy();
  const [days, setDays] = useState<string>("");
  const [initialized, setInitialized] = useState(false);

  // Bug real encontrado en esta sesión (verificación externa, sep-2026,
  // al escribir el test de integración de esta página): `days` arrancaba
  // en "" y el campo mostraba `policy.retention_days` solo como fallback
  // de RENDER (no como valor real del input) mientras `days === ""`. Al
  // vaciar el campo con la intención de escribir un número nuevo, el
  // fallback volvía a mostrar el valor persistido de inmediato — y
  // escribir después lo CONCATENABA (ej. vaciar y escribir "51" con un
  // valor persistido de 90 días dejaba "9051" en el campo, no "51").
  // Corregido: `days` se inicializa UNA vez con el valor real ya
  // cargado (contenido editable de verdad, no un fallback de display),
  // así que vaciar el campo lo deja genuinamente vacío.
  useEffect(() => {
    if (!initialized && policy) {
      setDays(String(policy.retention_days));
      setInitialized(true);
    }
  }, [initialized, policy]);

  const save = async () => {
    const parsed = Number(days);
    if (!Number.isInteger(parsed) || parsed < 1) return;
    await updatePolicy.mutateAsync({ retention_days: parsed });
  };

  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-display text-lg font-medium text-foreground">Política de retención</h2>
      <p className="text-sm text-muted-foreground">
        Aplica solo a eventos operativos generales. Los eventos del expediente clínico (<code>medical.*</code>)
        nunca se purgan desde acá — quedan protegidos aparte por regulación, sin importar esta configuración.
      </p>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.code === "PERMISSION_DENIED" ? "No tenés permiso para ver la política de retención." : error.message}
        </p>
      )}

      {!isLoading && !error && (
        <div className="flex flex-wrap items-end gap-3 rounded-md border border-border p-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="retention-days">Días de retención</Label>
            <Input
              id="retention-days" type="number" min={1} max={3650}
              value={days}
              onChange={(e) => setDays(e.target.value)}
              className="w-32"
            />
          </div>
          <Button size="sm" onClick={save} disabled={updatePolicy.isPending}>
            Guardar
          </Button>
          {purgeEligible && (
            <p className="text-sm text-muted-foreground">
              {purgeEligible.eligible_count} evento{purgeEligible.eligible_count === 1 ? "" : "s"} operativo
              {purgeEligible.eligible_count === 1 ? "" : "s"} vencido{purgeEligible.eligible_count === 1 ? "" : "s"} según la
              política actual ({purgeEligible.excluded_medical_count} evento{purgeEligible.excluded_medical_count === 1 ? "" : "s"} clínico
              {purgeEligible.excluded_medical_count === 1 ? "" : "s"} excluido{purgeEligible.excluded_medical_count === 1 ? "" : "s"} de este conteo).
              La depuración física es un procedimiento de mantenimiento aparte, no un botón en este panel.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function LogsSection() {
  const [filters, setFilters] = useState<AuditLogFilters>({ limit: 50, offset: 0 });
  const { data: logs, isLoading, isFetching, error } = useAuditLogs(filters);

  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-display text-lg font-medium text-foreground">Registro de actividad</h2>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="filter-entity-type">Tipo de entidad</Label>
          <Input
            id="filter-entity-type" placeholder="ej. sales_order" className="w-44"
            value={filters.entity_type ?? ""}
            onChange={(e) => setFilters((f) => ({ ...f, entity_type: e.target.value || undefined, offset: 0 }))}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="filter-event">Evento</Label>
          <Input
            id="filter-event" placeholder="ej. sales.order.confirm" className="w-52"
            value={filters.event ?? ""}
            onChange={(e) => setFilters((f) => ({ ...f, event: e.target.value || undefined, offset: 0 }))}
          />
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.code === "PERMISSION_DENIED" ? "No tenés permiso para ver el registro de auditoría." : error.message}
        </p>
      )}

      {!isLoading && !error && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="whitespace-nowrap px-3 py-2">Fecha</th>
                <th className="whitespace-nowrap px-3 py-2">Evento</th>
                <th className="whitespace-nowrap px-3 py-2">Entidad</th>
                <th className="whitespace-nowrap px-3 py-2">Usuario</th>
                <th className="whitespace-nowrap px-3 py-2">Cambios</th>
              </tr>
            </thead>
            <tbody>
              {(logs ?? []).map((log) => (
                <tr key={log.id} className="border-t border-border align-top">
                  <td className="whitespace-nowrap px-3 py-2">{new Date(log.created_at).toLocaleString()}</td>
                  <td className="whitespace-nowrap px-3 py-2">{log.event}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {log.entity_type} #{log.entity_id}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">{log.user_id ?? "—"}</td>
                  <td className="px-3 py-2">
                    {log.changes ? (
                      <pre className="max-w-xs whitespace-pre-wrap break-words text-xs text-muted-foreground">
                        {JSON.stringify(log.changes, null, 2)}
                      </pre>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {(logs ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-muted-foreground">
                    Sin eventos para este filtro.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button
          size="sm" variant="ghost" disabled={(filters.offset ?? 0) === 0 || isFetching}
          onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - (f.limit ?? 50)) }))}
        >
          Anterior
        </Button>
        <Button
          size="sm" variant="ghost" disabled={(logs ?? []).length < (filters.limit ?? 50) || isFetching}
          onClick={() => setFilters((f) => ({ ...f, offset: (f.offset ?? 0) + (f.limit ?? 50) }))}
        >
          Siguiente
        </Button>
      </div>
    </section>
  );
}
