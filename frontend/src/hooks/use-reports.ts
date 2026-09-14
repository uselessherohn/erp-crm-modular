import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, apiDownloadFile } from "@/lib/api-client";
import {
  MetricInfo,
  MetricDataResult,
  DashboardRead,
  type DashboardCreate,
} from "@/lib/reports-temp-contract";

export function useMetrics() {
  return useQuery({
    queryKey: ["reports", "metrics"],
    queryFn: () => apiRequest<MetricInfo[]>("/reports/metrics", { responseSchema: MetricInfo.array() }),
  });
}

export function useMetricData(metricKey: string | null, dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ["reports", "metric-data", metricKey, dateFrom, dateTo],
    queryFn: () =>
      apiRequest<MetricDataResult>(`/reports/metrics/${metricKey}/data`, {
        query: { date_from: dateFrom, date_to: dateTo },
        responseSchema: MetricDataResult,
      }),
    enabled: Boolean(metricKey && dateFrom && dateTo),
  });
}

export function exportMetric(metricKey: string, dateFrom: string, dateTo: string, format: "csv" | "xlsx" | "pdf") {
  const path = `/reports/metrics/${metricKey}/export?date_from=${dateFrom}&date_to=${dateTo}&format=${format}`;
  return apiDownloadFile(path, `${metricKey}_${dateFrom}_${dateTo}.${format}`);
}

export function useDashboards() {
  return useQuery({
    queryKey: ["reports", "dashboards"],
    queryFn: () => apiRequest<DashboardRead[]>("/reports/dashboards", { responseSchema: DashboardRead.array() }),
  });
}

export function useCreateDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: DashboardCreate) =>
      apiRequest<DashboardRead>("/reports/dashboards", { method: "POST", body: payload, responseSchema: DashboardRead }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports", "dashboards"] }),
  });
}

export function useDeleteDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dashboardId: number) => apiRequest<void>(`/reports/dashboards/${dashboardId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports", "dashboards"] }),
  });
}
