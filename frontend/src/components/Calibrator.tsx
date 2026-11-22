import { lazy, Suspense, useEffect, useState } from "react";
import type { CalibrationReport } from "@/api/types";
import { useSaveThreshold } from "@/hooks/useCalibration";
import { pl } from "@/i18n/pl";
import { pointAt } from "@/lib/calibration";
import { formatThreshold } from "@/lib/format";
import { useToasts } from "@/state/toastContext";

const CalibrationChart = lazy(() => import("@/components/CalibrationChart"));

const MIN = 5;
const MAX = 95;
const toSlider = (threshold: number) => Math.min(MAX, Math.max(MIN, Math.round(threshold * 100)));

/** Threshold slider with the live sentence, the two stat cards and the chart below. */
export function Calibrator({ report }: { report: CalibrationReport }) {
  const [value, setValue] = useState(() => toSlider(report.current_threshold));
  const save = useSaveThreshold();
  const toasts = useToasts();
  useEffect(() => setValue(toSlider(report.current_threshold)), [report.current_threshold]);

  const threshold = value / 100;
  const point = pointAt(report.points, threshold);
  const total = report.n_positive;
  const negatives = Math.max(0, report.n_labels - report.n_positive);
  const found = point?.tp ?? 0;
  const fp = point?.fp ?? 0;
  const flagged = found + fp;
  const recall = total ? Math.round((found / total) * 100) : 0;
  const precision = flagged ? Math.round((found / flagged) * 100) : 100;
  const recommended = report.recommended_f2;
  const s = pl.sensitivity.sentence;

  return (
    <>
      <div className="calib-grid">
        <section className="calib">
          <div className="calib__head">
            <label htmlFor="thr" className="h3">
              {pl.sensitivity.threshold}
            </label>
            <span className="calib__value">{formatThreshold(threshold)}</span>
          </div>
          <div>
            <input
              id="thr"
              className="range"
              type="range"
              min={MIN}
              max={MAX}
              step={1}
              value={value}
              aria-valuetext={formatThreshold(threshold)}
              onChange={(event) => setValue(Number(event.target.value))}
            />
            <div className="range__ends">
              <span>{pl.sensitivity.more}</span>
              <span>{pl.sensitivity.fewer}</span>
            </div>
          </div>
          <p className="calib__sentence" aria-live="polite">
            {s.before}
            <span className="good">{s.found(found, total)}</span>
            {s.middle}
            <span className="bad">{s.fp(fp)}</span>
            {s.after(negatives)}
          </p>
          <div className="actions">
            <button
              type="button"
              className="btn btn--primary"
              disabled={save.isPending}
              onClick={() =>
                save.mutate(
                  { module: report.module, value: threshold },
                  {
                    onSuccess: () =>
                      toasts.show({
                        key: "threshold",
                        tone: "success",
                        title: pl.sensitivity.saved,
                        text: formatThreshold(threshold),
                      }),
                    onError: () =>
                      toasts.show({
                        key: "threshold",
                        tone: "danger",
                        title: pl.sensitivity.saveError,
                      }),
                  },
                )
              }
            >
              {pl.sensitivity.save}
            </button>
            <button
              type="button"
              className="btn btn--outline"
              onClick={() => setValue(toSlider(recommended))}
            >
              {pl.sensitivity.recommended(formatThreshold(recommended))}
            </button>
          </div>
        </section>
        <section className="stack-16">
          <div className="stat stat--ok">
            <div className="stat__label stat__label--strong">{pl.sensitivity.recall}</div>
            <div className="stat__value">{recall}%</div>
            <div className="stat__detail">
              {pl.sensitivity.recallDetail(found, total, Math.max(0, total - found))}
            </div>
          </div>
          <div className="stat stat--high">
            <div className="stat__label stat__label--strong">{pl.sensitivity.precision}</div>
            <div className="stat__value">{precision}%</div>
            <div className="stat__detail">{pl.sensitivity.precisionDetail(fp, flagged)}</div>
          </div>
          <p className="note">{pl.sensitivity.note}</p>
        </section>
      </div>
      <Suspense fallback={<div className="calib-chart calib-chart--loading" />}>
        <CalibrationChart report={report} threshold={threshold} />
      </Suspense>
    </>
  );
}
