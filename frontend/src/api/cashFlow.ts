import { api } from "@/api/client";
import { appendAccountIds } from "@/hooks/useAccountFilter";
import type { CashFlowResponse } from "@/types";

export function fetchCashFlow(startDate?: string, endDate?: string, accountIds?: number[]) {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  appendAccountIds(params, accountIds);
  const query = params.toString();
  return api.get<CashFlowResponse>(`/cash-flow${query ? `?${query}` : ""}`);
}
