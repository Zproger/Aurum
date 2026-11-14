import { api } from "@/api/client";
import { appendAccountIds } from "@/hooks/useAccountFilter";
import type { DashboardSummary } from "@/types";

export function fetchDashboardSummary(year: number, month: number, accountIds?: number[]) {
  const params = appendAccountIds(new URLSearchParams({ year: String(year), month: String(month) }), accountIds);
  return api.get<DashboardSummary>(`/dashboard/summary?${params.toString()}`);
}
