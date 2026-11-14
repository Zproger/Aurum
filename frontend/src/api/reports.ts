import { api } from "@/api/client";
import { appendAccountIds } from "@/hooks/useAccountFilter";
import type { CategoryKind, CategoryRankingReport, CategorySpendingReport } from "@/types";

export function fetchCategorySpendingReport(categoryId: number, startDate?: string, endDate?: string, accountIds?: number[]) {
  const params = new URLSearchParams({ category_id: String(categoryId) });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  appendAccountIds(params, accountIds);
  return api.get<CategorySpendingReport>(`/reports/category-spending?${params.toString()}`);
}

export function fetchCategoryRanking(kind: CategoryKind, startDate?: string, endDate?: string, accountIds?: number[]) {
  const params = new URLSearchParams({ kind });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  appendAccountIds(params, accountIds);
  return api.get<CategoryRankingReport>(`/reports/category-ranking?${params.toString()}`);
}
