import { StepIcon } from "@/components/StepIcon";
import { pl } from "@/i18n/pl";
import type { CheckProgress } from "@/lib/checkSteps";
import { formatSeconds } from "@/lib/format";

interface ProgressCardProps {
  progress: CheckProgress;
  elapsedMs: number;
}

/** "Postęp": bar plus six equal-height step rows. */
export function ProgressCard({ progress, elapsedMs }: ProgressCardProps) {
  const percent = Math.round((progress.done / progress.total) * 100);
  return (
    <section className="card" aria-labelledby="progress-h">
      <div className="progress__head">
        <h2 id="progress-h" className="h3">
          {pl.check.progress}
        </h2>
        <span className="progress__count">
          {pl.check.progressCount(progress.done, progress.total, formatSeconds(elapsedMs))}
        </span>
      </div>
      <div
        className="progress__bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={progress.total}
        aria-valuenow={progress.done}
        aria-label={pl.check.progress}
      >
        <div className="progress__fill" style={{ width: `${percent}%` }} />
      </div>
      <ol className="steps" aria-live="polite">
        {progress.steps.map((step) => (
          <li key={step.key} className={`step step--${step.state}`}>
            <StepIcon state={step.state} />
            <div className="step__text">
              <div className="step__label">{step.label}</div>
              {step.detail && (
                <div className="step__detail" title={step.detail}>
                  {step.detail}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
