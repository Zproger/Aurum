import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Label, Select } from "@/components/ui/Input";
import { AccountFilter, AccountFilterNotice } from "@/components/layout/AccountFilter";
import { PillSelector } from "@/components/layout/PillSelector";
import { YearRangeSelector } from "@/components/layout/YearSelector";
import { CategoryRankingCard } from "@/components/reports/CategoryRankingCard";
import { CategorySpendingChart } from "@/components/reports/CategorySpendingChart";
import { TransactionsTable } from "@/components/transactions/TransactionsTable";
import { TransactionFormModal } from "@/components/transactions/TransactionFormModal";
import { useAccountFilter } from "@/hooks/useAccountFilter";
import { useCategories } from "@/hooks/useCategories";
import { useCategoryRanking, useCategorySpendingReport } from "@/hooks/useReports";
import { useDeleteTransaction, useTransactions, useTransactionYears } from "@/hooks/useTransactions";
import type { TransactionSort } from "@/api/transactions";
import { computeRange, type CustomYearRange, type RangePreset } from "@/lib/dateRange";
import { QueryStateNotice } from "@/components/ui/QueryStateNotice";
import { useTranslation } from "@/lib/i18n";
import { queryDisplayState, type QueryDisplayState } from "@/lib/queryDisplayState";
import { buildHierarchicalCategories, translateCategoryName } from "@/lib/categoryLabels";
import type { Transaction } from "@/types";

const PAGE_SIZE = 20;

/** Worst state of several queries feeding one block: any failure without data wins over stale. */
function combineStates(...states: QueryDisplayState[]): QueryDisplayState {
  if (states.includes("unavailable")) return "unavailable";
  if (states.includes("stale")) return "stale";
  return "ready";
}

