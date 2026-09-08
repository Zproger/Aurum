import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addCryptoTransaction,
  createCryptoHolding,
  createCryptoPortfolio,
  deleteCryptoHolding,
  deleteCryptoPortfolio,
  deleteCryptoTransaction,
  fetchCrypto90dPerformance,
  fetchCryptoHistory,
  fetchCryptoHoldings,
  fetchCryptoPortfolios,
  fetchCryptoTransactions,
  refreshCryptoPrices,
  updateCryptoHoldingRisk,
  updateCryptoPortfolio,
  updateCryptoTransaction,
} from "@/api/crypto";
import type { CryptoHoldingCreateInput, CryptoPortfolioInput, CryptoRange, CryptoTransactionInput, RiskLevel } from "@/types";

function useInvalidateCrypto() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["crypto-holdings"] });
    queryClient.invalidateQueries({ queryKey: ["crypto-transactions"] });
    queryClient.invalidateQueries({ queryKey: ["crypto-history"] });
    // A crypto holding is a normal Asset under the hood — Net Worth's own
    // numbers change the moment one is added/traded/repriced/removed.
    queryClient.invalidateQueries({ queryKey: ["net-worth-summary"] });
  };
}

export function useCryptoPortfolios(includeArchived = false) {
  return useQuery({
    queryKey: ["crypto-portfolios", includeArchived],
    queryFn: () => fetchCryptoPortfolios(includeArchived),
  });
}

export function useCreateCryptoPortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CryptoPortfolioInput) => createCryptoPortfolio(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["crypto-portfolios"] }),
  });
}

export function useUpdateCryptoPortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<CryptoPortfolioInput> }) =>
      updateCryptoPortfolio(id, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["crypto-portfolios"] }),
  });
}

export function useDeleteCryptoPortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteCryptoPortfolio(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["crypto-portfolios"] }),
  });
}

export function useCryptoHoldings(portfolioId?: number | null) {
  return useQuery({
    queryKey: ["crypto-holdings", portfolioId ?? null],
    queryFn: () => fetchCryptoHoldings(portfolioId),
  });
}

export function useCryptoHistory(range: CryptoRange, portfolioId?: number | null) {
  return useQuery({
    queryKey: ["crypto-history", range, portfolioId ?? null],
    queryFn: () => fetchCryptoHistory(range, portfolioId),
  });
}

// Only fires while the 90d range is actually selected — a real CoinGecko
// call per held coin (see get_90d_performance's docstring), not something
// to run on every Crypto tab visit the way 7d/30d/1y already do for free.
export function useCrypto90dPerformance(range: CryptoRange, portfolioId?: number | null) {
  return useQuery({
    queryKey: ["crypto-performance-90d", portfolioId ?? null],
    queryFn: () => fetchCrypto90dPerformance(portfolioId),
    enabled: range === "90d",
  });
}

export function useCryptoTransactions(assetId: number | null) {
  return useQuery({
    queryKey: ["crypto-transactions", assetId],
    queryFn: () => fetchCryptoTransactions(assetId!),
    enabled: assetId !== null,
  });
}

export function useRefreshCryptoPrices() {
  const invalidate = useInvalidateCrypto();
  // Always a bare call — sync covers every portfolio regardless of which
  // tab is active (see refresh_prices' own docstring), so there's no
  // portfolio_id variable for callers to pass here.
  return useMutation({ mutationFn: () => refreshCryptoPrices(), onSuccess: invalidate });
}

export function useCreateCryptoHolding() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: (input: CryptoHoldingCreateInput) => createCryptoHolding(input),
    onSuccess: invalidate,
  });
}

export function useAddCryptoTransaction() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: ({ assetId, input }: { assetId: number; input: CryptoTransactionInput }) =>
      addCryptoTransaction(assetId, input),
    onSuccess: invalidate,
  });
}

export function useUpdateCryptoTransaction() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: ({ transactionId, input }: { transactionId: number; input: CryptoTransactionInput }) =>
      updateCryptoTransaction(transactionId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteCryptoTransaction() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: (transactionId: number) => deleteCryptoTransaction(transactionId),
    onSuccess: invalidate,
  });
}

export function useDeleteCryptoHolding() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: (assetId: number) => deleteCryptoHolding(assetId),
    onSuccess: invalidate,
  });
}

export function useUpdateCryptoHoldingRisk() {
  const invalidate = useInvalidateCrypto();
  return useMutation({
    mutationFn: ({ assetId, riskLevel }: { assetId: number; riskLevel: RiskLevel }) =>
      updateCryptoHoldingRisk(assetId, riskLevel),
    onSuccess: invalidate,
  });
}
