import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useUser } from "@/hooks/use-core-data";
import { ApiError } from "@/lib/api-client";

export function UserDetailDialog({ userId, onOpenChange }: { userId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data, isLoading, error } = useUser(userId);

  return (
    <Dialog open={userId !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Detalle de usuario</DialogTitle>
          <DialogDescription>Información completa del registro.</DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}

        {error instanceof ApiError && (
          <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error.message}
          </p>
        )}

        {data && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">Nombre</dt>
            <dd>{data.full_name}</dd>
            <dt className="text-muted-foreground">Correo</dt>
            <dd>{data.email}</dd>
            <dt className="text-muted-foreground">Estado</dt>
            <dd>{data.is_active ? "Activo" : "Inactivo"}</dd>
            <dt className="text-muted-foreground">Creado</dt>
            <dd>{new Date(data.created_at).toLocaleString("es-HN")}</dd>
            <dt className="text-muted-foreground">Actualizado</dt>
            <dd>{new Date(data.updated_at).toLocaleString("es-HN")}</dd>
          </dl>
        )}
      </DialogContent>
    </Dialog>
  );
}
