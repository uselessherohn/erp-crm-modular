import { useMemo, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { usePurchaseOrders } from "@/hooks/use-purchasing";
import { useContacts } from "@/hooks/use-contacts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CreatePurchaseOrderDialog } from "@/components/CreatePurchaseOrderDialog";
import { PurchaseOrderDetailDialog } from "@/components/PurchaseOrderDetailDialog";
import { ApiError } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";

type PurchaseOrderRead = components["schemas"]["PurchaseOrderRead"];

const STATUS_LABELS: Record<string, string> = {
  draft: "Borrador",
  confirmed: "Confirmada",
  received: "Recibida",
  closed: "Cerrada",
  cancelled: "Cancelada",
};

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  confirmed: "bg-secondary text-secondary-foreground",
  received: "bg-secondary text-secondary-foreground",
  closed: "bg-muted text-muted-foreground",
  cancelled: "bg-destructive/10 text-destructive",
};

export function PurchaseOrdersPage() {
  const { data, isLoading, error } = usePurchaseOrders();
  const { data: contacts } = useContacts("");
  const rows = useMemo(() => data ?? [], [data]);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const vendorName = (id: number) => contacts?.find((c) => c.id === id)?.name ?? `#${id}`;

  const columns: ColumnDef<PurchaseOrderRead>[] = [
    { accessorKey: "number", header: "Número" },
    { id: "vendor", header: "Proveedor", cell: ({ row }) => vendorName(row.original.vendor_id) },
    {
      accessorKey: "status",
      header: "Estado",
      cell: ({ getValue }) => (
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[getValue<string>()]}`}>
          {STATUS_LABELS[getValue<string>()]}
        </span>
      ),
    },
    { accessorKey: "currency_code", header: "Moneda" },
  ];

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Órdenes de compra</h1>
          <p className="text-sm text-muted-foreground">Draft → Confirmada → Recibida → Cerrada.</p>
        </div>
        <CreatePurchaseOrderDialog />
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}
      {!isLoading && !error && rows.length === 0 && <p className="text-sm text-muted-foreground">Todavía no hay órdenes de compra.</p>}

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

      <PurchaseOrderDetailDialog poId={selectedId} onOpenChange={(open) => !open && setSelectedId(null)} />
    </div>
  );
}
