import { useMemo, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { useUsers } from "@/hooks/use-core-data";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CreateUserDialog } from "@/components/CreateUserDialog";
import { UserDetailDialog } from "@/components/UserDetailDialog";
import { ApiError } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";

type UserRead = components["schemas"]["UserRead"];

const columns: ColumnDef<UserRead>[] = [
  { accessorKey: "full_name", header: "Nombre" },
  { accessorKey: "email", header: "Correo" },
  {
    accessorKey: "is_active",
    header: "Estado",
    cell: ({ getValue }) => (
      <span
        className={
          getValue<boolean>()
            ? "rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground"
            : "rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
        }
      >
        {getValue<boolean>() ? "Activo" : "Inactivo"}
      </span>
    ),
  },
  {
    accessorKey: "created_at",
    header: "Creado",
    cell: ({ getValue }) => new Date(getValue<string>()).toLocaleDateString("es-HN"),
  },
];

export function UsersPage() {
  const { data, isLoading, error } = useUsers();
  const rows = useMemo(() => data ?? [], [data]);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Usuarios</h1>
          <p className="text-sm text-muted-foreground">Personas con acceso al sistema en tu empresa.</p>
        </div>
        <CreateUserDialog />
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}

      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.code === "PERMISSION_DENIED"
            ? "No tenés permiso para ver esta lista."
            : error.message}
        </p>
      )}

      {!isLoading && !error && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">Todavía no hay usuarios además de vos.</p>
      )}

      {!isLoading && !error && rows.length > 0 && (
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow
                key={row.id}
                className="cursor-pointer"
                onClick={() => setSelectedUserId(row.original.id)}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <UserDetailDialog userId={selectedUserId} onOpenChange={(open) => !open && setSelectedUserId(null)} />
    </div>
  );
}
