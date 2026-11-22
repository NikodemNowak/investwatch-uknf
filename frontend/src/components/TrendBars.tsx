import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipContentProps, TooltipValueType } from "recharts";
import { pl } from "@/i18n/pl";
import { formatInt } from "@/lib/plural";
import type { TrendDay } from "@/lib/trend";

// Same tokens as the risk pills (styles/app.css); SVG fills cannot read CSS variables in every
// browser's export path, so the values are repeated here.
const HIGH = "#dc2626";
const MEDIUM = "#d97706";
const INK = "#3f3f46";
const AXIS = "#e4e4e7";

/** Stacked bars per bucket (Recharts): high risk at the baseline, medium on top. Lazy-loaded. */
export default function TrendBars({
  days,
  label,
}: {
  days: TrendDay[];
  /** Axis and tooltip label of a bucket ("21.11" or "15:00"). */
  label: (key: string) => string;
}) {
  const byDay = new Map(days.map((d) => [d.day, d]));

  const tooltip = ({
    active,
    label: key,
  }: TooltipContentProps<TooltipValueType, string | number>) => {
    const day = active && typeof key === "string" ? byDay.get(key) : undefined;
    if (!day) return null;
    return (
      <div className="trend-tip">
        <div className="trend-tip__day">{label(day.day)}</div>
        <div className="trend-tip__row">
          <span className="trend-key trend-key--high" />
          {pl.review.trend.high}
          <strong>{formatInt(day.high)}</strong>
        </div>
        <div className="trend-tip__row">
          <span className="trend-key trend-key--medium" />
          {pl.review.trend.medium}
          <strong>{formatInt(day.medium)}</strong>
        </div>
        <div className="trend-tip__row trend-tip__row--sum">
          {pl.review.trend.sum}
          <strong>{formatInt(day.high + day.medium)}</strong>
        </div>
      </div>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={148}>
      <BarChart data={days} margin={{ top: 8, right: 0, bottom: 0, left: 0 }} barCategoryGap="28%">
        <XAxis
          dataKey="day"
          tickFormatter={label}
          tick={{ fontSize: 12, fill: INK }}
          tickLine={false}
          axisLine={{ stroke: AXIS }}
          interval="preserveStartEnd"
          minTickGap={12}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fontSize: 12, fill: INK }}
          tickLine={false}
          axisLine={false}
          tickCount={3}
          width={32}
        />
        <Tooltip
          content={tooltip}
          cursor={{ fill: "#f4f4f5" }}
          isAnimationActive={false}
          wrapperStyle={{ outline: "none" }}
        />
        <Bar
          dataKey="high"
          stackId="risk"
          fill={HIGH}
          stroke="#ffffff"
          strokeWidth={1}
          isAnimationActive={false}
        />
        <Bar
          dataKey="medium"
          stackId="risk"
          fill={MEDIUM}
          stroke="#ffffff"
          strokeWidth={1}
          radius={[4, 4, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
