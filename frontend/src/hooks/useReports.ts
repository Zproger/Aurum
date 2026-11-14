import { useQuery } from "@tanstack/react-query";
import { fetchCategoryRanking, fetchCategorySpendingReport } from "@/api/reports";
import type { CategoryKind } from "@/types";

export function useCategorySpendingReport(categoryId: number | null, startDate?: string, endDate?: string, accountIds?: number[]) {
  return useQuery({
    queryKey: ["category-spending-report", categoryId, startDate, endDate, accountIds ?? "all"],
    queryFn: () => fetchCategorySpendingReport(categoryId as number, startDate, endDate, accountIds),
    enabled: categoryId !== null,
  });
}

export function useCategoryRanking(kind: CategoryKind, startDate?: string, endDate?: string, accountIds?: number[]) {
  return useQuery({
    queryKey: ["category-ranking", kind, startDate, endDate, accountIds ?? "all"],
    queryFn: () => fetchCategoryRanking(kind, startDate, endDate, accountIds),
  });
}
