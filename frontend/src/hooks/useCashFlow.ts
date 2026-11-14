import { useQuery } from "@tanstack/react-query";
import { fetchCashFlow } from "@/api/cashFlow";

export function useCashFlow(startDate?: string, endDate?: string, accountIds?: number[]) {
  return useQuery({
    queryKey: ["cash-flow", startDate, endDate, accountIds ?? "all"],
    queryFn: () => fetchCashFlow(startDate, endDate, accountIds),
  });
}
