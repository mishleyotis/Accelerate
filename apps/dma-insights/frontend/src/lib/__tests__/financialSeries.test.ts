/**
 * Client-side financial series miner (D5 Context chart fallback) —
 * mirrors the backend _pairs orientations so the Context chart renders
 * whenever the payload carries a year→$ series as TEXT (metrics values /
 * lines prose) while `series_labeled` shipped empty.
 */
import { describe, expect, it } from "vitest";
import { extractYearMoneyPairs, mineFinancialSeries } from "../financialSeries";

describe("extractYearMoneyPairs", () => {
  it("year→value orientation: '2023 $34.2B' / 'in 2021 to $3.2B'", () => {
    // 34.2 * 1e9 (not the 34.2e9 literal) — matches the miner's own
    // float arithmetic; downstream values are rounded after unit scaling.
    expect(extractYearMoneyPairs("2023 $34.2B")).toEqual([[2023, 34.2 * 1e9]]);
    expect(extractYearMoneyPairs("grew from $2.286B in 2021 to $3.209B in 2025"))
      .toEqual(expect.arrayContaining([[2021, 2.286e9], [2025, 3.209e9]]));
  });

  it("value→year orientation: '$592M in 2023' and '$153.7M (FY2022)'", () => {
    expect(extractYearMoneyPairs("$592M in 2023")).toEqual([[2023, 592e6]]);
    expect(extractYearMoneyPairs("$153.7M (FY2022)")).toEqual([[2022, 153.7e6]]);
  });

  it("rejects out-of-range years and non-money numbers", () => {
    expect(extractYearMoneyPairs("$5B in 1970")).toEqual([]);
    expect(extractYearMoneyPairs("headcount 2023: 4,100 FTE")).toEqual([]);
  });
});

describe("mineFinancialSeries", () => {
  it("mines a chartable multi-year series out of prose lines", () => {
    const out = mineFinancialSeries({
      lines: ["Total assets grew from $2.286B in 2021 to $3.209B in 2025."],
    });
    expect(out).toHaveLength(1);
    expect(out[0]).toEqual({
      metric: "total_assets",
      unit: "usd_b",
      fy: [2021, 2025],
      values: [2.29, 3.21],
    });
  });

  it("mines string metric values, keyed by the metric name", () => {
    const out = mineFinancialSeries({
      metrics: {
        net_income: "$592M in 2023, up from $410M in 2021",
        rating: "A+",
      },
    });
    expect(out).toHaveLength(1);
    expect(out[0].metric).toBe("net_income");
    expect(out[0].unit).toBe("usd_m");
    expect(out[0].fy).toEqual([2021, 2023]);
    expect(out[0].values).toEqual([410, 592]);
  });

  it("needs >=2 distinct years — a single point never charts", () => {
    expect(mineFinancialSeries({ lines: ["Revenue of $1.2B in 2024."] })).toEqual([]);
    expect(mineFinancialSeries({ lines: ["No numbers here."] })).toEqual([]);
    expect(mineFinancialSeries(null)).toEqual([]);
  });

  it("first value wins per (metric, year) and series sort is most-points-first", () => {
    const out = mineFinancialSeries({
      lines: [
        "Total assets $3.1B in 2023 and $3.4B in 2024; restated total assets $9.9B in 2023.",
        "Revenue $0.8B in 2022, $0.9B in 2023, $1.0B in 2024.",
      ],
    });
    expect(out[0].metric).toBe("revenue");        // 3 points beat 2
    expect(out[0].fy).toEqual([2022, 2023, 2024]);
    const assets = out.find((s) => s.metric === "total_assets");
    expect(assets?.values).toEqual([3.1, 3.4]);   // first 2023 value kept
  });

  it("drops a cross-metric outlier from the last-resort mine (no $0.48B cliff)", () => {
    const out = mineFinancialSeries({
      lines: [
        "Total assets $29.5B in 2021, $30.8B in 2022, $32.1B in 2023, " +
          "$0.48B in 2024, $34.3B in 2025.",
      ],
    });
    const assets = out.find((s) => s.metric === "total_assets");
    expect(assets).toBeDefined();
    expect(assets?.fy).not.toContain(2024);       // 66x-below-median outlier gone
    expect(assets?.values).not.toContain(0.48);
  });

  it("keeps a plausible 2-point series but drops an implausible one", () => {
    const ok = mineFinancialSeries({
      lines: ["Total assets $30B in 2021, $34B in 2025."],
    });
    expect(ok.find((s) => s.metric === "total_assets")?.fy).toHaveLength(2);
    const bad = mineFinancialSeries({
      lines: ["Total assets $30B in 2021, $0.3B in 2025."],
    });
    expect(bad.find((s) => s.metric === "total_assets")).toBeUndefined();
  });
});
