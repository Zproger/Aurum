import { describe, expect, it } from "vitest";
import { makeHolding } from "@/test/cryptoFixtures";
import { computeTotals } from "./CryptoStatsRow";

describe("computeTotals", () => {
  it("excludes unpriced holdings from profit/loss instead of counting their cost as a loss", () => {
    const priced = makeHolding({ value: "150", cost_basis: "100", profit_loss: "50", profit_loss_percent: 50 });
    // Bought before the first successful price sync: real cost, no price yet.
    const unpriced = makeHolding({ value: null, cost_basis: "500", profit_loss: null, profit_loss_percent: null });

    const totals = computeTotals([priced, unpriced], "7d", undefined);

    expect(totals.totalValue).toBe(150);
    // "Total invested" is money actually spent, so it still includes the coin.
    expect(totals.totalCostBasis).toBe(600);
    // The old value - costBasis formula reported -450 here.
    expect(totals.totalProfitLoss).toBe(50);
    // Percentage uses the same priced base as the profit, not the full cost.
    expect(totals.totalProfitLossPercent).toBe(50);
  });

  it("shows no percentage when nothing in the portfolio can be priced", () => {
    const unpriced = makeHolding({ value: null, cost_basis: "500", profit_loss: null, profit_loss_percent: null });

    const totals = computeTotals([unpriced], "7d", undefined);

    expect(totals.totalProfitLoss).toBe(0);
    expect(totals.totalProfitLossPercent).toBeNull();
  });

  it("keeps a priced loss negative", () => {
    const priced = makeHolding({ value: "80", cost_basis: "100", profit_loss: "-20", profit_loss_percent: -20 });

    const totals = computeTotals([priced], "7d", undefined);

    expect(totals.totalProfitLoss).toBe(-20);
    expect(totals.totalProfitLossPercent).toBe(-20);
  });

  it("still picks best and worst performers from the selected range", () => {
    const up = makeHolding({ price_change_7d: "12.5" });
    const down = makeHolding({ price_change_7d: "-4.25" });
    const unknown = makeHolding({ price_change_7d: null });

    const totals = computeTotals([up, down, unknown], "7d", undefined);

    expect(totals.best?.holding.asset_id).toBe(up.asset_id);
    expect(totals.best?.percent).toBe(12.5);
    expect(totals.worst?.holding.asset_id).toBe(down.asset_id);
    expect(totals.worst?.percent).toBe(-4.25);
  });
});
