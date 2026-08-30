import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useCreditDebitNote, usePostCreditDebitNote, useCancelCreditDebitNote } from "@/hooks/use-accounting";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = { draft: "Borrador", posted: "Contabilizada", cancelled: "Cancelada" };

export function CreditDebitNoteDetailDialog({ noteId, onOpenChange }: { noteId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data: note, isLoading, error } = useCreditDebitNote(noteId);
  const postNote = usePostCreditDebitNote();
  const cancelNote = useCancelCreditDebitNote();
  const [actionError, setActionError] = useState<string | null>(null);

  const handleAction = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "No se pudo completar la acción");
    }
  };

  return (
    <Dialog open={noteId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{note?.number ?? "Nota"}</DialogTitle>
          <DialogDescription>
            {note ? `${STATUS_LABELS[note.status]} — ${note.reason}` : ""}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}

        {note && (
          <div className="flex flex-col gap-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-1 font-medium">Descripción</th>
                  <th className="py-1 font-medium">Cant.</th>
                  <th className="py-1 font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {note.lines.map((line) => (
                  <tr key={line.id} className="border-b border-border">
                    <td className="py-1.5">{line.description}</td>
                    <td className="py-1.5">{line.quantity}</td>
                    <td className="py-1.5">{line.line_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="flex justify-end gap-6 text-sm">
              <div className="text-right">
                <p className="text-muted-foreground">Subtotal</p>
                <p className="font-medium">{note.subtotal}</p>
              </div>
              <div className="text-right">
                <p className="text-muted-foreground">Impuesto</p>
                <p className="font-medium">{note.tax_amount}</p>
              </div>
              <div className="text-right">
                <p className="text-muted-foreground">Total</p>
                <p className="font-medium">{note.total}</p>
              </div>
            </div>

            {actionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{actionError}</p>}

            {note.status === "draft" && (
              <div className="flex gap-2">
                <Button size="sm" onClick={() => handleAction(() => postNote.mutateAsync(note.id))}>Contabilizar</Button>
                <Button size="sm" variant="outline" onClick={() => handleAction(() => cancelNote.mutateAsync(note.id))}>Cancelar</Button>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
