import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatCurrency, getIntlLocale, pluralizeRu } from "@/lib/format";
import { useTranslation, type Language } from "@/lib/i18n";
import type { CategorySpendingPoint } from "@/types";

interface SpendingTrendChartProps {
  /** Already resolved for display — a category name goes through
   * translateCategoryName before it gets here, a tag name is shown as the
   * user typed it. Undefined while the report is still loading. */
  title: string | undefined;
  color: string;
  totalAmount: string | undefined;
  averagePerMonth: string | undefined;
  transactionCount: number | undefined;
  series: CategorySpendingPoint[] | undefined;
  isLoading: boolean;
}

function monthKey(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

function formatMonthLabel(key: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { month: "short", year: "numeric" }).format(
    new Date(`${key}T00:00:00`)
  );
}

function transactionsCountLabel(count: number, language: Language): string {
  if (language === "ru") return pluralizeRu(count, "транзакция", "транзакции", "транзакций");
  return count === 1 ? "transaction" : "transactions";
}

/** Same landmark idea as the Net Worth chart: year ticks only when the bars
 * span more than one calendar year, so a 5-year report reads at a glance. */
function computeYearTicks(keys: string[]): string[] {
  if (keys.length < 2) return [];
  const startYear = Number(keys[0].slice(0, 4));
  const endYear = Number(keys[keys.length - 1].slice(0, 4));
  if (startYear === endYear) return [];
  const ticks: string[] = [];
  for (let year = startYear + 1; year <= endYear; year++) {
    const jan = `${year}-01-01`;
    if (keys.includes(jan)) ticks.push(jan);
  }
  return ticks;
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: { key: string; amount: number } }> }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-surface-1 px-3 py-2 text-sm shadow-md">
      <p className="text-text-muted">{formatMonthLabel(point.key)}</p>
      <p className="font-medium text-text-primary">{formatCurrency(point.amount)}</p>
    </div>
  );
}

/** One subject's month-by-month spending, as bars with a headline total —
 * the presentational half of the Reports detail chart, taking a plain
 * already-resolved shape rather than a report object so the category
 * (CategorySpendingChart) and tag (TagSpendingChart) sides render
 * identically instead of growing two drifting copies of this. */
export function SpendingTrendChart({
  title,
  color,
  totalAmount,
  averagePerMonth,
  transactionCount,
  series,
  isLoading,
}: SpendingTrendChartProps) {
  const { t, language } = useTranslation();
  const chartData =
    series?.map((point) => ({
      key: monthKey(point.year, point.month),
      amount: Number(point.amount),
    })) ?? [];
  const yearTicks = computeYearTicks(chartData.map((point) => point.key));
  const hasReport = totalAmount !== undefined;

  return (
    <Card>
      <CardHeader className="items-start">
        <div>
          <CardTitle>{title ?? t("reports.defaultChartTitle")}</CardTitle>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums text-text-primary sm:text-[28px]">
            {isLoading || !hasReport ? "…" : formatCurrency(totalAmount)}
          </p>
          {hasReport && averagePerMonth !== undefined && transactionCount !== undefined && (
            <p className="mt-1 text-sm text-text-muted">
              {t("reports.averagePerMonth", { amount: formatCurrency(averagePerMonth) })} ·{" "}
              {transactionCount} {transactionsCountLabel(transactionCount, language)}
            </p>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-56 w-full sm:h-64">
          {isLoading || !hasReport || chartData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-text-muted">
              {isLoading ? t("common.loading") : t("reports.noDataForPeriod")}
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
                {yearTicks.length > 0 && (
                  <XAxis
                    dataKey="key"
                    type="category"
                    ticks={yearTicks}
                    tickFormatter={(value: string) => value.slice(0, 4)}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                    interval="preserveStartEnd"
                  />
                )}
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--surface-2)" }} />
                <Bar dataKey="amount" fill={color} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        {chartData.length > 1 && (
          <div className="mt-2 flex justify-between text-xs text-text-muted">
            <span>{formatMonthLabel(chartData[0].key)}</span>
            <span>{formatMonthLabel(chartData[chartData.length - 1].key)}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
