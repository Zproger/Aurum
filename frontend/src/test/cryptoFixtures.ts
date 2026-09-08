import type { CryptoHolding } from "@/types";

let nextAssetId = 1;

/** Minimal valid CryptoHolding for allocation-math tests — every field the
 * type requires, with sane defaults so a test only has to override what it
 * actually cares about (symbol, value, risk_level, network, ...). */
export function makeHolding(overrides: Partial<CryptoHolding> = {}): CryptoHolding {
  const id = overrides.asset_id ?? nextAssetId++;
  return {
    asset_id: id,
    portfolio_id: 1,
    coingecko_id: `coin-${id}`,
    symbol: `C${id}`,
    name: `Coin ${id}`,
    thumb_url: null,
    risk_level: "high",
    network: null,
    quantity: "1",
    avg_buy_price: "1",
    current_price: "1",
    price_change_1h: null,
    price_change_24h: null,
    price_change_7d: null,
    price_change_30d: null,
    price_change_1y: null,
    value: "100",
    cost_basis: "100",
    profit_loss: "0",
    profit_loss_percent: 0,
    ...overrides,
  };
}
