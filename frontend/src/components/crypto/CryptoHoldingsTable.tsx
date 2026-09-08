import { Bitcoin, Plus, Trash2 } from "lucide-react";
import { RiskLevelPicker } from "@/components/crypto/RiskLevelPicker";
import { formatCryptoAmount, maskAmount } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding, CryptoPortfolio, RiskLevel } from "@/types";

interface CryptoHoldingsTableProps {
  items: CryptoHolding[];
  hidden: boolean;
  onTrade: (holding: CryptoHolding) => void;
  onViewHistory: (holding: CryptoHolding) => void;
  onDelete: (holding: CryptoHolding) => void;
  onRiskChange: (holding: CryptoHolding, riskLevel: RiskLevel) => void;
  // Only passed while viewing the "All" tab — renders each row's portfolio
  // as a small colored badge under the coin name so it's still clear which
  // portfolio it belongs to. Omitted while a single portfolio is selected,
  // since every row would carry the same badge.
  portfoliosById?: Map<number, CryptoPortfolio>;
}

function PercentCell({ value }: { value: string | null }) {
  if (value === null) return <span className="text-text-muted">—</span>;
  const num = Number(value);
  const color = num > 0 ? "var(--success)" : num < 0 ? "var(--danger)" : "var(--text-muted)";
  return (
    <span className="tabular-nums" style={{ color }}>
      {num > 0 ? "+" : ""}
      {num.toFixed(2)}%
    </span>
  );
}

export function CryptoHoldingsTable({
  items,
  hidden,
  onTrade,
  onViewHistory,
  onDelete,
  onRiskChange,
  portfoliosById,
}: CryptoHoldingsTableProps) {
  const { t } = useTranslation();

  if (items.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("crypto.empty")}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[880px] text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-text-muted">
            <th className="py-2.5 pr-4 font-medium">{t("crypto.table.name")}</th>
            <th className="whitespace-nowrap py-2.5 pr-4 text-right font-medium">{t("crypto.table.price")}</th>
            <th className="whitespace-nowrap py-2.5 pr-4 text-right font-medium">{t("crypto.table.change1h")}</th>
            <th className="whitespace-nowrap py-2.5 pr-4 text-right font-medium">{t("crypto.table.change24h")}</th>
            <th className="whitespace-nowrap py-2.5 pr-4 text-right font-medium">{t("crypto.table.change7d")}</th>
            <th className="whitespace-nowrap py-2.5 pr-4 text-right font-medium">{t("crypto.table.holdings")}</th>
            <th className="whitespace-nowrap py-2.5 pr-4 text-right font-medium">{t("crypto.table.avgBuyPrice")}</th>
            <th className="whitespace-nowrap py-2.5 pr-4 text-right font-medium">{t("crypto.table.profitLoss")}</th>
            <th className="whitespace-nowrap py-2.5 pr-4 text-right font-medium">{t("crypto.table.risk")}</th>
            <th className="whitespace-nowrap py-2.5 pl-4 text-right font-medium">{t("crypto.table.actions")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gridline">
          {items.map((holding) => {
            const profitColor =
              holding.profit_loss === null
                ? undefined
                : Number(holding.profit_loss) > 0
                  ? "var(--success)"
                  : Number(holding.profit_loss) < 0
                    ? "var(--danger)"
                    : "var(--text-muted)";
            const sign = holding.profit_loss !== null && Number(holding.profit_loss) > 0 ? "+" : "";

            return (
              <tr
                key={holding.asset_id}
                onClick={() => onViewHistory(holding)}
                className="cursor-pointer hover:bg-surface-2"
              >
                <td className="py-3.5 pr-4 align-middle">
                  <div className="flex items-center gap-2.5">
                    {holding.thumb_url ? (
                      <img src={holding.thumb_url} alt="" className="h-7 w-7 shrink-0 rounded-full" />
                    ) : (
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-2">
                        <Bitcoin size={14} className="text-text-secondary" />
                      </span>
                    )}
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-text-primary" title={holding.name}>
                        {holding.name}
                      </span>
                      <span className="mt-0.5 flex items-center gap-1.5 text-xs text-text-muted">
                        <span className="shrink-0">{holding.symbol}</span>
                        {portfoliosById && (
                          <span
                            className="flex min-w-0 items-center gap-1"
                            title={portfoliosById.get(holding.portfolio_id)?.name}
                          >
                            <span
                              className="h-1.5 w-1.5 shrink-0 rounded-full"
                              style={{
                                backgroundColor: portfoliosById.get(holding.portfolio_id)?.color ?? "var(--text-muted)",
                              }}
                            />
                            <span className="truncate">{portfoliosById.get(holding.portfolio_id)?.name}</span>
                          </span>
                        )}
                      </span>
                    </span>
                  </div>
                </td>
                <td className="py-3.5 pr-4 text-right align-middle tabular-nums text-text-primary">
                  {holding.current_price !== null
                    ? maskAmount(formatCryptoAmount(holding.current_price), hidden)
                    : t("crypto.pendingPrice")}
                </td>
                <td className="py-3.5 pr-4 text-right align-middle">
                  <PercentCell value={holding.price_change_1h} />
                </td>
                <td className="py-3.5 pr-4 text-right align-middle">
                  <PercentCell value={holding.price_change_24h} />
                </td>
                <td className="py-3.5 pr-4 text-right align-middle">
                  <PercentCell value={holding.price_change_7d} />
                </td>
                <td className="py-3.5 pr-4 text-right align-middle">
                  <span className="block tabular-nums text-text-primary">
                    {holding.value !== null ? maskAmount(formatCryptoAmount(holding.value), hidden) : t("crypto.pendingPrice")}
                  </span>
                  <span className="mt-0.5 block text-xs tabular-nums text-text-muted">
                    {maskAmount(`${Number(holding.quantity)} ${holding.symbol}`, hidden)}
                  </span>
                </td>
                <td className="py-3.5 pr-4 text-right align-middle tabular-nums text-text-primary">
                  {holding.avg_buy_price !== null ? maskAmount(formatCryptoAmount(holding.avg_buy_price), hidden) : "—"}
                </td>
                <td className="py-3.5 pr-4 text-right align-middle">
                  {holding.profit_loss !== null && holding.profit_loss_percent !== null ? (
                    <>
                      <span className="block tabular-nums" style={{ color: profitColor }}>
                        {maskAmount(`${sign}${formatCryptoAmount(holding.profit_loss)}`, hidden)}
                      </span>
                      <span className="mt-0.5 block text-xs tabular-nums" style={{ color: profitColor }}>
                        {sign}
                        {holding.profit_loss_percent.toFixed(2)}%
                      </span>
                    </>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>
                <td className="py-3.5 pr-4 align-middle" onClick={(event) => event.stopPropagation()}>
                  <span className="flex justify-end">
                    <RiskLevelPicker value={holding.risk_level} onChange={(level) => onRiskChange(holding, level)} />
                  </span>
                </td>
                <td className="py-3.5 pl-4 align-middle">
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      aria-label={t("crypto.form.tradeButton")}
                      onClick={(event) => {
                        event.stopPropagation();
                        onTrade(holding);
                      }}
                      className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
                    >
                      <Plus size={15} />
                    </button>
                    <button
                      type="button"
                      aria-label={t("common.delete")}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDelete(holding);
                      }}
                      className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
