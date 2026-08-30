import { useMemo, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { useQuotes } from "@/hooks/use-sales";
import { useContacts } from "@/hooks/use-contacts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CreateQuoteDialog } from "@/components/CreateQuoteDialog";
import { QuoteDetailDialog } from "@/components/QuoteDetailDialog";
import { ApiError } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";

type QuoteRead = components["schemas"]["QuoteRead"];

const STATUS_LABELS: Record<string, string> = {
  draft: "Borrador",
  sent: "Enviada",
  accepted: "Aceptada",
  expired: "Vencida",
  cancelled: "Cancelada",
  converted: "Convertida",
};

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  sent: "bg-secondary text-secondary-foreground",
  accepted: "bg-secondary text-secondary-foreground",
  expired: "bg-destructive/10 text-destructive",
  cancelled: "bg-destructive/10 text-destructive",
  converted: "bg-muted text-muted-foreground",
};

export function QuotesPage() {
  const { data, isLoading, error } = useQuotes();
  const { data: contacts } = useContacts("");
  const rows = useMemo(() => data ?? [], [data]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const customerName = (id: number) => contacts?.find((c) => c.id === id)?.name ?? `#${id}`;

  const columns: ColumnDef<QuoteRead>[] = [
    { accessorKey: "number", header: "Número" },
    { id: "customer", header: "Cliente", cell: ({ row }) => customerName(row.original.customer_id) },
    {
      accessorKey: "status",
      header: "Estado",
      cell: ({ getValue }) => (
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[getValue<string>()]}`}>
          {STATUS_LABELS[getValue<string>()]}
        </span>
      ),
    },
    { accessorKey: "valid_until", header: "Válida hasta" },
  ];

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Cotizaciones</h1>
          <p className="text-sm text-muted-foreground">Borrador → Enviada → Aceptada → Convertida.</p>
        </div>
        <CreateQuoteDialog />
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}
      {!isLoading && !error && rows.length === 0 && <p className="text-sm text-muted-foreground">Todavía no hay cotizaciones.</p>}

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

      <QuoteDetailDialog quoteId={selectedId} onOpenChange={(open) => !open && setSelectedId(null)} />
    </div>
  );
}
