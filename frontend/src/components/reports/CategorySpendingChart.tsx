import { SpendingTrendChart } from "@/components/reports/SpendingTrendChart";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { CategorySpendingReport } from "@/types";

interface CategorySpendingChartProps {
  report: CategorySpendingReport | undefined;
  isLoading: boolean;
}

/** One category's spend month by month. The drawing itself lives in
 * SpendingTrendChart, shared with the tag side — this only maps the report
 * onto it and resolves the category's name through the default-category
 * translations. */
export function CategorySpendingChart({ report, isLoading }: CategorySpendingChartProps) {
  return (
    <SpendingTrendChart
      title={report ? translateCategoryName(report.category_name) : undefined}
      color={report?.category_color ?? "#898781"}
      totalAmount={report?.total_amount}
      averagePerMonth={report?.average_per_month}
      transactionCount={report?.transaction_count}
      series={report?.series}
      isLoading={isLoading}
    />
  );
}
