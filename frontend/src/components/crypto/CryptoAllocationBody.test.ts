import { describe, expect, it } from "vitest";
import { makeHolding } from "@/test/cryptoFixtures";
import { buildSlices } from "./CryptoAllocationBody";

describe("buildSlices (per-coin allocation)", () => {
  it("keys each slice by asset_id, one per holding", () => {
    const holdings = [makeHolding({ asset_id: 7, name: "Bitcoin", symbol: "BTC", value: "100" })];
    const slices = buildSlices(holdings);
    expect(slices).toEqual([{ key: "7", name: "Bitcoin", symbol: "BTC", amount: 100, color: "var(--series-1)" }]);
  });

  it("excludes unpriced and exactly-zero holdings", () => {
    const holdings = [makeHolding({ value: null }), makeHolding({ value: "0" })];
    expect(buildSlices(holdings)).toEqual([]);
  });

  it("sorts slices by amount descending", () => {
    const holdings = [
      makeHolding({ symbol: "SMALL", value: "10" }),
      makeHolding({ symbol: "BIG", value: "90" }),
    ];
    expect(buildSlices(holdings).map((s) => s.symbol)).toEqual(["BIG", "SMALL"]);
  });

  it("folds every coin past the top 7 into one 'Other' slice", () => {
    const holdings = Array.from({ length: 9 }, (_, i) => makeHolding({ symbol: `C${i}`, value: String(9 - i) }));
    const slices = buildSlices(holdings);
    expect(slices).toHaveLength(8);
    const other = slices.find((s) => s.key === "other")!;
    expect(other.name).toBe("Other");
    expect(other.symbol).toBeNull();
    // The two smallest holdings: value 2 and value 1.
    expect(other.amount).toBe(3);
    expect(other.color).toBe("var(--series-other)");
  });

  it("returns nothing at all when every holding is unpriced", () => {
    expect(buildSlices([makeHolding({ value: null })])).toEqual([]);
  });
});
