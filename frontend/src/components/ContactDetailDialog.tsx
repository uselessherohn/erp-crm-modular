import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useContact } from "@/hooks/use-contacts";
import { ApiError } from "@/lib/api-client";

const ROLE_LABELS: Record<string, string> = {
  is_customer: "Cliente",
  is_vendor: "Proveedor",
  is_patient: "Paciente",
  is_lead: "Prospecto",
};

export function ContactDetailDialog({ contactId, onOpenChange }: { contactId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data, isLoading, error } = useContact(contactId);

  const activeRoles = data
    ? Object.entries(ROLE_LABELS).filter(([key]) => (data as unknown as Record<string, boolean>)[key])
    : [];

  return (
    <Dialog open={contactId !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Detalle de contacto</DialogTitle>
          <DialogDescription>Información completa del registro.</DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}

        {error instanceof ApiError && (
          <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error.message}
          </p>
        )}

        {data && (
          <div className="flex flex-col gap-3 text-sm">
            <div>
              <p className="font-medium">{data.name}</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {activeRoles.map(([, label]) => (
                  <span key={label} className="rounded bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
                    {label}
                  </span>
                ))}
              </div>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
              <dt className="text-muted-foreground">Correo</dt>
              <dd>{data.email ?? "—"}</dd>
              <dt className="text-muted-foreground">Teléfono</dt>
              <dd>{data.phone ?? "—"}</dd>
              <dt className="text-muted-foreground">RTN</dt>
              <dd>{data.tax_id ?? "—"}</dd>
              <dt className="text-muted-foreground">Dirección</dt>
              <dd>{data.address ?? "—"}</dd>
            </dl>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
