import { describe, expect, it } from "vitest";
import { makeHolding } from "@/test/cryptoFixtures";
import { buildSlices } from "./CryptoNetworkAllocationBody";

const UNSET = "No network set";

describe("buildSlices (network allocation)", () => {
  it("groups holdings by network, summing their value", () => {
    const holdings = [
      makeHolding({ network: "Ethereum", value: "100" }),
      makeHolding({ network: "Ethereum", value: "50" }),
      makeHolding({ network: "Tron", value: "30" }),
    ];
    const slices = buildSlices(holdings, UNSET);
    const byLabel = Object.fromEntries(slices.map((s) => [s.label, s.amount]));
    expect(byLabel["Ethereum"]).toBe(150);
    expect(byLabel["Tron"]).toBe(30);
  });

  it("folds holdings with no network into one unset bucket instead of dropping them", () => {
    const holdings = [makeHolding({ network: null, value: "40" }), makeHolding({ network: null, value: "10" })];
    const slices = buildSlices(holdings, UNSET);
    expect(slices).toHaveLength(1);
    expect(slices[0].label).toBe(UNSET);
    expect(slices[0].amount).toBe(50);
  });

  it("excludes unpriced holdings entirely", () => {
    const holdings = [makeHolding({ network: "Ethereum", value: null })];
    expect(buildSlices(holdings, UNSET)).toEqual([]);
  });

  it("sorts slices by amount descending", () => {
    const holdings = [
      makeHolding({ network: "Small", value: "10" }),
      makeHolding({ network: "Big", value: "90" }),
    ];
    const slices = buildSlices(holdings, UNSET);
    expect(slices.map((s) => s.label)).toEqual(["Big", "Small"]);
  });

  it("assigns each of the first 7 slices its own distinct color", () => {
    const holdings = Array.from({ length: 7 }, (_, i) => makeHolding({ network: `Net${i}`, value: String(10 - i) }));
    const slices = buildSlices(holdings, UNSET);
    expect(slices).toHaveLength(7);
    expect(new Set(slices.map((s) => s.color)).size).toBe(7);
  });

  it("folds every network past the top 7 into one '__other__' slice", () => {
    // 9 distinct networks — 7 keep their own slice, 2 fold into "other".
    const holdings = Array.from({ length: 9 }, (_, i) => makeHolding({ network: `Net${i}`, value: String(9 - i) }));
    const slices = buildSlices(holdings, UNSET);
    expect(slices).toHaveLength(8); // 7 top + 1 "other"
    const other = slices.find((s) => s.key === "__other__")!;
    expect(other).toBeDefined();
    // The two smallest: Net7 (value 2) and Net8 (value 1).
    expect(other.amount).toBe(3);
  });
});
