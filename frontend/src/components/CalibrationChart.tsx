import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TooltipContentProps, TooltipValueType } from "recharts";
import type { CalibrationReport } from "@/api/types";
import { pl } from "@/i18n/pl";
import { snapThreshold, thresholdRows, type ThresholdRow } from "@/lib/calibration";
import { formatThreshold } from "@/lib/format";
import { formatInt } from "@/lib/plural";

// Validated pair (dataviz validator, light surface): accent blue and orange; "missed" is the
// recessive gray, dashed, so it never relies on hue alone. SVG strokes repeat the CSS tokens.
const BLUE = "#1d4ed8";
const ORANGE = "#e0622c";
const GRAY = "#71717a";
const INK = "#3f3f46";
const AXIS = "#e4e4e7";

type Mode = "counts" | "rates";
type Key = keyof Omit<ThresholdRow, "threshold">;
interface Series {
  key: Key;
  label: string;
  color: string;
  dash?: string;
}

const t = pl.calibChart;
const SERIES: Record<Mode, Series[]> = {
  counts: [
    { key: "found", label: t.found, color: BLUE },
    { key: "falseAlarms", label: t.falseAlarms, color: ORANGE },
    { key: "missed", label: t.missed, color: GRAY, dash: "6 4" },
  ],
  rates: [
    { key: "recall", label: t.recall, color: BLUE },
    { key: "precision", label: t.precision, color: ORANGE },
  ],
};

const value = (mode: Mode, v: number) =>
  mode === "rates" ? `${formatInt(Math.round(v))}%` : formatInt(v);

/** Threshold vs found / false alarms / missed (or recall / precision), moving with the slider. */
export default function CalibrationChart({
  report,
  threshold,
}: {
  report: CalibrationReport;
  threshold: number;
}) {
  const [mode, setMode] = useState<Mode>("counts");
  const rows = useMemo(() => thresholdRows(report.points), [report.points]);
  const at = snapThreshold(threshold);
  const current = rows.find((r) => Math.abs(r.threshold - at) < 1e-9);
  const series = SERIES[mode];
  const labels = report.labels_by_source ?? {};

  const tooltip = ({ active, label }: TooltipContentProps<TooltipValueType, string | number>) => {
    const row = active ? rows.find((r) => r.threshold === Number(label)) : undefined;
    if (!row) return null;
    return (
      <div className="trend-tip">
        <div className="trend-tip__day">
          {t.threshold} {formatThreshold(row.threshold)}
        </div>
        {series.map((s) => (
          <div key={s.key} className="trend-tip__row">
            <span className="chart-key" style={{ background: s.color }} />
            {s.label}
            <strong>{value(mode, row[s.key])}</strong>
          </div>
        ))}
      </div>
    );
  };

  return (
    <section className="calib-chart" aria-labelledby="calib-chart-h">
      <div className="calib-chart__head">
        <h2 id="calib-chart-h" className="h3">
          {t.title}
        </h2>
        <div role="tablist" className="seg seg--sm">
          {(["counts", "rates"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              className="seg__tab"
              onClick={() => setMode(m)}
            >
              {t.modes[m]}
            </button>
          ))}
        </div>
      </div>
      <ul className="chart-legend">
        {series.map((s) => (
          <li key={s.key}>
            <span
              className={s.dash ? "chart-key chart-key--dash" : "chart-key"}
              style={{ background: s.dash ? undefined : s.color, borderColor: s.color }}
            />
            {s.label}
            {current && <strong>{value(mode, current[s.key])}</strong>}
          </li>
        ))}
      </ul>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={rows} margin={{ top: 24, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#f4f4f5" vertical={false} />
          <XAxis
            dataKey="threshold"
            type="number"
            domain={[0.05, 0.95]}
            ticks={[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]}
            tickFormatter={(v: number) => formatThreshold(v)}
            tick={{ fontSize: 12, fill: INK }}
            tickLine={false}
            axisLine={{ stroke: AXIS }}
          />
          <YAxis
            allowDecimals={false}
            domain={mode === "rates" ? [0, 100] : [0, "auto"]}
            tickFormatter={(v: number) => (mode === "rates" ? `${v}%` : String(v))}
            tick={{ fontSize: 12, fill: INK }}
            tickLine={false}
            axisLine={false}
            width={40}
          />
          <Tooltip
            content={tooltip}
            cursor={{ stroke: "#a1a1aa", strokeWidth: 1 }}
            isAnimationActive={false}
            wrapperStyle={{ outline: "none" }}
          />
          <ReferenceLine
            x={at}
            stroke={INK}
            strokeWidth={1.5}
            label={{
              value: t.marker(formatThreshold(at)),
              position: "top",
              fill: INK,
              fontSize: 12,
              fontWeight: 600,
            }}
          />
          {series.map((s) => (
            <Line
              key={s.key}
              type="stepAfter"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={2}
              strokeDasharray={s.dash}
              dot={false}
              activeDot={{ r: 4, stroke: "#ffffff", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          ))}
          {current &&
            series.map((s) => (
              <ReferenceDot
                key={`dot-${s.key}`}
                x={at}
                y={current[s.key]}
                r={5}
                fill={s.color}
                stroke="#ffffff"
                strokeWidth={2}
              />
            ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="note">{t.caption(report.n_labels, labels.golden ?? 0, labels.analyst ?? 0)}</p>
      <details className="calib-chart__table">
        <summary>{t.table}</summary>
        <table className="hood__table">
          <thead>
            <tr>
              <th>{t.threshold}</th>
              {SERIES.counts.concat(SERIES.rates).map((s) => (
                <th key={s.key} className="hood__num">
                  {s.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows
              .filter((r) => Math.round(r.threshold * 100) % 5 === 0)
              .map((r) => (
                <tr key={r.threshold}>
                  <td>{formatThreshold(r.threshold)}</td>
                  <td className="hood__num">{formatInt(r.found)}</td>
                  <td className="hood__num">{formatInt(r.falseAlarms)}</td>
                  <td className="hood__num">{formatInt(r.missed)}</td>
                  <td className="hood__num">{value("rates", r.recall)}</td>
                  <td className="hood__num">{value("rates", r.precision)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
