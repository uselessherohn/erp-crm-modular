import { useMemo, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { useDepartments, usePositions, useEmployees } from "@/hooks/use-hr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CreateDepartmentDialog } from "@/components/CreateDepartmentDialog";
import { CreatePositionDialog } from "@/components/CreatePositionDialog";
import { CreateEmployeeDialog } from "@/components/CreateEmployeeDialog";
import { EmployeeDetailDialog } from "@/components/EmployeeDetailDialog";
import { ApiError } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";

type EmployeeRead = components["schemas"]["EmployeeRead"];

const STATUS_LABELS: Record<string, string> = { active: "Activo", terminated: "Dado de baja" };
const STATUS_STYLES: Record<string, string> = {
  active: "bg-secondary text-secondary-foreground",
  terminated: "bg-destructive/10 text-destructive",
};

export function EmployeesPage() {
  const { data: departments, isLoading: loadingDepts, error: deptsError } = useDepartments();
  const { data: positions } = usePositions();
  const { data: employees, isLoading: loadingEmployees, error: employeesError } = useEmployees();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const rows = useMemo(() => employees ?? [], [employees]);
  const positionTitle = (id: number | null) => {
    if (id === null) return "—";
    return positions?.find((p) => p.id === id)?.title ?? `#${id}`;
  };

  const columns: ColumnDef<EmployeeRead>[] = [
    { id: "name", header: "Nombre", cell: ({ row }) => `${row.original.first_name} ${row.original.last_name}` },
    { id: "position", header: "Puesto", cell: ({ row }) => positionTitle(row.original.position_id) },
    { accessorKey: "hire_date", header: "Contratación" },
    {
      accessorKey: "status",
      header: "Estado",
      cell: ({ getValue }) => (
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[getValue<string>()]}`}>
          {STATUS_LABELS[getValue<string>()]}
        </span>
      ),
    },
    {
      accessorKey: "salary",
      header: "Salario",
      cell: ({ getValue }) => {
        const value = getValue<string | null>();
        return value ?? <span className="text-xs text-muted-foreground">No visible</span>;
      },
    },
  ];

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Recursos Humanos</h1>
        <p className="text-sm text-muted-foreground">
          Legajo, estructura organizacional y jerarquías. El salario solo es visible con el permiso "ver datos sensibles".
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Departamentos</CardTitle>
          <CreateDepartmentDialog />
        </CardHeader>
        <CardContent>
          {loadingDepts && <p className="text-sm text-muted-foreground">Cargando…</p>}
          {deptsError instanceof ApiError && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{deptsError.message}</p>
          )}
          {!loadingDepts && !deptsError && (departments?.length ?? 0) === 0 && (
            <p className="text-sm text-muted-foreground">Todavía no hay departamentos.</p>
          )}
          {(departments?.length ?? 0) > 0 && (
            <ul className="flex flex-wrap gap-2 text-sm">
              {departments?.map((d) => (
                <li key={d.id} className="rounded-full bg-muted px-3 py-1">{d.name}</li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Puestos</CardTitle>
          <CreatePositionDialog />
        </CardHeader>
        <CardContent>
          {(positions?.length ?? 0) === 0 && <p className="text-sm text-muted-foreground">Todavía no hay puestos.</p>}
          {(positions?.length ?? 0) > 0 && (
            <ul className="flex flex-wrap gap-2 text-sm">
              {positions?.map((p) => {
                const dept = departments?.find((d) => d.id === p.department_id);
                return (
                  <li key={p.id} className="rounded-full bg-muted px-3 py-1">
                    {p.title}{dept ? ` — ${dept.name}` : ""}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Legajos</CardTitle>
          <CreateEmployeeDialog />
        </CardHeader>
        <CardContent>
          {loadingEmployees && <p className="text-sm text-muted-foreground">Cargando…</p>}
          {employeesError instanceof ApiError && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{employeesError.message}</p>
          )}
          {!loadingEmployees && !employeesError && rows.length === 0 && (
            <p className="text-sm text-muted-foreground">Todavía no hay empleados.</p>
          )}
          {rows.length > 0 && (
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
        </CardContent>
      </Card>

      <EmployeeDetailDialog employeeId={selectedId} onOpenChange={(open) => !open && setSelectedId(null)} />
    </div>
  );
}