export function ReportsPage() {
  const { t, language, currency } = useTranslation();
  const now = new Date();
  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "this_year", label: t("reports.rangeThisYear") },
    { value: "5y", label: t("reports.range5y") },
    { value: "custom", label: t("reports.rangeCustom") },
  ];
  const { data: categories } = useCategories();
  const { data: years } = useTransactionYears();
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [range, setRange] = useState<RangePreset>("all");
  const [customRange, setCustomRange] = useState<CustomYearRange>({
    fromYear: now.getFullYear(),
    toYear: now.getFullYear(),
  });
  const [sort, setSort] = useState<TransactionSort>("date_desc");
  const [page, setPage] = useState(1);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    if (categoryId === null && categories && categories.length > 0) {
      const firstExpense = categories.find((category) => category.kind === "expense");
      setCategoryId((firstExpense ?? categories[0]).id);
    }
  }, [categories, categoryId]);

  const { startDate, endDate } = computeRange(range, customRange);
  const { accountIds } = useAccountFilter();
  const { data: ranking, isLoading: isRankingLoading, isError: isRankingError } = useCategoryRanking("expense", startDate, endDate, accountIds);
  const { data: report, isLoading: isReportLoading, isError: isReportError } = useCategorySpendingReport(categoryId, startDate, endDate, accountIds);
  const { data: transactions, isLoading: isTransactionsLoading, isError: isTransactionsError } = useTransactions({
    category_id: categoryId ?? undefined,
    account_ids: accountIds,
    start_date: startDate,
    end_date: endDate,
    sort,
    page,
    page_size: PAGE_SIZE,
  });
  const reportState = queryDisplayState(report !== undefined, isReportLoading, isReportError);
  const rankingState = queryDisplayState(ranking !== undefined, isRankingLoading, isRankingError);
  const transactionsState = queryDisplayState(transactions !== undefined, isTransactionsLoading, isTransactionsError);
  const deleteTransaction = useDeleteTransaction();

  // Hierarchical within each group (a subcategory right under its own
  // parent, indented) — a bare "Sweets" option next to top-level categories
  // reads as if it were one itself.
  const expenseCategories = buildHierarchicalCategories(
    categories?.filter((category) => category.kind === "expense") ?? [],
    language
  );
  const incomeCategories = buildHierarchicalCategories(
    categories?.filter((category) => category.kind === "income") ?? [],
    language
  );
  const totalPages = transactions ? Math.max(1, Math.ceil(transactions.total / PAGE_SIZE)) : 1;

  function handleEdit(transaction: Transaction) {
    setEditingTransaction(transaction);
    setModalOpen(true);
  }

  function handleDelete(transaction: Transaction) {
    if (window.confirm(t("transactions.confirmDelete", { description: transaction.description }))) {
      deleteTransaction.mutate(transaction.id);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-xs flex-1">
          <Label htmlFor="report-category">{t("reports.categoryLabel")}</Label>
          <Select
            id="report-category"
            value={categoryId ?? ""}
            onChange={(event) => {
              setCategoryId(Number(event.target.value));
              setPage(1);
            }}
          >
            {expenseCategories.length > 0 && (
              <optgroup label={t("reports.expenseGroup")}>
                {expenseCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.indented ? `    ↳ ` : ""}
                    {translateCategoryName(category.name)}
                  </option>
                ))}
              </optgroup>
            )}
            {incomeCategories.length > 0 && (
              <optgroup label={t("reports.incomeGroup")}>
                {incomeCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.indented ? `    ↳ ` : ""}
                    {translateCategoryName(category.name)}
                  </option>
                ))}
              </optgroup>
            )}
          </Select>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <AccountFilter />
          <PillSelector
            options={RANGE_OPTIONS}
            value={range}
            onChange={(value) => {
              setRange(value);
              setPage(1);
            }}
          />
          {range === "custom" && (
            <YearRangeSelector
              years={years ?? [now.getFullYear()]}
              fromYear={customRange.fromYear}
              toYear={customRange.toYear}
              onChange={(value) => {
                setCustomRange(value);
                setPage(1);
              }}
            />
          )}
        </div>
      </div>

      <AccountFilterNotice />

      <QueryStateNotice
        state={combineStates(reportState, rankingState)}
        unavailableText={t("reports.unavailable")}
        staleText={t("reports.stale")}
      />

      <CategorySpendingChart report={report} isLoading={isReportLoading} unavailable={reportState === "unavailable"} />

      <CategoryRankingCard
        items={ranking?.items ?? []}
        currency={ranking?.reporting_currency ?? currency}
        incomplete={ranking?.incomplete ?? false}
        isLoading={isRankingLoading}
        unavailable={rankingState === "unavailable"}
        selectedCategoryId={categoryId}
        onSelectCategory={(id) => {
          setCategoryId(id);
          setPage(1);
        }}
      />

      <Card>
        <CardHeader>
          <CardTitle>{t("reports.transactionsTitle")}</CardTitle>
          {transactions && (
            <span className="text-xs text-text-muted">{t("common.totalCount", { count: transactions.total })}</span>
          )}
        </CardHeader>
        <CardContent>
          <Select
            value={sort}
            onChange={(event) => {
              setSort(event.target.value as TransactionSort);
              setPage(1);
            }}
            className="mb-3 sm:w-56"
          >
            <option value="date_desc">{t("transactions.sortDateDesc")}</option>
            <option value="amount_desc">{t("transactions.sortAmountDesc")}</option>
            <option value="amount_asc">{t("transactions.sortAmountAsc")}</option>
          </Select>
          <QueryStateNotice
            state={transactionsState}
            unavailableText={t("transactions.unavailable")}
            staleText={t("transactions.stale")}
            className="mb-3"
          />
          {transactionsState === "loading" ? (
            <p className="py-12 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : transactionsState === "unavailable" ? null : (
            <TransactionsTable items={transactions?.items ?? []} onEdit={handleEdit} onDelete={handleDelete} />
          )}

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3 text-sm">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                {t("common.back")}
              </Button>
              <span className="text-text-muted">{t("common.pageOf", { page, total: totalPages })}</span>
              <Button variant="secondary" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                {t("common.next")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <TransactionFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        transaction={editingTransaction}
      />
    </div>
  );
}
