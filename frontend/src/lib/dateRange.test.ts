import { afterEach, describe, expect, it, vi } from "vitest";
import { computeRange } from "@/lib/dateRange";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
});

describe("computeRange", () => {
  it("ends this_year on the local calendar date, not the UTC one", () => {
    // 00:30 on Jan 1 in UTC+5:30 is still Dec 31 in UTC. The old
    // toISOString().slice(0, 10) end date was therefore before the start
    // date, and "this year" reports came back empty until UTC midnight.
    vi.stubEnv("TZ", "Asia/Kolkata");
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:30:00+05:30"));

    expect(computeRange("this_year")).toEqual({ startDate: "2026-01-01", endDate: "2026-01-01" });
  });

  it("ends 5y on the local date, so today's transactions stay in range", () => {
    vi.stubEnv("TZ", "Asia/Kolkata");
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-16T00:30:00+05:30"));

    // 5 years back from Nov 2026, from the first of that month.
    expect(computeRange("5y")).toEqual({ startDate: "2021-11-01", endDate: "2026-11-16" });
  });

  it("returns no bounds for all, and the full calendar years for custom", () => {
    expect(computeRange("all")).toEqual({});
    expect(computeRange("custom", { fromYear: 2020, toYear: 2024 })).toEqual({
      startDate: "2020-01-01",
      endDate: "2024-12-31",
    });
    expect(computeRange("custom")).toEqual({});
  });
});
