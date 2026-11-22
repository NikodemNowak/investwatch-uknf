import { Icon } from "@/components/Icon";
import { pl } from "@/i18n/pl";
import type { FindingWithPost } from "@/api/types";
import { countryGenitive, subjectOf } from "@/lib/problems";
import { primaryFinding } from "@/lib/verdict";
import { domainOf } from "@/lib/format";
import type { CheckRun } from "@/state/checkContext";

interface FactsProps {
  post: NonNullable<CheckRun["post"]>;
  findings: FindingWithPost[];
  analyzed: boolean;
}

/** "Kto reklamuje" and "Rejestr KNF" cards of a check. */
export function Facts({ post, findings, analyzed }: FactsProps) {
  const primary = primaryFinding(findings);
  const withFirm = [...findings].sort((a, b) => b.score - a.score).find((f) => f.firm);
  const firm = withFirm?.firm ?? null;
  const ownSite = withFirm?.firm_match?.on === "author";
  const who = primary
    ? subjectOf({ ...primary, post })
    : post.platform === "web"
      ? domainOf(post.url)
      : post.author;
  const whoSub = !analyzed
    ? pl.platformLong[post.platform]
    : primary?.module === "m1_third_party_ad"
      ? pl.check.thirdParty
      : ownSite
        ? pl.check.ownSite
        : pl.platformLong[post.platform];
  const unregistered = findings.some(
    (f) => f.module === "m3_shadow_advisory" && f.risk_level !== "low",
  );

  return (
    <div className="facts">
      <div className="fact">
        <div className="fact__label">{pl.check.who}</div>
        <div className="fact__value">
          <span title={who}>{who}</span>
        </div>
        <div className="fact__sub">{whoSub}</div>
      </div>
      <div className="fact">
        <div className="fact__label">{pl.check.registry}</div>
        {!analyzed ? (
          <div className="fact__value fact__value--muted">
            <Icon name="spinner" size={18} />
            <span>{pl.check.registryChecking}</span>
          </div>
        ) : firm?.fictional ? (
          <>
            <div className="fact__value" data-testid="registry-fictional">
              <Icon name="alert" size={18} color="#b45309" />
              <span title={firm.name}>{firm.name}</span>
            </div>
            <div className="fact__sub">{pl.check.registryFictional}</div>
          </>
        ) : firm ? (
          <>
            <div className="fact__value">
              <Icon name="check" size={18} color="#15803d" />
              <span title={firm.name}>{firm.name}</span>
            </div>
            <div className="fact__sub">
              {pl.check.firmFrom(countryGenitive(firm.country), firm.kind)}
            </div>
          </>
        ) : unregistered ? (
          <>
            <div className="fact__value">
              <Icon name="cross" size={16} color="#b91c1c" />
              <span>{pl.check.registryMissing}</span>
            </div>
            <div className="fact__sub">{pl.check.registryMissingText}</div>
          </>
        ) : (
          <>
            <div className="fact__value fact__value--muted">
              <span>{pl.check.registryNone}</span>
            </div>
            <div className="fact__sub">{pl.check.registryNoneText}</div>
          </>
        )}
      </div>
    </div>
  );
}
