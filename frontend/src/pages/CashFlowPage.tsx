import { useState } from "react";
import { AccountFilter, AccountFilterNotice } from "@/components/layout/AccountFilter";
import { useAccountFilter } from "@/hooks/useAccountFilter";
import { PillSelector } from "@/components/layout/PillSelector";
import { YearRangeSelector } from "@/components/layout/YearSelector";
import { CashFlowChart } from "@/components/cashflow/CashFlowChart";
import { useCashFlow } from "@/hooks/useCashFlow";
import { useTransactionYears } from "@/hooks/useTransactions";
import { computeRange, type CustomYearRange, type RangePreset } from "@/lib/dateRange";
import { useTranslation } from "@/lib/i18n";
import { queryDisplayState } from "@/lib/queryDisplayState";

export function CashFlowPage() {
  const { t } = useTranslation();
  const now = new Date();
  const { data: years } = useTransactionYears();
  const { accountIds } = useAccountFilter();
  const [range, setRange] = useState<RangePreset>("this_year");
  const [customRange, setCustomRange] = useState<CustomYearRange>({
    fromYear: now.getFullYear(),
    toYear: now.getFullYear(),
  });

  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "this_year", label: t("reports.rangeThisYear") },
    { value: "5y", label: t("reports.range5y") },
    { value: "custom", label: t("reports.rangeCustom") },
  ];

  const { startDate, endDate } = computeRange(range, customRange);
  const { data: cashFlow, isLoading, isError } = useCashFlow(startDate, endDate, accountIds);
  const displayState = queryDisplayState(cashFlow !== undefined, isLoading, isError);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <AccountFilter />
        <PillSelector options={RANGE_OPTIONS} value={range} onChange={setRange} />
        {range === "custom" && (
          <YearRangeSelector
            years={years ?? [now.getFullYear()]}
            fromYear={customRange.fromYear}
            toYear={customRange.toYear}
            onChange={setCustomRange}
          />
        )}
      </div>

      {displayState === "stale" && (
        <p className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning" role="status">
          {t("cashFlow.stale")}
        </p>
      )}

      <AccountFilterNotice />

      <CashFlowChart cashFlow={cashFlow} state={displayState} />
    </div>
  );
}
