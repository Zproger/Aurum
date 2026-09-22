import { Dialog } from "@/components/ui/Dialog";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import { translateCategoryName } from "@/lib/categoryLabels";

interface CategoryBreakdownChild {
  // Null only on the tag side: the share of a tag's total that had no
  // category at all (a transaction saved without one).
  category_id: number | null;
  name: string;
  color: string;
  icon: string | null;
  amount: string;
}

interface CategoryBreakdownModalProps {
  open: boolean;
  onClose: () => void;
  /** The parent category being broken down — the child row matching it is
   * the "no subcategory" share. Omitted by the tag ranking, where the rows
   * are categories and no one of them is the subject itself. */
  categoryId?: number;
  /** Shown as-is instead of `categoryName` run through the default-category
   * translations — used by the tag ranking, whose subject is a user-typed
   * tag name that must never be translated. */
  title?: string;
  categoryName: string;
  totalAmount: string;
  children: CategoryBreakdownChild[];
}

/** Shows how a total splits across the categories that fed it — a modal
 * rather than an inline expansion, since a subject with many parts (or many
 * split-across purchases) would otherwise push the Dashboard's donut/list
 * layout out of alignment as rows grow taller. Shared by the Dashboard
 * breakdown and the Reports category ranking, which expose the same shape
 * (see services/category_rollup.py's CategoryRollupChildItem), and by the
 * Reports tag ranking, whose rows are that tag's categories instead
 * (services/tag_rollup.py's TagRollupCategoryItem). */
export function CategoryBreakdownModal({
  open,
  onClose,
  categoryId,
  title,
  categoryName,
  totalAmount,
  children,
}: CategoryBreakdownModalProps) {
  const { t } = useTranslation();
  const total = Number(totalAmount);

  return (
    <Dialog open={open} onClose={onClose} title={title ?? translateCategoryName(categoryName)}>
      <div className="mb-3 flex items-center justify-between border-b border-gridline pb-3 text-sm">
        <span className="text-text-muted">{t("reports.categoryBreakdownTotalLabel")}</span>
        <span className="font-semibold tabular-nums text-text-primary">{formatCurrency(totalAmount)}</span>
      </div>
      <ul className="divide-y divide-gridline">
        {children.map((child) => {
          const Icon = getCategoryIcon(child.icon);
          const percent = total ? (Number(child.amount) / total) * 100 : 0;
          const label =
            child.category_id === null
              ? t("reports.noCategoryLabel")
              : child.category_id === categoryId
                ? t("reports.directSpendLabel")
                : translateCategoryName(child.name);
          return (
            <li key={child.category_id ?? "uncategorized"} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                style={{ backgroundColor: `${child.color}26` }}
              >
                <Icon size={15} style={{ color: child.color }} />
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-text-primary">{label}</span>
              <span className="w-9 shrink-0 text-right text-xs text-text-muted tabular-nums">
                {percent.toFixed(0)}%
              </span>
              <span className="shrink-0 text-sm font-medium tabular-nums text-text-primary">
                {formatCurrency(child.amount)}
              </span>
            </li>
          );
        })}
      </ul>
    </Dialog>
  );
}
