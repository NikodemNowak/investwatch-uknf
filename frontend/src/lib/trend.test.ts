import { describe, expect, it } from "vitest";
import type { TrendSeries } from "@/api/types";
import { bucketLabel, shortDay, trendPeriod, trendTotals, violationsPerDay } from "@/lib/trend";

const series: TrendSeries = {
  bucket: "day",
  start: "2026-11-20",
  end: "2026-11-21",
  points: [
    {
      bucket_start: "2026-11-21",
      module: "m1_third_party_ad",
      total: 5,
      high: 1,
      medium: 2,
      low: 2,
    },
    {
      bucket_start: "2026-11-21",
      module: "m2_risk_disclosure",
      total: 3,
      high: 2,
      medium: 0,
      low: 1,
    },
    {
      bucket_start: "2026-11-20",
      module: "m1_third_party_ad",
      total: 1,
      high: 0,
      medium: 1,
      low: 0,
    },
    {
      bucket_start: "2026-11-20",
      module: "m2_risk_disclosure",
      total: 0,
      high: 0,
      medium: 0,
      low: 0,
    },
  ],
};

describe("violationsPerDay", () => {
  it("sums modules per day, oldest first, and drops low risk", () => {
    expect(violationsPerDay(series)).toEqual([
      { day: "2026-11-20", high: 0, medium: 1 },
      { day: "2026-11-21", high: 3, medium: 2 },
    ]);
  });

  it("keeps only the active module tab", () => {
    expect(violationsPerDay(series, "m2_risk_disclosure")).toEqual([
      { day: "2026-11-20", high: 0, medium: 0 },
      { day: "2026-11-21", high: 2, medium: 0 },
    ]);
  });
});

describe("trendTotals", () => {
  it("adds up levels and finds the busiest day", () => {
    const totals = trendTotals(violationsPerDay(series));
    expect(totals).toMatchObject({ high: 3, medium: 3, total: 6 });
    expect(totals.peak?.day).toBe("2026-11-21");
  });

  it("has no peak when nothing was detected", () => {
    expect(trendTotals([{ day: "2026-11-20", high: 0, medium: 0 }]).peak).toBeNull();
  });
});

describe("shortDay", () => {
  it("formats day.month", () => {
    expect(shortDay("2026-11-08")).toBe("08.11");
  });
});

describe("hourly buckets (fresh demo: everything within 48 h)", () => {
  const hourly: TrendSeries = {
    bucket: "hour",
    start: "2026-11-21",
    end: "2026-11-21",
    points: [
      {
        bucket_start: "2026-11-21",
        bucket_at: "2026-11-21T14:00:00Z",
        module: "m1_third_party_ad",
        total: 2,
        high: 1,
        medium: 1,
        low: 0,
      },
      {
        bucket_start: "2026-11-21",
        bucket_at: "2026-11-21T15:00:00Z",
        module: "m1_third_party_ad",
        total: 3,
        high: 2,
        medium: 0,
        low: 1,
      },
      {
        bucket_start: "2026-11-21",
        bucket_at: "2026-11-21T15:00:00Z",
        module: "m2_risk_disclosure",
        total: 1,
        high: 1,
        medium: 0,
        low: 0,
      },
    ],
  };

  it("keeps one bar per hour, not one per day", () => {
    expect(violationsPerDay(hourly).map((d) => [d.day, d.high])).toEqual([
      ["2026-11-21T14:00:00Z", 1],
      ["2026-11-21T15:00:00Z", 3],
    ]);
    expect(trendPeriod(hourly)).toEqual({ bucket: "hour", count: 2 });
  });

  it("labels hours in Polish time and days as day.month", () => {
    expect(bucketLabel("2026-11-21T15:00:00Z", "hour")).toBe("16:00");
    expect(bucketLabel("2026-11-21", "day")).toBe("21.11");
  });
});
