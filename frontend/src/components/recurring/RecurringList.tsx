import { ArrowLeftRight, CalendarCheck, Pencil, Trash2 } from "lucide-react";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency, getIntlLocale } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";
import type { RecurringTransaction } from "@/types";

interface RecurringListProps {
  items: RecurringTransaction[];
  onPost: (item: RecurringTransaction) => void;
  onEdit: (item: RecurringTransaction) => void;
  onDelete: (item: RecurringTransaction) => void;
  isPosting: boolean;
}

function formatDueDate(isoDate: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { day: "numeric", month: "short", year: "numeric" }).format(
    new Date(`${isoDate}T00:00:00`)
  );
}

export function RecurringList({ items, onPost, onEdit, onDelete, isPosting }: RecurringListProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("recurring.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((item) => {
        const isTransfer = item.type === "transfer";
        const isExpense = item.type === "expense";
        const Icon = isTransfer ? ArrowLeftRight : getCategoryIcon(item.category_icon);
        const color = isTransfer ? "var(--text-muted)" : item.category_color ?? "var(--text-muted)";

        return (
          <li key={item.id} className="flex items-center gap-3 py-3">
            <span
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
              style={{ backgroundColor: color.startsWith("#") ? `${color}26` : "var(--surface-2)" }}
            >
              <Icon size={16} style={{ color }} />
            </span>

            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-text-primary">{item.description}</span>
              <span className="flex flex-wrap items-center gap-x-1 truncate text-xs text-text-muted">
                <span>{t(`recurring.frequency.${item.frequency}` as TranslationKey)}</span>
                {item.category_name && <span>· {translateCategoryName(item.category_name)}</span>}
                <span style={{ color: item.is_due ? "var(--danger)" : "var(--text-muted)" }}>
                  ·{" "}
                  {item.is_due
                    ? item.days_until_due < 0
                      ? t("recurring.overdueDays", { days: Math.abs(item.days_until_due) })
                      : t("recurring.dueToday")
                    : t("recurring.dueInDays", { days: item.days_until_due, date: formatDueDate(item.next_due_date) })}
                </span>
              </span>
            </span>

            <span
              className={`shrink-0 text-sm font-medium tabular-nums ${
                isTransfer ? "text-text-muted" : isExpense ? "text-text-primary" : "text-success"
              }`}
            >
              {isTransfer ? "" : isExpense ? "-" : "+"}
              {formatCurrency(item.amount, item.currency)}
            </span>

            <span className="flex shrink-0 gap-1">
              <button
                type="button"
                aria-label={t("recurring.postLabel")}
                disabled={isPosting}
                onClick={() => onPost(item)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-success disabled:opacity-50"
              >
                <CalendarCheck size={15} />
              </button>
              <button
                type="button"
                aria-label={t("common.edit")}
                onClick={() => onEdit(item)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                <Pencil size={15} />
              </button>
              <button
                type="button"
                aria-label={t("common.delete")}
                onClick={() => onDelete(item)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
              >
                <Trash2 size={15} />
              </button>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
