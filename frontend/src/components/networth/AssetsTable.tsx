import { Pencil, Trash2 } from "lucide-react";
import { getCategoryIcon } from "@/lib/icons";
import { formatCurrency, formatTransactionDate } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { Asset, CapitalRole } from "@/types";

const CLASS_ICONS: Record<Asset["asset_class"], string> = {
  investments: "trending-up",
  crypto: "bitcoin",
  real_estate: "building-2",
  vehicles: "car",
  precious_metals: "gem",
  other: "package",
};

const ROLE_COLORS: Record<CapitalRole, string> = {
  income: "var(--success)",
  neutral: "var(--text-muted)",
  drain: "var(--danger)",
};

interface AssetsTableProps {
  items: Asset[];
  onEdit: (asset: Asset) => void;
  onDelete: (asset: Asset) => void;
}

export function AssetsTable({ items, onEdit, onDelete }: AssetsTableProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("netWorth.assetsTable.empty")}</p>;
  }

  return (
    <ul className="divide-y divide-gridline">
      {items.map((asset) => {
        const Icon = getCategoryIcon(CLASS_ICONS[asset.asset_class]);
        const roleColor = ROLE_COLORS[asset.capital_role];
        const cashFlow = asset.monthly_cash_flow !== null ? Number(asset.monthly_cash_flow) : null;
        const currentValue = Number(asset.current_value);
        // Annual ROI only makes sense for money coming in against what was
        // paid for the asset — same formula as RoiCalculatorCard.
        const annualRoiPercent = cashFlow !== null && cashFlow > 0 && currentValue > 0 ? (cashFlow * 12) / currentValue * 100 : null;

        return (
          <li key={asset.id} className="flex items-center gap-3 py-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-2">
              <Icon size={16} className="text-text-secondary" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-text-primary">{asset.name}</span>
              <span className="flex items-center gap-1 truncate text-xs text-text-muted">
                {t(`netWorth.assetClass.${asset.asset_class}` as TranslationKey)} ·{" "}
                {t("netWorth.assetsTable.asOf", { date: formatTransactionDate(asset.as_of_date) })}
                <span className="inline-flex items-center gap-1" style={{ color: roleColor }}>
                  · <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: roleColor }} />
                  {t(`netWorth.capitalRole.${asset.capital_role}` as TranslationKey)}
                </span>
              </span>
            </span>
            <span className="shrink-0 text-right">
              <span className="block text-sm font-medium tabular-nums text-text-primary">
                {formatCurrency(asset.current_value, asset.currency)}
              </span>
              {asset.currency !== "USD" && <span className="block text-xs tabular-nums text-text-muted">{formatCurrency(asset.current_value_usd, "USD")}</span>}
              {cashFlow !== null && cashFlow !== 0 && (
                <span
                  className="block text-xs tabular-nums"
                  style={{ color: cashFlow > 0 ? "var(--success)" : "var(--danger)" }}
                >
                  {cashFlow > 0 ? "+" : ""}
                  {formatCurrency(cashFlow, asset.currency)}
                  {t("common.perMonth")}
                  {annualRoiPercent !== null && ` · ${t("netWorth.assetsTable.annualRoi", { percent: annualRoiPercent.toFixed(1) })}`}
                </span>
              )}
            </span>
            <span className="flex shrink-0 gap-1">
              <button
                type="button"
                aria-label={t("common.edit")}
                onClick={() => onEdit(asset)}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
              >
                <Pencil size={15} />
              </button>
              <button
                type="button"
                aria-label={t("common.delete")}
                onClick={() => onDelete(asset)}
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
