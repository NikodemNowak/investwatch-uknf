import { Icon } from "@/components/Icon";

export type VerdictTone = "high" | "medium" | "low" | "info" | "neutral";

interface VerdictBannerProps {
  tone: VerdictTone;
  /** Small line above the headline ("Wynik wstępny (czeka na ocenę modelu)"). */
  label?: string;
  headline: string;
  text?: string;
  /** Right-hand figure, e.g. the risk score (rules + classifier, 0-1). */
  score?: { value: string; label: string };
}

const CIRCLE: Record<VerdictTone, string> = {
  high: "circle--solid-red",
  medium: "circle--solid-amber",
  low: "circle--solid-green",
  info: "circle--solid-blue",
  neutral: "circle--solid-grey",
};

/** Large coloured result banner with a 48 px icon. */
export function VerdictBanner({ tone, label, headline, text, score }: VerdictBannerProps) {
  return (
    <div className={`verdict verdict--${tone}`} role="status">
      <span className={`circle circle--lg ${CIRCLE[tone]}`}>
        {(tone === "high" || tone === "medium") && <Icon name="alert" size={24} color="#ffffff" />}
        {tone === "low" && <Icon name="check" size={24} color="#ffffff" strokeWidth={2.8} />}
        {tone === "info" && <Icon name="spinner" size={26} />}
        {tone === "neutral" && <Icon name="cross" size={20} color="#ffffff" strokeWidth={3} />}
      </span>
      <div>
        {label && <div className="verdict__label">{label}</div>}
        <div className="verdict__headline">{headline}</div>
        {text && <div className="verdict__text">{text}</div>}
      </div>
      {score ? (
        <div className="verdict__score">
          <div className="verdict__score-value">{score.value}</div>
          <div className="verdict__score-label">{score.label}</div>
        </div>
      ) : (
        <span />
      )}
    </div>
  );
}
