import { useRoles } from "@/hooks/use-core-data";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { CreateRoleDialog } from "@/components/CreateRoleDialog";
import { ApiError } from "@/lib/api-client";

export function RolesPage() {
  const { data, isLoading, error } = useRoles();

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Roles</h1>
          <p className="text-sm text-muted-foreground">Conjuntos de permisos que se asignan a los usuarios.</p>
        </div>
        <CreateRoleDialog />
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}

      {error instanceof ApiError && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error.code === "PERMISSION_DENIED" ? "No tenés permiso para ver esta lista." : error.message}
        </p>
      )}

      {!isLoading && !error && (data?.length ?? 0) === 0 && (
        <p className="text-sm text-muted-foreground">Todavía no hay roles creados.</p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((role) => (
          <Card key={role.id}>
            <CardHeader>
              <CardTitle className="text-base">{role.name}</CardTitle>
              {role.description && <CardDescription>{role.description}</CardDescription>}
            </CardHeader>
            <CardContent>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {role.permissions?.length ?? 0} permiso{role.permissions?.length === 1 ? "" : "s"}
              </p>
              <ul className="mt-2 flex flex-wrap gap-1">
                {role.permissions?.map((p) => (
                  <li key={p.id} className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {p.code}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
