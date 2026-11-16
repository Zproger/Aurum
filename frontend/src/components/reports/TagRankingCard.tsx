import { useState } from "react";
import { SquareDivide, Tag as TagIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { CategoryBreakdownModal } from "@/components/categories/CategoryBreakdownModal";
import { formatCurrency } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { TagRankingItem } from "@/types";

interface TagRankingCardProps {
  items: TagRankingItem[];
  isLoading: boolean;
  /** Everything spent in the period, tagged or not — the denominator behind
   * each row's percent, shown so the percentages are interpretable. */
  totalAmount: string | undefined;
  taggedAmount: string | undefined;
  selectedTagId: number | null;
  onSelectTag: (tagId: number) => void;
}

/** Ranks every tag by total spent over the selected period — "which trip,
 * which occasion, which person cost the most", the question the category
 * ranking can't answer because one such answer is spread across several
 * categories at once. Clicking a row drills into that tag in the chart and
 * transaction list.
 *
 * Deliberately unlike the category ranking in one way: the percentages
 * needn't sum to 100 and the rows may overlap, because one transaction can
 * carry several tags and each tag owns it whole. The coverage line in the
 * header is what keeps that honest — it says how much of the period carries
 * any tag at all. */
export function TagRankingCard({
  items,
  isLoading,
  totalAmount,
  taggedAmount,
  selectedTagId,
  onSelectTag,
}: TagRankingCardProps) {
  const { t } = useTranslation();
  const [breakdownItem, setBreakdownItem] = useState<TagRankingItem | null>(null);

  return (
    <Card>
      <CardHeader className="items-start">
        <div>
          <CardTitle>{t("reports.tagRankingTitle")}</CardTitle>
          {taggedAmount !== undefined && totalAmount !== undefined && (
            <p className="mt-1 text-xs text-text-muted">
              {t("reports.tagCoverage", {
                tagged: formatCurrency(taggedAmount),
                total: formatCurrency(totalAmount),
              })}
            </p>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
        ) : items.length === 0 ? (
          <p className="py-10 text-center text-sm text-text-muted">{t("reports.noTagRankingData")}</p>
        ) : (
          <ul className="divide-y divide-gridline">
            {items.map((item, index) => {
              const isSelected = item.tag_id === selectedTagId;
              // Shown even for a single-category tag, unlike the category
              // ranking's: a tag row names no category at all, so even a
              // one-row breakdown says something the row itself doesn't.
              const hasBreakdown = item.categories.length > 0;
              return (
                <li key={item.tag_id}>
                  <div
                    className={`flex items-center gap-1 rounded-lg transition-colors hover:bg-surface-2 ${
                      isSelected ? "bg-surface-2" : ""
                    }`}
                  >
                    {/* Fixed-width slot on every row, populated or not — the
                        amount column at the row's end must stay flush right
                        the same way whether or not this row has a
                        breakdown to open. */}
                    <span className="ml-1 flex h-8 w-7 shrink-0 items-center justify-center">
                      {hasBreakdown && (
                        <button
                          type="button"
                          aria-label={t("common.expand")}
                          onClick={() => setBreakdownItem(item)}
                          className="rounded-md p-1.5 text-text-muted hover:text-text-primary"
                        >
                          <SquareDivide size={14} />
                        </button>
                      )}
                    </span>
                    <button
                      type="button"
                      onClick={() => onSelectTag(item.tag_id)}
                      className="flex flex-1 items-center gap-3 py-2.5 text-left"
                    >
                      <span className="w-4 shrink-0 text-right text-xs tabular-nums text-text-muted">{index + 1}</span>
                      <span
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                        style={{ backgroundColor: `${item.color}26` }}
                      >
                        <TagIcon size={15} style={{ color: item.color }} />
                      </span>
                      {/* A tag name is whatever the user typed — shown
                          verbatim, never run through the default-category
                          translations. */}
                      <span className="min-w-0 flex-1 truncate text-sm text-text-primary">{item.name}</span>
                      <span className="hidden w-24 shrink-0 items-center gap-2 sm:flex">
                        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                          <span
                            className="block h-full rounded-full"
                            style={{ width: `${Math.min(item.percent, 100)}%`, backgroundColor: item.color }}
                          />
                        </span>
                        <span className="w-9 shrink-0 text-right text-xs text-text-muted tabular-nums">
                          {item.percent.toFixed(0)}%
                        </span>
                      </span>
                      <span className="shrink-0 text-sm font-medium tabular-nums text-text-primary">
                        {formatCurrency(item.amount)}
                      </span>
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>

      {breakdownItem && (
        <CategoryBreakdownModal
          open
          onClose={() => setBreakdownItem(null)}
          title={breakdownItem.name}
          categoryName={breakdownItem.name}
          totalAmount={breakdownItem.amount}
          children={breakdownItem.categories}
        />
      )}
    </Card>
  );
}
