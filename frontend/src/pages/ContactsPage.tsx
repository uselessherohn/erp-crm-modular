import { useMemo, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { Search } from "lucide-react";
import { useContacts } from "@/hooks/use-contacts";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { CreateContactDialog } from "@/components/CreateContactDialog";
import { ContactDetailDialog } from "@/components/ContactDetailDialog";
import { ApiError } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";

type ContactRead = components["schemas"]["ContactRead"];

function roleBadges(contact: ContactRead) {
  const roles: string[] = [];
  if (contact.is_customer) roles.push("Cliente");
  if (contact.is_vendor) roles.push("Proveedor");
  if (contact.is_patient) roles.push("Paciente");
  if (contact.is_lead) roles.push("Prospecto");
  return roles;
}

const columns: ColumnDef<ContactRead>[] = [
  { accessorKey: "name", header: "Nombre" },
  {
    id: "roles",
    header: "Rol",
    cell: ({ row }) => (
      <div className="flex flex-wrap gap-1">
        {roleBadges(row.original).map((r) => (
          <span key={r} className="rounded bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
            {r}
          </span>
        ))}
      </div>
    ),
  },
  { accessorKey: "phone", header: "Teléfono", cell: ({ getValue }) => getValue<string | null>() ?? "—" },
  { accessorKey: "email", header: "Correo", cell: ({ getValue }) => getValue<string | null>() ?? "—" },
];

export function ContactsPage() {
  const [searchInput, setSearchInput] = useState("");
  const search = useDebouncedValue(searchInput, 300);
  const { data, isLoading, error } = useContacts(search);
  const rows = useMemo(() => data ?? [], [data]);
  const [selectedContactId, setSelectedContactId] = useState<number | null>(null);

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Contactos</h1>
          <p className="text-sm text-muted-foreground">Clientes, proveedores, pacientes y prospectos.</p>
        </div>
        <CreateContactDialog />
      </div>

      <div className="relative mb-4 max-w-sm">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Buscar por nombre…"
          className="pl-9"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}

      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.code === "PERMISSION_DENIED" ? "No tenés permiso para ver esta lista." : error.message}
        </p>
      )}

      {!isLoading && !error && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {search ? "Sin resultados para esa búsqueda." : "Todavía no hay contactos."}
        </p>
      )}

      {!isLoading && !error && rows.length > 0 && (
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id} className="cursor-pointer" onClick={() => setSelectedContactId(row.original.id)}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <ContactDetailDialog contactId={selectedContactId} onOpenChange={(open) => !open && setSelectedContactId(null)} />
    </div>
  );
}
