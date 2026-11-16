import { SpendingTrendChart } from "@/components/reports/SpendingTrendChart";
import { NEUTRAL_TAG_COLOR } from "@/lib/tagColors";
import type { TagSpendingReport } from "@/types";

interface TagSpendingChartProps {
  report: TagSpendingReport | undefined;
  /** Borrowed from the tag's own ranking row (the color of the category it
   * spends the most on) so the chart and the ranking bar agree — a tag has
   * no color of its own. */
  color: string | undefined;
  isLoading: boolean;
}

/** One tag's spend month by month — "what has this trip / these gifts cost
 * me over time", the question the category chart can't answer because one
 * such answer cuts across several categories. A tag name is shown exactly
 * as the user typed it, so unlike the category chart it never goes through
 * the default-name translations. */
export function TagSpendingChart({ report, color, isLoading }: TagSpendingChartProps) {
  return (
    <SpendingTrendChart
      title={report?.tag_name}
      color={color ?? NEUTRAL_TAG_COLOR}
      totalAmount={report?.total_amount}
      averagePerMonth={report?.average_per_month}
      transactionCount={report?.transaction_count}
      series={report?.series}
      isLoading={isLoading}
    />
  );
}
