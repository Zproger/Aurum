import { beforeEach, describe, expect, it } from "vitest";
import { setLanguage } from "@/lib/i18n";
import {
  formatCryptoAmount,
  formatCurrency,
  formatSignedCurrency,
  formatTransactionDate,
  getIntlLocale,
  getMonthLabels,
  maskAmount,
  pluralizeRu,
  trimTrailingZeros,
} from "@/lib/format";

describe("getIntlLocale", () => {
  it("maps ru to ru-RU and en to en-US", () => {
    expect(getIntlLocale("ru")).toBe("ru-RU");
    expect(getIntlLocale("en")).toBe("en-US");
  });
});

describe("formatCurrency", () => {
  beforeEach(() => setLanguage("en"));

  it("keeps unambiguous currency symbols compact, not spelled out", () => {
    // The exact regression this suite exists to catch: currencyDisplay
    // "code" would turn this into "USD 614" — see lib/format.ts's
    // createCurrencyFormatter docstring and the PR #18 review that flagged it.
    expect(formatCurrency(614, "USD")).toBe("$614");
  });

  it("drops the region prefix on ambiguous symbols (CNY, HKD) instead of spelling out the code", () => {
    const cny = formatCurrency(614, "CNY");
    const hkd = formatCurrency(614, "HKD");
    expect(cny).not.toContain("CN¥");
    expect(cny).not.toContain("CNY");
    expect(hkd).not.toContain("HK$");
    expect(hkd).not.toContain("HKD");
  });

  it("rounds to whole units", () => {
    expect(formatCurrency(614.5, "USD")).toBe("$615");
    expect(formatCurrency(614.4, "USD")).toBe("$614");
  });

  it("accepts a numeric string the same as a number", () => {
    expect(formatCurrency("614", "USD")).toBe(formatCurrency(614, "USD"));
  });
});

describe("formatCryptoAmount", () => {
  beforeEach(() => setLanguage("en"));

  it("uses 2 decimals once the value reaches 1", () => {
    expect(formatCryptoAmount(1234.5678, "USD")).toBe("$1,234.57");
  });

  it("uses 2 decimals for exactly zero", () => {
    expect(formatCryptoAmount(0, "USD")).toBe("$0.00");
  });

  it("scales precision for sub-cent values so they don't round away to $0.00", () => {
    // 8 leading zeros after the decimal point + 4 digits of real precision.
    expect(formatCryptoAmount(0.000000006894, "USD")).toBe("$0.000000006894");
  });
});

describe("formatSignedCurrency", () => {
  beforeEach(() => setLanguage("en"));

  it("prefixes a plus sign on positive amounts", () => {
    expect(formatSignedCurrency(100, "USD")).toBe("+$100");
  });

  it("leaves the formatter's own minus sign on negative amounts, no double sign", () => {
    expect(formatSignedCurrency(-100, "USD")).toBe("-$100");
  });

  it("adds no sign for zero", () => {
    expect(formatSignedCurrency(0, "USD")).toBe("$0");
  });
});

describe("maskAmount", () => {
  it("replaces the formatted value when hidden", () => {
    expect(maskAmount("$1,234", true)).toBe("••••");
  });

  it("passes the formatted value through when not hidden", () => {
    expect(maskAmount("$1,234", false)).toBe("$1,234");
  });
});

describe("trimTrailingZeros", () => {
  it("strips a wei-level all-zero fractional part down to the integer", () => {
    expect(trimTrailingZeros("3.000000000000000000")).toBe("3");
  });

  it("trims only the trailing zeros, keeping real precision", () => {
    expect(trimTrailingZeros("3.140000")).toBe("3.14");
  });

  it("leaves a value with no decimal point untouched", () => {
    expect(trimTrailingZeros("42")).toBe("42");
  });

  it("collapses an all-zero fractional part to a bare 0, not empty or a dangling minus", () => {
    expect(trimTrailingZeros("0.000")).toBe("0");
    expect(trimTrailingZeros("-0.000")).toBe("0");
  });
});

describe("getMonthLabels", () => {
  it("returns 12 labels for each language", () => {
    expect(getMonthLabels("en")).toHaveLength(12);
    expect(getMonthLabels("ru")).toHaveLength(12);
  });

  it("starts January in both languages", () => {
    expect(getMonthLabels("en")[0]).toBe("Jan");
    expect(getMonthLabels("ru")[0]).toBe("Янв");
  });
});

describe("formatTransactionDate", () => {
  it("omits the year by default", () => {
    expect(formatTransactionDate("2026-08-29", false)).toBe(getIntlLocale("en") === "en-US" ? "Aug 29" : "Aug 29");
  });

  it("includes the year when asked", () => {
    expect(formatTransactionDate("2026-08-29", true)).toContain("2026");
  });
});

describe("pluralizeRu", () => {
  it("picks the singular form for 1 (and 21, 31, ... but not 11)", () => {
    expect(pluralizeRu(1, "актив", "актива", "активов")).toBe("актив");
    expect(pluralizeRu(21, "актив", "актива", "активов")).toBe("актив");
    expect(pluralizeRu(11, "актив", "актива", "активов")).not.toBe("актив");
  });

  it("picks the few form for 2-4 (and 22-24, but not 12-14)", () => {
    expect(pluralizeRu(2, "актив", "актива", "активов")).toBe("актива");
    expect(pluralizeRu(4, "актив", "актива", "активов")).toBe("актива");
    expect(pluralizeRu(22, "актив", "актива", "активов")).toBe("актива");
    expect(pluralizeRu(12, "актив", "актива", "активов")).toBe("активов");
  });

  it("picks the many form for 0, 5-20, and 11-14", () => {
    expect(pluralizeRu(0, "актив", "актива", "активов")).toBe("активов");
    expect(pluralizeRu(5, "актив", "актива", "активов")).toBe("активов");
    expect(pluralizeRu(11, "актив", "актива", "активов")).toBe("активов");
    expect(pluralizeRu(14, "актив", "актива", "активов")).toBe("активов");
  });
});
