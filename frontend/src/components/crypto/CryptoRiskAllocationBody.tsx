import { formatCurrency, maskAmount } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { CryptoHolding, RiskLevel } from "@/types";

interface CryptoRiskAllocationBodyProps {
  holdings: CryptoHolding[];
  isLoading: boolean;
  hidden: boolean;
}

// Same status-color convention as NetWorthPage's own RiskAllocationCard
// (low reads as "good", high as "critical") — not a categorical hue, so
// hardcoded here rather than threaded through from the backend.
const TIER_COLOR: Record<RiskLevel, string> = {
  low: "var(--success)",
  medium: "var(--text-muted)",
  high: "var(--danger)",
};
const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high"];

/** The "Risk levels" tab's content inside CryptoOverviewCard — same
 * three-tier layout as NetWorthPage's own RiskAllocationCard, but scoped to
 * crypto holdings only (not the whole net worth), so "am I overweight on
 * memecoins" doesn't get diluted by cash/real estate/etc. Entirely
 * client-side: every holding already carries value + risk_level from
 * GET /crypto/holdings, no separate endpoint needed. */
export function CryptoRiskAllocationBody({ holdings, isLoading, hidden }: CryptoRiskAllocationBodyProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>;
  }
  if (holdings.length === 0) {
    return <p className="py-10 text-center text-sm text-text-muted">{t("crypto.empty")}</p>;
  }

  // Unpriced holdings (CoinGecko never successfully priced them yet) can't
  // contribute a % of portfolio value — same "best data on hand" principle
  // the rest of the Crypto tab already follows for a null value/price.
  const priced = holdings.filter((h) => h.value !== null);
  const totalValue = priced.reduce((sum, h) => sum + Number(h.value), 0);

  const tiers = RISK_LEVELS.map((level) => {
    const items = priced
      .filter((h) => h.risk_level === level)
      .map((h) => ({ symbol: h.symbol, name: h.name, value: Number(h.value) }))
      .sort((a, b) => b.value - a.value);
    const tierValue = items.reduce((sum, item) => sum + item.value, 0);
    return {
      level,
      value: tierValue,
      percent: totalValue > 0 ? (tierValue / totalValue) * 100 : 0,
      items: items.map((item) => ({
        ...item,
        percent: tierValue > 0 ? (item.value / tierValue) * 100 : 0,
      })),
    };
  });

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {tiers.map((tier) => (
        <div key={tier.level} className="rounded-lg border border-border p-3.5">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: TIER_COLOR[tier.level] }} />
            {t(`netWorth.riskLevel.${tier.level}` as TranslationKey)}
          </p>
          <p className="mt-1.5 text-xl font-semibold tabular-nums text-text-primary">
            {maskAmount(formatCurrency(tier.value), hidden)}
          </p>
          <p className="mt-1 text-xs text-text-muted">
            {tier.percent.toFixed(1)}% {t("crypto.riskAllocationOfPortfolio")}
          </p>

          {tier.items.length > 0 && (
            <ul className="mt-3 space-y-1.5 border-t border-gridline pt-3">
              {tier.items.map((item) => (
                <li key={item.symbol} className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">{item.symbol}</span>
                  <span className="h-1 w-10 shrink-0 overflow-hidden rounded-full bg-surface-2">
                    <span
                      className="block h-full rounded-full"
                      style={{ width: `${item.percent}%`, backgroundColor: TIER_COLOR[tier.level] }}
                    />
                  </span>
                  <span className="w-8 shrink-0 text-right text-[11px] tabular-nums text-text-muted">
                    {item.percent.toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
