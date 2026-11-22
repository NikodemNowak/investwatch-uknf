import type { FindingWithPost, KnfWarning } from "@/api/types";
import { pl } from "@/i18n/pl";
import { formatCountry, formatDate } from "@/lib/format";

/** "Na liście ostrzeżeń publicznych KNF od …" line with the entry and a link to the list. */
export function WarningLine({ warning }: { warning: KnfWarning }) {
  return (
    <div className="warning-line" role="note" data-testid="knf-warning">
      <p className="warning-line__title">{pl.finding.warning.line(formatDate(warning.as_of))}</p>
      <p className="warning-line__sub">
        {pl.finding.warning.entity(warning.name)} (
        {pl.finding.warning.match[warning.method](warning.matched_text)})
      </p>
      <p className="note">{pl.finding.warning.asOfNote}</p>
      <a href={warning.source_url} target="_blank" rel="noreferrer noopener">
        {pl.finding.warning.open}
      </a>
    </div>
  );
}

/** "Firma w rejestrze KNF" card (or "Firma fikcyjna (demo)"), with the KNF warning-list flag when the publisher is listed. */
export function FirmCard({ finding }: { finding: FindingWithPost }) {
  const firm = finding.firm;
  const warning = finding.knf_warning ? <WarningLine warning={finding.knf_warning} /> : null;
  if (!firm) {
    return (
      <section className="card">
        <h2 className="h3 card__title">{pl.finding.firmMissingTitle}</h2>
        <p>{pl.finding.firmMissing}</p>
        {warning}
      </section>
    );
  }
  const match = finding.firm_match;
  // A fictional demo firm only pretends to be in the register: no "w rejestrze KNF", no link.
  const fictional = firm.fictional === true;
  return (
    <section className="card" data-testid="firm-card">
      <h2 className="h3 card__title">
        {fictional ? pl.finding.firmFictionalTitle : pl.finding.firmTitle}
      </h2>
      {fictional && <p className="note">{pl.finding.firmFictional}</p>}
      {warning}
      <dl className="facts-list">
        <dt>{pl.finding.firmRows.name}</dt>
        <dd style={{ fontWeight: 600 }}>{firm.name}</dd>
        <dt>{pl.finding.firmRows.kind}</dt>
        <dd>{pl.firmKinds[firm.kind]}</dd>
        {firm.country && (
          <>
            <dt>{pl.finding.firmRows.country}</dt>
            <dd>{formatCountry(firm.country)}</dd>
          </>
        )}
        {match && (
          <>
            <dt>{pl.finding.firmRows.match}</dt>
            <dd>{pl.finding.match[match.method](match.matched_text)}</dd>
          </>
        )}
      </dl>
      {firm.register_url && !fictional && (
        <a className="card-link" href={firm.register_url} target="_blank" rel="noreferrer noopener">
          {pl.finding.openRegister}
        </a>
      )}
    </section>
  );
}
