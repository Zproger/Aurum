import { api } from "@/api/client";

export interface FxQuote {
  currency: string;
  rate_to_usd: string;
  rate_date: string;
}

export function fetchFxQuote(currency: string, date: string) {
  return api.get<FxQuote>(`/fx/quote?${new URLSearchParams({ currency, date })}`);
}
