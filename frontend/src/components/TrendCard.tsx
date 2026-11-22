import { lazy, Suspense, useMemo } from "react";
import type { ModuleId } from "@/api/types";
import { useTrend } from "@/hooks/useTrend";
import { pl } from "@/i18n/pl";
import { formatInt } from "@/lib/plural";
import { bucketLabel, trendTotals, violationsPerDay } from "@/lib/trend";

// Recharts is the heaviest UI dependency; load it after the table so the list shows first.
const TrendBars = lazy(() => import("@/components/TrendBars"));

/**
 * "Wykryte naruszenia w czasie" for the active module tab: hourly buckets when all data is from
 * the last 48 hours (a fresh demo), daily otherwise. The period label says which.
 */
export function TrendCard({ module }: { module: ModuleId | undefined }) {
  const trend = useTrend(module);
  const days = useMemo(() => (trend.data ? violationsPerDay(trend.data) : []), [trend.data]);
  const bucket = trend.data?.bucket ?? "day";
  const label = (key: string) => bucketLabel(key, bucket);
  const totals = trendTotals(days);
  const t = pl.review.trend;
  const summary = t.summary(
    bucket,
    days.length,
    totals.total,
    totals.high,
    totals.medium,
    totals.peak ? label(totals.peak.day) : null,
    totals.peak ? totals.peak.high + totals.peak.medium : 0,
  );

  return (
    <section className="card trend" aria-labelledby="trend-title">
      <div className="trend__head">
        <div>
          <h2 id="trend-title" className="trend__title">
            {t.title}
          </h2>
          <p className="trend__period">
            {trend.data ? `${t.period(bucket, days.length)} · ${t.total(totals.total)}` : "\u00a0"}
          </p>
        </div>
        <ul className="trend__legend">
          <li>
            <span className="trend-key trend-key--high" />
            {t.high}
          </li>
          <li>
            <span className="trend-key trend-key--medium" />
            {t.medium}
          </li>
        </ul>
      </div>
      {trend.isError ? (
        <p className="trend__error">{t.error}</p>
      ) : (
        <figure className="trend__plot" aria-label={trend.data ? summary : undefined}>
          <div aria-hidden="true">
            {trend.data && (
              <Suspense fallback={null}>
                <TrendBars days={days} label={label} />
              </Suspense>
            )}
          </div>
          {trend.data && (
            <div className="sr-only">
              <table>
                <caption>{summary}</caption>
                <thead>
                  <tr>
                    <th scope="col">{bucket === "hour" ? t.hour : t.day}</th>
                    <th scope="col">{t.high}</th>
                    <th scope="col">{t.medium}</th>
                  </tr>
                </thead>
                <tbody>
                  {days.map((d) => (
                    <tr key={d.day}>
                      <th scope="row">{label(d.day)}</th>
                      <td>{formatInt(d.high)}</td>
                      <td>{formatInt(d.medium)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </figure>
      )}
    </section>
  );
}
