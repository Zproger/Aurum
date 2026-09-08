import { useMemo, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { CryptoAddModal } from "@/components/crypto/CryptoAddModal";
import { CryptoHoldingsTable } from "@/components/crypto/CryptoHoldingsTable";
import { CryptoOverviewCard } from "@/components/crypto/CryptoOverviewCard";
import { CryptoPortfolioFormModal } from "@/components/crypto/CryptoPortfolioFormModal";
import { CryptoPortfolioTabs } from "@/components/crypto/CryptoPortfolioTabs";
import { CryptoStatsRow } from "@/components/crypto/CryptoStatsRow";
import { CryptoTransactionHistoryModal } from "@/components/crypto/CryptoTransactionHistoryModal";
import { CryptoTransactionModal } from "@/components/crypto/CryptoTransactionModal";
import {
  useCrypto90dPerformance,
  useCryptoHistory,
  useCryptoHoldings,
  useCryptoPortfolios,
  useDeleteCryptoHolding,
  useRefreshCryptoPrices,
  useUpdateCryptoHoldingRisk,
} from "@/hooks/useCrypto";
import { getIntlLocale } from "@/lib/format";
import { useTranslation } from "@/lib/i18n";
import type { CryptoHolding, CryptoPortfolio, CryptoRange, CryptoTransaction, RiskLevel } from "@/types";

function formatSyncedAt(iso: string): string {
  return new Intl.DateTimeFormat(getIntlLocale(), { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));
}

export function CryptoPage() {
  const { t } = useTranslation();
  // "all" by default — a 30-day window makes a portfolio that's actually
  // grown steadily for years look demotivating whenever it's mid-dip.
  const [range, setRange] = useState<CryptoRange>("all");
  // Single "hide balance" switch for the whole tab — owned here so every
  // money-displaying section (chart, stats, allocation, table, trade
  // history) masks together instead of the toggle only affecting whichever
  // component happened to own it.
  const [hidden, setHidden] = useState(false);
  // null = "All portfolios" tab.
  const [portfolioFilter, setPortfolioFilter] = useState<number | null>(null);
  const { data: portfolios } = useCryptoPortfolios();
  const { data, isLoading } = useCryptoHoldings(portfolioFilter);
  const { data: history, isLoading: isHistoryLoading } = useCryptoHistory(range, portfolioFilter);
  const { data: performance90d, isLoading: isPerformance90dLoading } = useCrypto90dPerformance(range, portfolioFilter);
  const refresh = useRefreshCryptoPrices();
  const deleteHolding = useDeleteCryptoHolding();
  const updateRisk = useUpdateCryptoHoldingRisk();

  const [addOpen, setAddOpen] = useState(false);
  const [editingPortfolio, setEditingPortfolio] = useState<CryptoPortfolio | null>(null);
  const [portfolioModalOpen, setPortfolioModalOpen] = useState(false);
  const [tradingHolding, setTradingHolding] = useState<CryptoHolding | null>(null);
  const [historyHolding, setHistoryHolding] = useState<CryptoHolding | null>(null);
  // Set together with tradingHolding when editing an entry from the history
  // list — CryptoTransactionModal is the same dialog for both "+" (new
  // trade, transaction stays null) and this (pre-filled, PATCHes instead of
  // POSTing). Cleared whenever that dialog closes, same as tradingHolding.
  const [editingTransaction, setEditingTransaction] = useState<CryptoTransaction | null>(null);

  const holdings = data?.holdings ?? [];
  const totalValue = holdings.reduce((sum, holding) => sum + (holding.value !== null ? Number(holding.value) : 0), 0);
  const portfoliosById = useMemo(() => new Map((portfolios ?? []).map((p) => [p.id, p])), [portfolios]);
  const performance90dByAsset = useMemo(
    () => new Map((performance90d?.items ?? []).map((item) => [item.asset_id, item.price_change_percent])),
    [performance90d]
  );

  function openAddPortfolioModal() {
    setEditingPortfolio(null);
    setPortfolioModalOpen(true);
  }

  function openEditPortfolioModal(portfolio: CryptoPortfolio) {
    setEditingPortfolio(portfolio);
    setPortfolioModalOpen(true);
  }

  function handleDelete(holding: CryptoHolding) {
    if (window.confirm(t("crypto.confirmDelete", { name: holding.name }))) {
      deleteHolding.mutate(holding.asset_id);
    }
  }

  function handleRiskChange(holding: CryptoHolding, riskLevel: RiskLevel) {
    updateRisk.mutate({ assetId: holding.asset_id, riskLevel });
  }

  function handleEditTransaction(transaction: CryptoTransaction) {
    setEditingTransaction(transaction);
    setTradingHolding(historyHolding);
    setHistoryHolding(null);
  }

  function closeTradeModal() {
    setTradingHolding(null);
    setEditingTransaction(null);
  }

  function openTradeModal(holding: CryptoHolding) {
    setEditingTransaction(null);
    setTradingHolding(holding);
  }

  return (
    <div className="space-y-5">
      <CryptoPortfolioTabs
        portfolios={portfolios ?? []}
        activeId={portfolioFilter}
        onChange={setPortfolioFilter}
        onAdd={openAddPortfolioModal}
        onEdit={openEditPortfolioModal}
      />

      <CryptoOverviewCard
        totalValue={totalValue}
        history={history}
        isHistoryLoading={isHistoryLoading}
        range={range}
        onRangeChange={setRange}
        holdings={holdings}
        isHoldingsLoading={isLoading}
        hidden={hidden}
        onToggleHidden={() => setHidden((prev) => !prev)}
      />

      <CryptoStatsRow
        holdings={holdings}
        isLoading={isLoading}
        hidden={hidden}
        range={range}
        performance90d={performance90dByAsset}
        isPerformance90dLoading={isPerformance90dLoading}
      />

      <Card>
        <CardHeader className="flex-col items-stretch gap-3 sm:flex-row sm:items-center">
          <div>
            <CardTitle>{t("crypto.holdingsTitle")}</CardTitle>
            <p className="mt-0.5 text-xs text-text-muted">
              {data?.last_synced_at
                ? t("crypto.lastSynced", { time: formatSyncedAt(data.last_synced_at) })
                : t("crypto.neverSynced")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <RefreshCw size={16} className={refresh.isPending ? "animate-spin" : undefined} />
              {refresh.isPending ? t("crypto.refreshing") : t("crypto.refreshButton")}
            </Button>
            <Button onClick={() => setAddOpen(true)}>
              <Plus size={16} />
              {t("crypto.addButton")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-10 text-center text-sm text-text-muted">{t("common.loading")}</p>
          ) : (
            <>
              {data?.error_key && <p className="mb-3 text-sm text-danger">{t(`crypto.syncError.${data.error_key}`)}</p>}
              <CryptoHoldingsTable
                items={holdings}
                hidden={hidden}
                onTrade={openTradeModal}
                onViewHistory={setHistoryHolding}
                onDelete={handleDelete}
                onRiskChange={handleRiskChange}
                portfoliosById={portfolioFilter === null ? portfoliosById : undefined}
              />
            </>
          )}
        </CardContent>
      </Card>

      <CryptoAddModal open={addOpen} onClose={() => setAddOpen(false)} defaultPortfolioId={portfolioFilter} />
      <CryptoPortfolioFormModal
        open={portfolioModalOpen}
        onClose={() => setPortfolioModalOpen(false)}
        portfolio={editingPortfolio}
        onDeleted={() => {
          if (editingPortfolio && portfolioFilter === editingPortfolio.id) setPortfolioFilter(null);
        }}
      />
      <CryptoTransactionModal
        open={tradingHolding !== null}
        onClose={closeTradeModal}
        holding={tradingHolding}
        transaction={editingTransaction}
      />
      <CryptoTransactionHistoryModal
        open={historyHolding !== null}
        onClose={() => setHistoryHolding(null)}
        holding={historyHolding}
        hidden={hidden}
        onEdit={handleEditTransaction}
      />
    </div>
  );
}
