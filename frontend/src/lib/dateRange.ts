import { toIsoDate } from "@/lib/format";

/** Shared by CashFlowPage and ReportsPage — both offer the same four
 * period presets over their respective date-ranged endpoints. */
export type RangePreset = "all" | "this_year" | "5y" | "custom";

export interface CustomYearRange {
  fromYear: number;
  toYear: number;
}

export function computeRange(
  preset: RangePreset,
  custom?: CustomYearRange
): { startDate?: string; endDate?: string } {
  const today = new Date();
  switch (preset) {
    case "all":
      return {};
    case "this_year":
      return { startDate: `${today.getFullYear()}-01-01`, endDate: toIsoDate(today) };
    case "5y": {
      const start = new Date(today.getFullYear() - 5, today.getMonth(), 1);
      return { startDate: toIsoDate(start), endDate: toIsoDate(today) };
    }
    case "custom": {
      if (!custom) return {};
      return { startDate: `${custom.fromYear}-01-01`, endDate: `${custom.toYear}-12-31` };
    }
  }
}
