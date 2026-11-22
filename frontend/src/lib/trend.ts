import type { ModuleId, TrendBucket, TrendSeries } from "@/api/types";

/** One bucket (day or hour) of the "Wykryte naruszenia w czasie" chart, by risk level. */
export interface TrendDay {
  /** ISO date of a daily bucket, or ISO timestamp (UTC) of an hourly one. */
  day: string;
  high: number;
  medium: number;
}

/** Headline numbers for the chart's caption and its accessible summary. */
export interface TrendTotals {
  high: number;
  medium: number;
  total: number;
  /** Busiest day, or null when nothing was detected. */
  peak: TrendDay | null;
}

/**
 * Sum the per-module points of `GET /api/stats/trend` into one bar per bucket.
 * Low-risk findings are not violations, so they are left out of the chart.
 */
export function violationsPerDay(series: TrendSeries, module?: ModuleId): TrendDay[] {
  const days = new Map<string, TrendDay>();
  for (const point of series.points) {
    if (module && point.module !== module) continue;
    const key =
      series.bucket === "hour" ? (point.bucket_at ?? point.bucket_start) : point.bucket_start;
    const day = days.get(key) ?? { day: key, high: 0, medium: 0 };
    day.high += point.high;
    day.medium += point.medium;
    days.set(key, day);
  }
  return [...days.values()].sort((a, b) => a.day.localeCompare(b.day));
}

/** Totals over all days and the busiest one (first on ties). */
export function trendTotals(days: TrendDay[]): TrendTotals {
  let peak: TrendDay | null = null;
  let high = 0;
  let medium = 0;
  for (const day of days) {
    high += day.high;
    medium += day.medium;
    if (day.high + day.medium > (peak ? peak.high + peak.medium : 0)) peak = day;
  }
  return { high, medium, total: high + medium, peak };
}

const HOUR = new Intl.DateTimeFormat("pl-PL", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Warsaw",
});

/** "15:00" for an hourly bucket, in Polish time (the analysts' clock). */
export function shortHour(iso: string): string {
  return HOUR.format(new Date(iso));
}

/** Axis / tooltip label of a bucket. */
export function bucketLabel(key: string, bucket: TrendBucket): string {
  return bucket === "hour" ? shortHour(key) : shortDay(key);
}

/** The chart's honest period: how many buckets of which size it shows. */
export interface TrendPeriod {
  bucket: TrendBucket;
  count: number;
}

export function trendPeriod(series: TrendSeries): TrendPeriod {
  return { bucket: series.bucket, count: violationsPerDay(series).length };
}

/** "21.11" for an ISO date, without timezone shifts. */
export function shortDay(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day ?? ""}.${month ?? ""}`;
}
