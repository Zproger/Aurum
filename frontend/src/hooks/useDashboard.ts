import { useQuery } from "@tanstack/react-query";
import { fetchDashboardSummary } from "@/api/dashboard";

export function useDashboardSummary(year: number, month: number, accountIds?: number[]) {
  return useQuery({
    queryKey: ["dashboard-summary", year, month, accountIds ?? "all"],
    queryFn: () => fetchDashboardSummary(year, month, accountIds),
  });
}
