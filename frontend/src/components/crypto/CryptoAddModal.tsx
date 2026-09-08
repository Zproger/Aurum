import { type FormEvent, useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import { searchCryptoCoins } from "@/api/crypto";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input, Label, Select } from "@/components/ui/Input";
import { useCreateCryptoHolding, useCryptoHoldings, useCryptoPortfolios } from "@/hooks/useCrypto";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import type { CryptoSearchResult, RiskLevel } from "@/types";

const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high"];

interface CryptoAddModalProps {
  open: boolean;
  onClose: () => void;
  // The portfolio tab active on the Crypto page when "+" was clicked — pre-
  // selects that portfolio here instead of always defaulting to the first
  // one. Null (the "All" tab) falls back to the first portfolio in the list.
  defaultPortfolioId?: number | null;
}

/** Two phases in one dialog: search CoinGecko for a coin, then pick one and
 * enter how much of it is held. No separate multi-step wizard — unlike CSV
 * import, there's nothing here worth a dedicated page for. */
export function CryptoAddModal({ open, onClose, defaultPortfolioId }: CryptoAddModalProps) {
  const { t } = useTranslation();
  const createHolding = useCreateCryptoHolding();
  const { data: portfolios } = useCryptoPortfolios();
  // Every portfolio's holdings, purely to build the network datalist below
  // (already-typed values like "Ethereum"/"Tron" as autocomplete, not a
  // fixed list — see CryptoHolding.network).
  const { data: allHoldings } = useCryptoHoldings();
  const knownNetworks = Array.from(
    new Set((allHoldings?.holdings ?? []).map((h) => h.network).filter((n): n is string => Boolean(n)))
  ).sort();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CryptoSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<CryptoSearchResult | null>(null);
  const [portfolioId, setPortfolioId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState("");
  const [pricePerUnit, setPricePerUnit] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  // Defaults to "high", same as the backend default — crypto is this app's
  // own textbook HIGH risk example — but overridable per coin here.
  const [riskLevel, setRiskLevel] = useState<RiskLevel>("high");
  const [network, setNetwork] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (open) return;
    setQuery("");
    setResults([]);
    setSelected(null);
    setQuantity("");
    setPricePerUnit("");
    setDate(new Date().toISOString().slice(0, 10));
    setRiskLevel("high");
    setNetwork("");
    setSearchError(null);
    setSaveError(null);
  }, [open]);

  // Re-picked every time the dialog opens or the portfolio list loads —
  // covers both "opened from a specific tab" and "opened from All before
  // any portfolio existed yet, then the default one got created".
  useEffect(() => {
    if (!open) return;
    if (defaultPortfolioId != null) {
      setPortfolioId(defaultPortfolioId);
    } else if (portfolios && portfolios.length > 0) {
      setPortfolioId((current) => (current !== null && portfolios.some((p) => p.id === current) ? current : portfolios[0].id));
    }
  }, [open, defaultPortfolioId, portfolios]);

  useEffect(() => {
    if (!open || selected) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      setSearchError(null);
      return;
    }
    setSearching(true);
    setSearchError(null);
    const timer = setTimeout(async () => {
      try {
        setResults(await searchCryptoCoins(trimmed));
      } catch (error) {
        setResults([]);
        setSearchError(
          error instanceof ApiError && error.status === 400 ? t("crypto.search.noApiKey") : t("crypto.form.saveError")
        );
      } finally {
        setSearching(false);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [query, open, selected, t]);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setSaveError(null);
    try {
      await createHolding.mutateAsync({
        portfolio_id: portfolioId,
        coingecko_id: selected.coingecko_id,
        symbol: selected.symbol,
        name: selected.name,
        thumb_url: selected.thumb_url,
        quantity,
        price_per_unit: pricePerUnit,
        date,
        risk_level: riskLevel,
        network: network.trim() || null,
      });
      onClose();
    } catch {
      setSaveError(t("crypto.form.saveError"));
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={selected ? t("crypto.form.addTitle", { name: selected.name }) : t("crypto.addButton")}
    >
      {!selected ? (
        <div className="space-y-3">
          <Input
            autoFocus
            placeholder={t("crypto.search.placeholder")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {searchError && <p className="text-sm text-danger">{searchError}</p>}
          {!searchError && query.trim().length < 2 && (
            <p className="text-sm text-text-muted">{t("crypto.search.hint")}</p>
          )}
          {searching && <p className="text-sm text-text-muted">{t("common.loading")}</p>}
          {!searching && !searchError && query.trim().length >= 2 && results.length === 0 && (
            <p className="text-sm text-text-muted">{t("crypto.search.empty")}</p>
          )}
          <ul className="max-h-72 space-y-1 overflow-y-auto">
            {results.map((coin) => (
              <li key={coin.coingecko_id}>
                <button
                  type="button"
                  onClick={() => setSelected(coin)}
                  className="flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-surface-2"
                >
                  {coin.thumb_url ? (
                    <img src={coin.thumb_url} alt="" className="h-6 w-6 shrink-0 rounded-full" />
                  ) : (
                    <span className="h-6 w-6 shrink-0 rounded-full bg-surface-2" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-text-primary">{coin.name}</span>
                    <span className="block text-xs text-text-muted">{coin.symbol}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <form onSubmit={handleSave} className="space-y-3">
          <div className="flex items-center gap-3 rounded-lg bg-surface-2 p-2">
            {selected.thumb_url ? (
              <img src={selected.thumb_url} alt="" className="h-6 w-6 shrink-0 rounded-full" />
            ) : (
              <span className="h-6 w-6 shrink-0 rounded-full bg-surface-1" />
            )}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-text-primary">{selected.name}</span>
              <span className="block text-xs text-text-muted">{selected.symbol}</span>
            </span>
          </div>

          {portfolios && portfolios.length > 1 && (
            <div>
              <Label htmlFor="crypto-portfolio">{t("crypto.portfolio.form.nameLabel")}</Label>
              <Select
                id="crypto-portfolio"
                value={portfolioId ?? ""}
                onChange={(event) => setPortfolioId(Number(event.target.value))}
              >
                {portfolios.map((portfolio) => (
                  <option key={portfolio.id} value={portfolio.id}>
                    {portfolio.name}
                  </option>
                ))}
              </Select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="crypto-quantity">{t("crypto.form.quantityLabel")}</Label>
              <Input
                id="crypto-quantity"
                type="number"
                step="any"
                min="0"
                required
                autoFocus
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="crypto-price">{t("crypto.form.pricePerUnitLabel")}</Label>
              <Input
                id="crypto-price"
                type="number"
                step="any"
                min="0"
                required
                value={pricePerUnit}
                onChange={(event) => setPricePerUnit(event.target.value)}
              />
            </div>
          </div>

          <div>
            <Label htmlFor="crypto-date">{t("crypto.form.dateLabel")}</Label>
            <Input
              id="crypto-date"
              type="date"
              required
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="crypto-risk">{t("netWorth.form.riskLevelLabel")}</Label>
            <Select
              id="crypto-risk"
              value={riskLevel}
              onChange={(event) => setRiskLevel(event.target.value as RiskLevel)}
            >
              {RISK_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {t(`netWorth.riskLevel.${level}` as TranslationKey)}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <Label htmlFor="crypto-network">{t("crypto.form.networkLabel")}</Label>
            <Input
              id="crypto-network"
              list="crypto-known-networks"
              placeholder={t("crypto.form.networkPlaceholder")}
              value={network}
              onChange={(event) => setNetwork(event.target.value.toUpperCase())}
            />
            <datalist id="crypto-known-networks">
              {knownNetworks.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </div>

          {saveError && <p className="text-sm text-danger">{saveError}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setSelected(null)}>
              {t("common.back")}
            </Button>
            <Button type="submit" disabled={createHolding.isPending}>
              {createHolding.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
