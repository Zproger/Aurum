import { useState } from "react";
import { AccountFilter, AccountFilterNotice } from "@/components/layout/AccountFilter";
import { useAccountFilter } from "@/hooks/useAccountFilter";
import { MonthSelector } from "@/components/layout/MonthSelector";
import { YearSelector } from "@/components/layout/YearSelector";
import { StatCard } from "@/components/dashboard/StatCard";
import { SpendingByCategoryCard } from "@/components/dashboard/SpendingByCategoryCard";
import { TotalBalanceCard } from "@/components/dashboard/TotalBalanceCard";
import { RecentTransactionsCard } from "@/components/dashboard/RecentTransactionsCard";
import { AlertBanner } from "@/components/insights/AlertBanner";
import { Page, PageHeader } from "@/components/ui/Page";
import { useDashboardSummary } from "@/hooks/useDashboard";
import { useTransactionYears } from "@/hooks/useTransactions";
import { formatReportingAmount, formatSignedReportingAmount } from "@/lib/format";
import { ReportingCurrencyNote } from "@/components/ui/ReportingCurrencyNote";
import { useTranslation } from "@/lib/i18n";
import { queryDisplayState } from "@/lib/queryDisplayState";

/** Share of income left over after spending (net / real_income). `null` when
 * there was no income to take a share of, rather than a misleading 0%. */
function savingsRate(realIncome: number, net: number): number | null {
  return realIncome > 0 ? (net / realIncome) * 100 : null;
}

function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(0)}%`;
}

export function DashboardPage() {
  const { t, language, currency } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const { data: years } = useTransactionYears();
  const { accountIds } = useAccountFilter();

  const { data, isLoading, isError, dataUpdatedAt } = useDashboardSummary(year, month, accountIds);
  const displayState = queryDisplayState(data !== undefined, isLoading, isError);
  const unavailable = displayState === "unavailable";
  const pending = displayState === "loading" || unavailable;
  // The month figures are in the currency the backend reports them in — the
  // settings value is only a fallback while the first response is loading.
  const reportingCurrency = data?.reporting_currency ?? currency;
  const rate =
    data && data.real_income !== null && data.net !== null
      ? savingsRate(Number(data.real_income), Number(data.net))
      : null;
  const lastUpdated = dataUpdatedAt > 0
    ? new Intl.DateTimeFormat(language === "ru" ? "ru-RU" : "en-US", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(dataUpdatedAt)
    : "—";

  return (
    <Page>
      <PageHeader
        title={t("nav.dashboard")}
        actions={
          <div className="flex w-full min-w-0 items-center gap-2 sm:w-auto">
            <div className="min-w-0 flex-1 sm:max-w-xl">
              <MonthSelector month={month} onChange={setMonth} />
            </div>
            <YearSelector years={years ?? [now.getFullYear()]} year={year} onChange={setYear} />
            <AccountFilter />
          </div>
        }
      />

      <AlertBanner excludeKeys={["risky_allocation_exceeded"]} />
      <AccountFilterNotice />

      {unavailable && (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {t("dashboard.errorLoading")}
        </p>
      )}
      {displayState === "stale" && (
        <p className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning" role="status">
          {t("dashboard.staleData", { time: lastUpdated })}
        </p>
      )}

      <TotalBalanceCard balance={data?.balance} state={displayState} />

      <div className="grid grid-cols-1 gap-3 min-[375px]:grid-cols-2 sm:gap-4 lg:grid-cols-4">
        <StatCard
          label={t("dashboard.statRealIncomeLabel")}
          value={pending ? (unavailable ? "—" : "…") : formatReportingAmount(data!.real_income, reportingCurrency)}
          caption={t("dashboard.statRealIncomeCaption")}
          tone="success"
        />
        <StatCard
          label={t("dashboard.statSpentLabel")}
          value={pending ? (unavailable ? "—" : "…") : formatReportingAmount(data!.spent, reportingCurrency)}
          caption={t("dashboard.statSpentCaption")}
          tone="danger"
        />
        <StatCard
          label={t("dashboard.statNetLabel")}
          value={pending ? (unavailable ? "—" : "…") : formatSignedReportingAmount(data!.net, reportingCurrency)}
          caption={t("dashboard.statNetCaption")}
          tone={!data || data.net === null ? "default" : Number(data.net) >= 0 ? "success" : "danger"}
        />
        <StatCard
          label={t("dashboard.statSavingsRateLabel")}
          value={pending ? (unavailable ? "—" : "…") : rate === null ? "—" : formatPercent(rate)}
          caption={t("dashboard.statSavingsRateCaption")}
          tone={rate === null ? "default" : rate >= 0 ? "success" : "danger"}
        />
      </div>

      {data && <ReportingCurrencyNote currency={data.reporting_currency} incomplete={data.incomplete} className="-mt-1" />}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <SpendingByCategoryCard items={data?.spending_by_category} currency={reportingCurrency} state={displayState} />
        <RecentTransactionsCard year={year} month={month} accountIds={accountIds} />
      </div>
    </Page>
  );
}
