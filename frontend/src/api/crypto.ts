import { api } from "@/api/client";
import type {
  CryptoHistoryResponse,
  CryptoHolding,
  CryptoHoldingCreateInput,
  CryptoPerformanceResponse,
  CryptoPortfolio,
  CryptoPortfolioInput,
  CryptoRange,
  CryptoSearchResult,
  CryptoSyncResult,
  CryptoTransaction,
  CryptoTransactionInput,
  RiskLevel,
} from "@/types";

export function fetchCryptoPortfolios(includeArchived = false) {
  return api.get<CryptoPortfolio[]>(`/crypto/portfolios?include_archived=${includeArchived}`);
}

export function createCryptoPortfolio(input: CryptoPortfolioInput) {
  return api.post<CryptoPortfolio>("/crypto/portfolios", input);
}

export function updateCryptoPortfolio(portfolioId: number, input: Partial<CryptoPortfolioInput>) {
  return api.patch<CryptoPortfolio>(`/crypto/portfolios/${portfolioId}`, input);
}

export function deleteCryptoPortfolio(portfolioId: number) {
  return api.delete<void>(`/crypto/portfolios/${portfolioId}`);
}

// Also triggers the lazy once-a-day auto-refresh server-side — see
// services/crypto_service.py. `portfolioId` only narrows what comes back in
// `holdings` — the sync itself (and the 24h window) always covers every
// portfolio, see refresh_prices' own docstring.
export function fetchCryptoHoldings(portfolioId?: number | null) {
  const query = portfolioId != null ? `?portfolio_id=${portfolioId}` : "";
  return api.get<CryptoSyncResult>(`/crypto/holdings${query}`);
}

export function refreshCryptoPrices(portfolioId?: number | null) {
  const query = portfolioId != null ? `?portfolio_id=${portfolioId}` : "";
  return api.post<CryptoSyncResult>(`/crypto/refresh${query}`, {});
}

export function createCryptoHolding(input: CryptoHoldingCreateInput) {
  return api.post<CryptoHolding>("/crypto/holdings", input);
}

// Buy more of, or sell some of, a coin already being tracked.
export function addCryptoTransaction(assetId: number, input: CryptoTransactionInput) {
  return api.post<CryptoHolding>(`/crypto/holdings/${assetId}/transactions`, input);
}

export function fetchCryptoTransactions(assetId: number) {
  return api.get<CryptoTransaction[]>(`/crypto/holdings/${assetId}/transactions`);
}

export function updateCryptoTransaction(transactionId: number, input: CryptoTransactionInput) {
  return api.patch<CryptoHolding>(`/crypto/transactions/${transactionId}`, input);
}

export function deleteCryptoTransaction(transactionId: number) {
  return api.delete<void>(`/crypto/transactions/${transactionId}`);
}

// Reuses the existing asset-delete endpoint — deleting the Asset cascades
// to the linked crypto_holdings row (and its whole transaction log)
// server-side, no dedicated endpoint.
export function deleteCryptoHolding(assetId: number) {
  return api.delete<void>(`/assets/${assetId}`);
}

// Risk level lives on the underlying Asset, not CryptoHolding — reuses the
// generic Asset PATCH endpoint, same pattern as deleteCryptoHolding above.
export function updateCryptoHoldingRisk(assetId: number, riskLevel: RiskLevel) {
  return api.patch<void>(`/assets/${assetId}`, { risk_level: riskLevel });
}

export function searchCryptoCoins(query: string) {
  return api.get<CryptoSearchResult[]>(`/crypto/search?q=${encodeURIComponent(query)}`);
}

export function fetchCryptoHistory(range: CryptoRange, portfolioId?: number | null) {
  const query = portfolioId != null ? `&portfolio_id=${portfolioId}` : "";
  return api.get<CryptoHistoryResponse>(`/crypto/history?range=${range}${query}`);
}

export function fetchCrypto90dPerformance(portfolioId?: number | null) {
  const query = portfolioId != null ? `?portfolio_id=${portfolioId}` : "";
  return api.get<CryptoPerformanceResponse>(`/crypto/performance/90d${query}`);
}
