import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useEmployee, useTerminateEmployee, usePositions } from "@/hooks/use-hr";
import { ApiError } from "@/lib/api-client";

const STATUS_LABELS: Record<string, string> = { active: "Activo", terminated: "Dado de baja" };

export function EmployeeDetailDialog({ employeeId, onOpenChange }: { employeeId: number | null; onOpenChange: (open: boolean) => void }) {
  const { data: employee, isLoading, error } = useEmployee(employeeId);
  const { data: positions } = usePositions();
  const terminateEmployee = useTerminateEmployee();
  const [actionError, setActionError] = useState<string | null>(null);
  const [terminationDate, setTerminationDate] = useState("");

  const positionTitle = (id: number | null) => {
    if (id === null) return "Sin puesto";
    return positions?.find((p) => p.id === id)?.title ?? `#${id}`;
  };

  const handleTerminate = async () => {
    if (!employee || !terminationDate) return;
    setActionError(null);
    try {
      await terminateEmployee.mutateAsync({ employeeId: employee.id, payload: { termination_date: terminationDate } });
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "No se pudo dar de baja al empleado");
    }
  };

  return (
    <Dialog open={employeeId !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{employee ? `${employee.first_name} ${employee.last_name}` : "Empleado"}</DialogTitle>
          <DialogDescription>
            {employee ? `${STATUS_LABELS[employee.status]} — ${positionTitle(employee.position_id)}` : ""}
          </DialogDescription>
        </DialogHeader>

        {isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {error instanceof ApiError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error.message}</p>}

        {employee && (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-muted-foreground">Contratación</p>
                <p className="font-medium">{employee.hire_date}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Salario</p>
                <p className="font-medium">{employee.salary ?? "No visible con tu permiso actual"}</p>
              </div>
              {employee.termination_date && (
                <div>
                  <p className="text-muted-foreground">Fecha de baja</p>
                  <p className="font-medium">{employee.termination_date}</p>
                </div>
              )}
            </div>

            {actionError && <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{actionError}</p>}

            {employee.status === "active" && (
              <div className="flex flex-col gap-2 rounded-md border border-border p-3">
                <Label htmlFor="termination_date">Dar de baja</Label>
                <div className="flex gap-2">
                  <Input
                    id="termination_date"
                    type="date"
                    value={terminationDate}
                    onChange={(e) => setTerminationDate(e.target.value)}
                  />
                  <Button size="sm" variant="outline" disabled={!terminationDate} onClick={handleTerminate}>
                    Dar de baja
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
