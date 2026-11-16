import { api } from "@/api/client";
import type {
  CategoryKind,
  CategoryRankingReport,
  CategorySpendingReport,
  TagRankingReport,
  TagSpendingReport,
} from "@/types";

export function fetchCategorySpendingReport(categoryId: number, startDate?: string, endDate?: string) {
  const params = new URLSearchParams({ category_id: String(categoryId) });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  return api.get<CategorySpendingReport>(`/reports/category-spending?${params.toString()}`);
}

export function fetchCategoryRanking(kind: CategoryKind, startDate?: string, endDate?: string) {
  const params = new URLSearchParams({ kind });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  return api.get<CategoryRankingReport>(`/reports/category-ranking?${params.toString()}`);
}

// `kind` is a parameter on both tag endpoints rather than a property of the
// tag: a category is either an expense or an income one, but a tag can sit
// on both sides of the ledger, so the caller picks which side it's asking
// about (see backend/app/services/reports_service.py).
export function fetchTagRanking(kind: CategoryKind, startDate?: string, endDate?: string) {
  const params = new URLSearchParams({ kind });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  return api.get<TagRankingReport>(`/reports/tag-ranking?${params.toString()}`);
}

export function fetchTagSpendingReport(tagId: number, kind: CategoryKind, startDate?: string, endDate?: string) {
  const params = new URLSearchParams({ tag_id: String(tagId), kind });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  return api.get<TagSpendingReport>(`/reports/tag-spending?${params.toString()}`);
}
