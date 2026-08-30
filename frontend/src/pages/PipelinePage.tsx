import { useState } from "react";
import { useStages, useOpportunities } from "@/hooks/use-pipeline";
import { useContacts } from "@/hooks/use-contacts";
import { CreateStageDialog } from "@/components/CreateStageDialog";
import { CreateOpportunityDialog } from "@/components/CreateOpportunityDialog";
import { OpportunityDetailDialog } from "@/components/OpportunityDetailDialog";
import { ApiError } from "@/lib/api-client";

export function PipelinePage() {
  const { data: stages, isLoading: loadingStages, error: stagesError } = useStages();
  const { data: opportunities, isLoading: loadingOpportunities, error: opportunitiesError } = useOpportunities();
  const { data: contacts } = useContacts("");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const contactName = (id: number) => contacts?.find((c) => c.id === id)?.name ?? `#${id}`;

  const isLoading = loadingStages || loadingOpportunities;
  const error = stagesError ?? opportunitiesError;

  const sortedStages = [...(stages ?? [])].sort((a, b) => a.sort_order - b.sort_order);
  const openOpportunities = (opportunities ?? []).filter((o) => o.status === "open");

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pipeline de oportunidades</h1>
          <p className="text-sm text-muted-foreground">
            Kanban con etapas configurables. Cerrar ganada/perdida es una acción explícita, no un simple arrastre.
          </p>
        </div>
        <div className="flex gap-2">
          <CreateStageDialog />
          <CreateOpportunityDialog />
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.code === "PACKAGE_NOT_LICENSED"
            ? "El paquete Administrativo no está activo para esta compañía — el pipeline de oportunidades requiere ese paquete."
            : error.message}
        </p>
      )}

      {!isLoading && !error && sortedStages.filter((s) => !s.is_won && !s.is_lost).length === 0 && (
        <p className="text-sm text-muted-foreground">
          Todavía no hay etapas configuradas — creá al menos una etapa (y una "ganada"/"perdida") antes de registrar oportunidades.
        </p>
      )}

      {!isLoading && !error && (
        <div className="flex flex-1 gap-4 overflow-x-auto">
          {sortedStages
            .filter((s) => !s.is_won && !s.is_lost)
            .map((stage) => {
              const stageOpportunities = openOpportunities.filter((o) => o.stage_id === stage.id);
              return (
                <div key={stage.id} className="flex w-72 shrink-0 flex-col gap-2 rounded-lg border border-border bg-muted/30 p-3">
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-medium">{stage.name}</h2>
                    <span className="text-xs text-muted-foreground">{stageOpportunities.length}</span>
                  </div>
                  <div className="flex flex-col gap-2">
                    {stageOpportunities.map((opp) => (
                      <button
                        key={opp.id}
                        type="button"
                        onClick={() => setSelectedId(opp.id)}
                        className="rounded-md border border-border bg-background p-2 text-left text-sm shadow-sm hover:border-primary"
                      >
                        <p className="font-medium">{opp.name}</p>
                        <p className="text-xs text-muted-foreground">{contactName(opp.contact_id)}</p>
                        {opp.amount && <p className="mt-1 text-xs font-medium">{opp.currency_code} {opp.amount}</p>}
                      </button>
                    ))}
                    {stageOpportunities.length === 0 && (
                      <p className="text-xs text-muted-foreground">Sin oportunidades.</p>
                    )}
                  </div>
                </div>
              );
            })}
        </div>
      )}

      <OpportunityDetailDialog opportunityId={selectedId} onOpenChange={(open) => !open && setSelectedId(null)} />
    </div>
  );
}
