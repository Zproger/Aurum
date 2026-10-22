import { useQuery } from "@tanstack/react-query";
import {
  fetchCategoryRanking,
  fetchCategorySpendingReport,
  fetchTagRanking,
  fetchTagSpendingReport,
} from "@/api/reports";
import type { CategoryKind } from "@/types";

export function useCategorySpendingReport(categoryId: number | null, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ["category-spending-report", categoryId, startDate, endDate],
    queryFn: () => fetchCategorySpendingReport(categoryId as number, startDate, endDate),
    enabled: categoryId !== null,
  });
}

export function useCategoryRanking(kind: CategoryKind, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ["category-ranking", kind, startDate, endDate],
    queryFn: () => fetchCategoryRanking(kind, startDate, endDate),
  });
}

export function useTagRanking(kind: CategoryKind, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ["tag-ranking", kind, startDate, endDate],
    queryFn: () => fetchTagRanking(kind, startDate, endDate),
  });
}

export function useTagSpendingReport(
  tagId: number | null,
  kind: CategoryKind,
  startDate?: string,
  endDate?: string
) {
  return useQuery({
    queryKey: ["tag-spending-report", tagId, kind, startDate, endDate],
    queryFn: () => fetchTagSpendingReport(tagId as number, kind, startDate, endDate),
    enabled: tagId !== null,
  });
}
