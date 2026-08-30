import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, schemas } from "@/lib/api-client";
import type { components } from "@/lib/generated/api-types";
import type { z } from "zod";

type DepartmentRead = components["schemas"]["DepartmentRead"];
type PositionRead = components["schemas"]["PositionRead"];
type EmployeeRead = components["schemas"]["EmployeeRead"];

type DepartmentCreate = z.infer<typeof schemas.DepartmentCreate>;
type PositionCreate = z.infer<typeof schemas.PositionCreate>;
type EmployeeCreate = z.infer<typeof schemas.EmployeeCreate>;
type EmployeeTerminate = z.infer<typeof schemas.EmployeeTerminate>;

// ---------------------------------------------------------------------------
// Departments
// ---------------------------------------------------------------------------

export function useDepartments() {
  return useQuery({
    queryKey: ["hr", "departments"],
    queryFn: () => apiRequest<DepartmentRead[]>("/hr/departments", { responseSchema: schemas.DepartmentRead.array() }),
  });
}

export function useCreateDepartment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DepartmentCreate) =>
      apiRequest<DepartmentRead>("/hr/departments", { method: "POST", body: payload, responseSchema: schemas.DepartmentRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hr", "departments"] }),
  });
}

// ---------------------------------------------------------------------------
// Positions
// ---------------------------------------------------------------------------

export function usePositions() {
  return useQuery({
    queryKey: ["hr", "positions"],
    queryFn: () => apiRequest<PositionRead[]>("/hr/positions", { responseSchema: schemas.PositionRead.array() }),
  });
}

export function useCreatePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PositionCreate) =>
      apiRequest<PositionRead>("/hr/positions", { method: "POST", body: payload, responseSchema: schemas.PositionRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hr", "positions"] }),
  });
}

// ---------------------------------------------------------------------------
// Employees
// ---------------------------------------------------------------------------

export function useEmployees() {
  return useQuery({
    queryKey: ["hr", "employees"],
    queryFn: () => apiRequest<EmployeeRead[]>("/hr/employees", { responseSchema: schemas.EmployeeRead.array() }),
  });
}

export function useEmployee(id: number | null) {
  return useQuery({
    queryKey: ["hr", "employees", id],
    queryFn: () => apiRequest<EmployeeRead>(`/hr/employees/${id}`, { responseSchema: schemas.EmployeeRead }),
    enabled: id !== null,
  });
}

export function useCreateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EmployeeCreate) =>
      apiRequest<EmployeeRead>("/hr/employees", { method: "POST", body: payload, responseSchema: schemas.EmployeeRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hr", "employees"] }),
  });
}

export function useTerminateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ employeeId, payload }: { employeeId: number; payload: EmployeeTerminate }) =>
      apiRequest<EmployeeRead>(`/hr/employees/${employeeId}/terminate`, {
        method: "POST",
        body: payload,
        responseSchema: schemas.EmployeeRead,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hr", "employees"] }),
  });
}
