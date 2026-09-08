import { useState } from "react";
import { ArrowDown, ArrowUp, Eye, EyeOff } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { CryptoAllocationBody } from "@/components/crypto/CryptoAllocationBody";
import { CryptoHistoryChartBody } from "@/components/crypto/CryptoHistoryChartBody";
import { CryptoNetworkAllocationBody } from "@/components/crypto/CryptoNetworkAllocationBody";
import { CryptoRangeSelector } from "@/components/crypto/CryptoRangeSelector";
import { CryptoRiskAllocationBody } from "@/components/crypto/CryptoRiskAllocationBody";
import { PillSelector } from "@/components/layout/PillSelector";
import { formatCurrency, formatSignedCurrency, maskAmount } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHistoryResponse, CryptoHolding, CryptoRange } from "@/types";

type OverviewTab = "history" | "allocation" | "risk" | "networks";

interface CryptoOverviewCardProps {
  totalValue: number;
  history: CryptoHistoryResponse | undefined;
  isHistoryLoading: boolean;
  range: CryptoRange;
  onRangeChange: (range: CryptoRange) => void;
  holdings: CryptoHolding[];
  isHoldingsLoading: boolean;
  hidden: boolean;
  onToggleHidden: () => void;
}

/** One card, four tabs — "History" (the value-over-time chart),
 * "Allocation" (a donut broken down by coin), "Risk levels" (% of the
 * portfolio in each RiskLevel tier), and "Networks" (a donut broken down by
 * CryptoHolding.network) — same CoinMarketCap-style layout the user asked
 * for: switching views instead of stacking separate cards, so the tab keeps
 * its footprint on the page instead of growing it. The
 * total/eye toggle/change line stay in the shared header regardless of
 * which tab is active — only the content panel below switches. */
export function CryptoOverviewCard({
  totalValue,
  history,
  isHistoryLoading,
  range,
  onRangeChange,
  holdings,
  isHoldingsLoading,
  hidden,
  onToggleHidden,
}: CryptoOverviewCardProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<OverviewTab>("history");

  const isPositive = history ? Number(history.change_amount) >= 0 : true;
  const trendColor = isPositive ? "var(--success)" : "var(--danger)";

  return (
    <Card>
      <CardHeader className="flex-col items-stretch gap-3 sm:flex-row sm:items-start">
        <div>
          <CardTitle>{t("nav.crypto")}</CardTitle>
          <p className="mt-1.5 flex items-center gap-2 text-2xl font-semibold tabular-nums text-text-primary sm:text-[28px]">
            {maskAmount(formatCurrency(totalValue), hidden)}
            <button
              type="button"
              aria-label={hidden ? t("crypto.chart.show") : t("crypto.chart.hide")}
              onClick={onToggleHidden}
              className="text-text-muted hover:text-text-primary"
            >
              {hidden ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </p>
          {history && (
            <p className="mt-1 flex items-center gap-1 text-sm font-medium" style={{ color: trendColor }}>
              {isPositive ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
              {maskAmount(formatSignedCurrency(history.change_amount), hidden)}
              {history.change_percent !== null && ` (${isPositive ? "+" : ""}${history.change_percent.toFixed(1)}%)`}
              <span className="font-normal text-text-muted">{t("netWorth.periodSuffix")}</span>
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <PillSelector
            options={[
              { value: "history" as const, label: t("crypto.overview.history") },
              { value: "allocation" as const, label: t("crypto.overview.allocation") },
              { value: "risk" as const, label: t("crypto.overview.risk") },
              { value: "networks" as const, label: t("crypto.overview.networks") },
            ]}
            value={tab}
            onChange={setTab}
          />
          {tab === "history" && <CryptoRangeSelector value={range} onChange={onRangeChange} />}
        </div>
      </CardHeader>
      <CardContent>
        {tab === "history" ? (
          <CryptoHistoryChartBody history={history} isLoading={isHistoryLoading} hidden={hidden} />
        ) : tab === "allocation" ? (
          <CryptoAllocationBody holdings={holdings} isLoading={isHoldingsLoading} hidden={hidden} />
        ) : tab === "risk" ? (
          <CryptoRiskAllocationBody holdings={holdings} isLoading={isHoldingsLoading} hidden={hidden} />
        ) : (
          <CryptoNetworkAllocationBody holdings={holdings} isLoading={isHoldingsLoading} hidden={hidden} />
        )}
      </CardContent>
    </Card>
  );
}
