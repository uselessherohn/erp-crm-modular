import { useMemo, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { useCreditDebitNotes } from "@/hooks/use-accounting";
import { useContacts } from "@/hooks/use-contacts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CreateCreditDebitNoteDialog } from "@/components/CreateCreditDebitNoteDialog";
import { CreditDebitNoteDetailDialog } from "@/components/CreditDebitNoteDetailDialog";
import { ApiError } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";

type CreditDebitNoteRead = components["schemas"]["CreditDebitNoteRead"];

const STATUS_LABELS: Record<string, string> = { draft: "Borrador", posted: "Contabilizada", cancelled: "Cancelada" };
const STATUS_STYLES: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  posted: "bg-secondary text-secondary-foreground",
  cancelled: "bg-destructive/10 text-destructive",
};
const NOTE_TYPE_LABELS: Record<string, string> = { credit: "Nota de crédito", debit: "Nota de débito" };
const DIRECTION_LABELS: Record<string, string> = { sale: "Venta", purchase: "Proveedor" };

export function CreditDebitNotesPage() {
  const { data, isLoading, error } = useCreditDebitNotes();
  const { data: contacts } = useContacts("");
  const rows = useMemo(() => data ?? [], [data]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const contactName = (id: number) => contacts?.find((c) => c.id === id)?.name ?? `#${id}`;

  const columns: ColumnDef<CreditDebitNoteRead>[] = [
    { accessorKey: "number", header: "Número" },
    { id: "note_type", header: "Tipo", cell: ({ row }) => NOTE_TYPE_LABELS[row.original.note_type] },
    { id: "direction", header: "Origen", cell: ({ row }) => DIRECTION_LABELS[row.original.direction] },
    { id: "contact", header: "Contacto", cell: ({ row }) => contactName(row.original.contact_id) },
    {
      accessorKey: "status",
      header: "Estado",
      cell: ({ getValue }) => (
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[getValue<string>()]}`}>
          {STATUS_LABELS[getValue<string>()]}
        </span>
      ),
    },
    { accessorKey: "total", header: "Total" },
  ];

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Notas de crédito y débito</h1>
          <p className="text-sm text-muted-foreground">Reversan o cargan sobre una factura ya contabilizada. Borrador → Contabilizada.</p>
        </div>
        <CreateCreditDebitNoteDialog />
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}
      {!isLoading && !error && rows.length === 0 && <p className="text-sm text-muted-foreground">Todavía no hay notas.</p>}

      {!isLoading && !error && rows.length > 0 && (
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => <TableHead key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</TableHead>)}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id} className="cursor-pointer" onClick={() => setSelectedId(row.original.id)}>
                {row.getVisibleCells().map((cell) => <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <CreditDebitNoteDetailDialog noteId={selectedId} onOpenChange={(open) => !open && setSelectedId(null)} />
    </div>
  );
}
