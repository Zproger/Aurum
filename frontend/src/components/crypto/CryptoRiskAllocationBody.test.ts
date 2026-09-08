import { describe, expect, it } from "vitest";
import { makeHolding } from "@/test/cryptoFixtures";
import { computeRiskTiers } from "./CryptoRiskAllocationBody";

describe("computeRiskTiers", () => {
  it("always returns exactly the three tiers, in low/medium/high order", () => {
    const tiers = computeRiskTiers([]);
    expect(tiers.map((t) => t.level)).toEqual(["low", "medium", "high"]);
  });

  it("splits total portfolio value by risk_level", () => {
    const holdings = [
      makeHolding({ symbol: "BTC", risk_level: "low", value: "600" }),
      makeHolding({ symbol: "ETH", risk_level: "medium", value: "300" }),
      makeHolding({ symbol: "SHIB", risk_level: "high", value: "100" }),
    ];
    const tiers = computeRiskTiers(holdings);
    const byLevel = Object.fromEntries(tiers.map((t) => [t.level, t]));

    expect(byLevel.low.value).toBe(600);
    expect(byLevel.low.percent).toBeCloseTo(60);
    expect(byLevel.medium.percent).toBeCloseTo(30);
    expect(byLevel.high.percent).toBeCloseTo(10);
  });

  it("sums multiple holdings in the same tier instead of overwriting", () => {
    const holdings = [
      makeHolding({ symbol: "SHIB", risk_level: "high", value: "100" }),
      makeHolding({ symbol: "PEPE", risk_level: "high", value: "50" }),
    ];
    const high = computeRiskTiers(holdings).find((t) => t.level === "high")!;
    expect(high.value).toBe(150);
    expect(high.items).toHaveLength(2);
  });

  it("excludes unpriced holdings from every percentage, not just their own tier", () => {
    const holdings = [
      makeHolding({ symbol: "BTC", risk_level: "low", value: "100" }),
      makeHolding({ symbol: "UNPRICED", risk_level: "low", value: null }),
    ];
    const low = computeRiskTiers(holdings).find((t) => t.level === "low")!;
    expect(low.value).toBe(100);
    expect(low.percent).toBe(100);
    expect(low.items).toHaveLength(1);
  });

  it("sorts a tier's items by value descending", () => {
    const holdings = [
      makeHolding({ symbol: "SMALL", risk_level: "high", value: "10" }),
      makeHolding({ symbol: "BIG", risk_level: "high", value: "90" }),
    ];
    const high = computeRiskTiers(holdings).find((t) => t.level === "high")!;
    expect(high.items.map((i) => i.symbol)).toEqual(["BIG", "SMALL"]);
  });

  it("computes each item's percent of its own tier, not of the whole portfolio", () => {
    const holdings = [
      makeHolding({ symbol: "BIG", risk_level: "high", value: "90" }),
      makeHolding({ symbol: "SMALL", risk_level: "high", value: "10" }),
      makeHolding({ symbol: "OTHER_TIER", risk_level: "low", value: "900" }),
    ];
    const high = computeRiskTiers(holdings).find((t) => t.level === "high")!;
    // 90/100 and 10/100 of the *high tier's* 100, not of the 1000 total.
    expect(high.items.find((i) => i.symbol === "BIG")!.percent).toBeCloseTo(90);
    expect(high.items.find((i) => i.symbol === "SMALL")!.percent).toBeCloseTo(10);
  });

  it("leaves an empty tier at 0%, not NaN, when nothing is held in it", () => {
    const holdings = [makeHolding({ risk_level: "high", value: "100" })];
    const low = computeRiskTiers(holdings).find((t) => t.level === "low")!;
    expect(low.value).toBe(0);
    expect(low.percent).toBe(0);
    expect(low.items).toEqual([]);
  });

  it("leaves every tier at 0% when nothing is priced at all, instead of dividing by zero", () => {
    const holdings = [makeHolding({ risk_level: "high", value: null })];
    for (const tier of computeRiskTiers(holdings)) {
      expect(tier.percent).toBe(0);
      expect(Number.isNaN(tier.percent)).toBe(false);
    }
  });
});
