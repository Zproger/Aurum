import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { categoryPath, translateCategoryName } from "@/lib/categoryLabels";
import { useTransactions } from "@/hooks/useTransactions";
import { useCategories } from "@/hooks/useCategories";
import { queryDisplayState } from "@/lib/queryDisplayState";

interface RecentTransactionsCardProps {
  year: number;
  month: number;
  /** Shared analytics account filter; undefined means every account. */
  accountIds?: number[];
}

export function RecentTransactionsCard({ year, month, accountIds }: RecentTransactionsCardProps) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useTransactions({ year, month, page: 1, page_size: 6, account_ids: accountIds });
  const state = queryDisplayState(data !== undefined, isLoading, isError);
  const { data: categories } = useCategories();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("dashboard.recentTransactionsTitle")}</CardTitle>
        <Link
          to={`/transactions?year=${year}&month=${month}`}
          className="inline-flex min-h-11 items-center rounded-md px-2 text-xs font-medium text-series-1 hover:bg-surface-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          {t("dashboard.allTransactionsLink")}
        </Link>
      </CardHeader>
      <CardContent>
        {state === "loading" ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : state === "unavailable" ? (
          <p className="py-10 text-center text-sm text-danger" role="alert">{t("dashboard.dataUnavailable")}</p>
        ) : !data?.items.length ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("dashboard.noTransactionsYet")}</p>
        ) : (
          <>
          {state === "stale" && <p className="mb-3 text-xs text-warning" role="status">{t("dashboard.staleList")}</p>}
          <ul className="divide-y divide-gridline">
            {data.items.map((tx) => {
              const isSplit = tx.splits.length > 0;
              const Icon = getCategoryIcon(tx.category?.icon);
              const isTransfer = tx.type === "transfer";
              const isExpense = tx.type === "expense";
              const color = tx.category?.color ?? "var(--text-muted)";
              const categoryLabel = isSplit
                ? tx.splits.map((split) => (split.category ? translateCategoryName(split.category.name) : "?")).join(" + ")
                : tx.category
                  ? categoryPath(tx.category, categories)
                  : null;
              return (
                <li key={tx.id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                  <span
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                    style={{ backgroundColor: `${color}26` }}
                  >
                    <Icon size={15} style={{ color }} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-text-primary">{tx.description}</span>
                    <span className="block truncate text-xs text-text-muted">
                      {formatTransactionDate(tx.date)} · {tx.account.name}
                      {categoryLabel ? ` · ${categoryLabel}` : ""}
                    </span>
                  </span>
                  <span
                    className={`shrink-0 text-sm font-medium tabular-nums ${
                      isTransfer ? "text-text-muted" : isExpense ? "text-text-primary" : "text-success"
                    }`}
                  >
                    {isTransfer ? "" : isExpense ? "-" : "+"}
                    {formatCurrency(tx.amount, tx.account.currency)}
                  </span>
                </li>
              );
            })}
          </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
