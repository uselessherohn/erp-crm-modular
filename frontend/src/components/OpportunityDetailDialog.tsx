import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import {
  useOpportunity,
  useStages,
  useMoveOpportunityStage,
  useCloseOpportunityWon,
  useCloseOpportunityLost,
  useReopenOpportunity,
  useActivities,
  useCreateActivity,
  useCompleteActivity,
} from "@/hooks/use-pipeline";
import { useContacts } from "@/hooks/use-contacts";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = { open: "Abierta", won: "Ganada", lost: "Perdida" };
const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  call: "Llamada",
  email: "Correo",
  meeting: "Reunión",
  note: "Nota",
  task: "Tarea",
};

export function OpportunityDetailDialog({ opportunityId, onOpenChange }: { opportunityId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data: opportunity, isLoading, error } = useOpportunity(opportunityId);
  const { data: stages } = useStages();
  const { data: contacts } = useContacts("");
  const { data: activities } = useActivities();
  const moveStage = useMoveOpportunityStage();
  const closeWon = useCloseOpportunityWon();
  const closeLost = useCloseOpportunityLost();
  const reopen = useReopenOpportunity();
  const createActivity = useCreateActivity();
  const completeActivity = useCompleteActivity();

  const [actionError, setActionError] = useState<string | null>(null);
  const [lostReason, setLostReason] = useState("");
  const [newActivitySubject, setNewActivitySubject] = useState("");
  const [newActivityType, setNewActivityType] = useState("call");

  const handleAction = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "No se pudo completar la acción");
    }
  };

  const openStages = (stages ?? []).filter((s) => !s.is_won && !s.is_lost);
  const opportunityActivities = (activities ?? []).filter((a) => a.opportunity_id === opportunity?.id);
  const contactName = (id: number) => contacts?.find((c) => c.id === id)?.name ?? `#${id}`;

  return (
    <Dialog open={opportunityId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{opportunity?.name ?? "Oportunidad"}</DialogTitle>
          <DialogDescription>
            {opportunity ? `${STATUS_LABELS[opportunity.status]} — ${contactName(opportunity.contact_id)}` : ""}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}

        {opportunity && (
          <div className="flex flex-col gap-4">
            {opportunity.amount && (
              <p className="text-sm">
                Monto estimado: <span className="font-medium">{opportunity.currency_code} {opportunity.amount}</span>
              </p>
            )}

            {actionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{actionError}</p>}

            {opportunity.status === "open" && (
              <div className="flex flex-col gap-3 rounded-md border border-border p-3">
                <Label_ text="Mover a etapa" />
                <Select
                  value={String(opportunity.stage_id)}
                  onValueChange={(v) => handleAction(() => moveStage.mutateAsync({ opportunityId: opportunity.id, payload: { stage_id: Number(v) } }))}
                >
                  <SelectTrigger aria-label="Mover a etapa"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {openStages.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => handleAction(() => closeWon.mutateAsync(opportunity.id))}>Cerrar ganada</Button>
                </div>
                <div className="flex gap-2">
                  <Input
                    placeholder="Motivo de pérdida (opcional)"
                    value={lostReason}
                    onChange={(e) => setLostReason(e.target.value)}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleAction(() => closeLost.mutateAsync({ opportunityId: opportunity.id, payload: { lost_reason: lostReason || null } }))}
                  >
                    Cerrar perdida
                  </Button>
                </div>
              </div>
            )}

            {opportunity.status !== "open" && (
              <div className="flex flex-col gap-2 rounded-md border border-border p-3">
                <p className="text-sm text-muted-foreground">
                  {opportunity.status === "won" ? "Ganada" : `Perdida${opportunity.lost_reason ? ` — ${opportunity.lost_reason}` : ""}`}
                </p>
                <Button size="sm" variant="outline" onClick={() => handleAction(() => reopen.mutateAsync(opportunity.id))}>
                  Reabrir
                </Button>
              </div>
            )}

            <div className="flex flex-col gap-2">
              <Label_ text="Actividades" />
              {opportunityActivities.map((a) => (
                <div key={a.id} className="flex items-center justify-between rounded-md border border-border p-2 text-sm">
                  <div>
                    <p className="font-medium">{ACTIVITY_TYPE_LABELS[a.activity_type]} — {a.subject}</p>
                    {a.completed_at && <p className="text-xs text-muted-foreground">Completada</p>}
                  </div>
                  {!a.completed_at && (
                    <Button size="sm" variant="ghost" onClick={() => handleAction(() => completeActivity.mutateAsync(a.id))}>
                      Completar
                    </Button>
                  )}
                </div>
              ))}
              {opportunityActivities.length === 0 && <p className="text-xs text-muted-foreground">Sin actividades registradas.</p>}

              <div className="flex gap-2">
                <Select value={newActivityType} onValueChange={setNewActivityType}>
                  <SelectTrigger aria-label="Tipo de actividad" className="w-32"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(ACTIVITY_TYPE_LABELS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  placeholder="Asunto"
                  value={newActivitySubject}
                  onChange={(e) => setNewActivitySubject(e.target.value)}
                />
                <Button
                  size="sm"
                  disabled={!newActivitySubject}
                  onClick={() =>
                    handleAction(async () => {
                      await createActivity.mutateAsync({
                        contact_id: opportunity.contact_id,
                        opportunity_id: opportunity.id,
                        activity_type: newActivityType as "call" | "email" | "meeting" | "note" | "task",
                        subject: newActivitySubject,
                      });
                      setNewActivitySubject("");
                    })
                  }
                >
                  + Registrar
                </Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Label_({ text }: { text: string }) {
  return <p className="text-xs font-medium text-muted-foreground">{text}</p>;
}
