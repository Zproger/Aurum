import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Label, Select } from "@/components/ui/Input";
import { PillSelector } from "@/components/layout/PillSelector";
import { YearRangeSelector } from "@/components/layout/YearSelector";
import { CategoryRankingCard } from "@/components/reports/CategoryRankingCard";
import { CategorySpendingChart } from "@/components/reports/CategorySpendingChart";
import { TagRankingCard } from "@/components/reports/TagRankingCard";
import { TagSpendingChart } from "@/components/reports/TagSpendingChart";
import { TransactionsTable } from "@/components/transactions/TransactionsTable";
import { TransactionFormModal } from "@/components/transactions/TransactionFormModal";
import { useCategories } from "@/hooks/useCategories";
import { useCategoryRanking, useCategorySpendingReport, useTagRanking, useTagSpendingReport } from "@/hooks/useReports";
import { useTags } from "@/hooks/useTags";
import { useDeleteTransaction, useTransactions, useTransactionYears } from "@/hooks/useTransactions";
import type { TransactionSort } from "@/api/transactions";
import { computeRange, type CustomYearRange, type RangePreset } from "@/lib/dateRange";
import { useTranslation } from "@/lib/i18n";
import { buildHierarchicalCategories, translateCategoryName } from "@/lib/categoryLabels";
import type { Transaction } from "@/types";

const PAGE_SIZE = 20;

/** Which axis the page is reporting along: down the categories ("what kind
 * of spend was this") or across the tags ("which event/project was it for").
 * The two answer genuinely different questions over the same transactions —
 * see backend/app/models/tag.py — so they're modes of one page rather than
 * two pages. */
type ReportMode = "category" | "tag";

export function ReportsPage() {
  const { t, language } = useTranslation();
  const now = new Date();
  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "this_year", label: t("reports.rangeThisYear") },
    { value: "5y", label: t("reports.range5y") },
    { value: "custom", label: t("reports.rangeCustom") },
  ];
  const MODE_OPTIONS: Array<{ value: ReportMode; label: string }> = [
    { value: "category", label: t("reports.modeCategory") },
    { value: "tag", label: t("reports.modeTag") },
  ];
  const { data: categories } = useCategories();
  const { data: tags } = useTags();
  const { data: years } = useTransactionYears();
  const [mode, setMode] = useState<ReportMode>("category");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [tagId, setTagId] = useState<number | null>(null);
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

  // A tag deleted elsewhere (Transactions page) would otherwise leave the
  // detail chart asking the API for an id that no longer resolves.
  useEffect(() => {
    if (tagId !== null && tags && !tags.some((tag) => tag.id === tagId)) setTagId(null);
  }, [tags, tagId]);

  const { startDate, endDate } = computeRange(range, customRange);
  const isTagMode = mode === "tag";
  const { data: ranking, isLoading: isRankingLoading } = useCategoryRanking("expense", startDate, endDate);
  const { data: tagRanking, isLoading: isTagRankingLoading } = useTagRanking("expense", startDate, endDate);
  const { data: report, isLoading: isReportLoading } = useCategorySpendingReport(categoryId, startDate, endDate);
  const { data: tagReport, isLoading: isTagReportLoading } = useTagSpendingReport(
    isTagMode ? tagId : null,
    "expense",
    startDate,
    endDate
  );
  const { data: transactions, isLoading: isTransactionsLoading } = useTransactions({
    category_id: isTagMode ? undefined : categoryId ?? undefined,
    tag_id: isTagMode ? tagId ?? undefined : undefined,
    start_date: startDate,
    end_date: endDate,
    sort,
    page,
    page_size: PAGE_SIZE,
  });
  const deleteTransaction = useDeleteTransaction();

  // The ranking is ordered by amount, so its first row is the tag worth
  // looking at first — a better landing selection than whichever tag
  // happens to sort first alphabetically in the picker.
  useEffect(() => {
    if (isTagMode && tagId === null && tagRanking && tagRanking.items.length > 0) {
      setTagId(tagRanking.items[0].tag_id);
    }
  }, [isTagMode, tagId, tagRanking]);

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
  const selectedTagColor = tagRanking?.items.find((item) => item.tag_id === tagId)?.color;

  function handleModeChange(value: ReportMode) {
    setMode(value);
    setPage(1);
  }

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
          {isTagMode ? (
            <>
              <Label htmlFor="report-tag">{t("reports.tagLabel")}</Label>
              <Select
                id="report-tag"
                value={tagId ?? ""}
                disabled={!tags || tags.length === 0}
                onChange={(event) => {
                  setTagId(event.target.value ? Number(event.target.value) : null);
                  setPage(1);
                }}
              >
                {(!tags || tags.length === 0) && <option value="">{t("reports.noTagsYet")}</option>}
                {tags?.map((tag) => (
                  <option key={tag.id} value={tag.id}>
                    {tag.name}
                  </option>
                ))}
              </Select>
            </>
          ) : (
            <>
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
            </>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <PillSelector options={MODE_OPTIONS} value={mode} onChange={handleModeChange} />
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

      {isTagMode ? (
        <>
          <TagSpendingChart report={tagReport} color={selectedTagColor} isLoading={isTagReportLoading} />
          <TagRankingCard
            items={tagRanking?.items ?? []}
            isLoading={isTagRankingLoading}
            totalAmount={tagRanking?.total_amount}
            taggedAmount={tagRanking?.tagged_amount}
            selectedTagId={tagId}
            onSelectTag={(id) => {
              setTagId(id);
              setPage(1);
            }}
          />
        </>
      ) : (
        <>
          <CategorySpendingChart report={report} isLoading={isReportLoading} />
          <CategoryRankingCard
            items={ranking?.items ?? []}
            isLoading={isRankingLoading}
            selectedCategoryId={categoryId}
            onSelectCategory={(id) => {
              setCategoryId(id);
              setPage(1);
            }}
          />
        </>
      )}

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
          {isTransactionsLoading ? (
            <p className="py-12 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
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
