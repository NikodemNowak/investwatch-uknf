import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { syncBackend } from "@/api/client";
import type { ModuleId, RiskLevel } from "@/api/types";
import { FilterBar } from "@/components/FilterBar";
import { Icon } from "@/components/Icon";
import { LoadState } from "@/components/LoadState";
import { PdfLink } from "@/components/PdfLink";
import { useFindingList } from "@/hooks/useFindingList";
import { useSummary } from "@/hooks/useSummary";
import { pl } from "@/i18n/pl";
import { csvFilename, downloadText, findingsCsv } from "@/lib/csv";
import { MODULES, RISK_LEVELS, oneOf } from "@/lib/enums";
import {
  DEFAULT_FILTERS,
  filtersQuery,
  matchesQuery,
  readFilters,
  writeFilters,
  type ResultFilters,
} from "@/lib/filters";
import { formatInt } from "@/lib/plural";
import { ReviewRow } from "@/components/ReviewRow";
import { TrendCard } from "@/components/TrendCard";

const COLUMNS = "120px minmax(0, 1fr) 196px 110px 128px 36px";
const PAGE = 50;
const RANK: Record<RiskLevel, number> = { high: 3, medium: 2, low: 1 };

/** "Do przejrzenia": findings most serious first, filtered by period, source, risk and status. */
export function ReviewPage() {
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  const module = oneOf(MODULES, params.get("rodzaj"));
  const risk = filters.risk;
  const [q, setQ] = useState(params.get("q") ?? "");
  const [limit, setLimit] = useState(PAGE);
  // Risk stays client-side: the cards count every level within the other filters.
  const serverQuery = filtersQuery(filters, { withRisk: false });
  const query = useFindingList(serverQuery);
  const summary = useSummary();

  const update = (next: URLSearchParams) => {
    setParams(next, { replace: true });
    setLimit(PAGE);
  };
  const setParam = (key: string, value: string | undefined) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    update(next);
  };
  const setFilters = (next: ResultFilters) => update(writeFilters(params, next));
  const clearAll = () => {
    setQ("");
    const next = writeFilters(params, DEFAULT_FILTERS);
    next.delete("rodzaj");
    next.delete("q");
    update(next);
  };

  const all = useMemo(
    () =>
      [...(query.data?.items ?? [])].sort(
        (a, b) =>
          RANK[b.risk_level] - RANK[a.risk_level] ||
          b.score - a.score ||
          b.created_at.localeCompare(a.created_at),
      ),
    [query.data],
  );
  const searched = useMemo(
    () => (q.trim() ? all.filter((f) => matchesQuery(f, { q })) : all),
    [all, q],
  );
  const inModule = module ? searched.filter((f) => f.module === module) : searched;
  const rows = risk ? inModule.filter((f) => f.risk_level === risk) : inModule;
  const countBy = (level: RiskLevel) => inModule.filter((f) => f.risk_level === level).length;
  const moduleCount = (id: ModuleId | undefined) =>
    id ? searched.filter((f) => f.module === id).length : searched.length;
  const truncated = query.data && query.data.total > query.data.items.length;

  const exportCsv = () => {
    const url = module
      ? syncBackend()?.reportCsvUrl(module, {
          ...serverQuery,
          risk_level: risk,
          q: q || undefined,
        })
      : null;
    if (url) {
      window.location.assign(url);
      return;
    }
    downloadText(findingsCsv(rows), csvFilename("do-przejrzenia"));
  };

  const open = summary.data?.open_findings;
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="title">{pl.review.title}</h1>
          <p className="lead">{open !== undefined ? pl.review.lead(open) : " "}</p>
        </div>
        <div className="page-head__actions">
          <PdfLink
            href={
              syncBackend()?.reportPdfUrl(module, {
                ...serverQuery,
                risk_level: risk,
                q: q || undefined,
              }) ?? null
            }
            label={pl.pdf.module}
          />
          <button
            type="button"
            className="btn btn--outline btn--md"
            onClick={exportCsv}
            disabled={!query.data}
          >
            <Icon name="download" size={16} />
            {pl.review.csv}
          </button>
        </div>
      </div>

      <div className="stats stats--3">
        {RISK_LEVELS.map((level) => (
          <button
            key={level}
            type="button"
            className={`stat stat--${level}`}
            aria-pressed={risk === level}
            title={pl.review.filterRisk(pl.riskCards[level])}
            onClick={() => setParam("ryzyko", risk === level ? undefined : level)}
          >
            <div className="stat__label stat__label--strong">{pl.riskCards[level]}</div>
            <div className="stat__value">{query.data ? formatInt(countBy(level)) : "–"}</div>
          </button>
        ))}
      </div>

      <TrendCard module={module} />

      <div className="results">
        <div className="toolbar">
          <div role="tablist" className="seg">
            {([undefined, ...MODULES] as (ModuleId | undefined)[]).map((id) => (
              <button
                key={id ?? "all"}
                type="button"
                role="tab"
                aria-selected={module === id}
                className="seg__tab seg__tab--count"
                onClick={() => setParam("rodzaj", id)}
              >
                {id ? pl.moduleTabs[id] : pl.review.all}
                <span className="seg__count">{query.data ? formatInt(moduleCount(id)) : "–"}</span>
              </button>
            ))}
          </div>
          <label className="search">
            <Icon name="search" size={16} />
            <span className="sr-only">{pl.review.search}</span>
            <input
              type="search"
              placeholder={pl.review.searchPlaceholder}
              value={q}
              onChange={(event) => {
                setQ(event.target.value);
                setLimit(PAGE);
              }}
            />
          </label>
        </div>

        <FilterBar
          filters={filters}
          onChange={setFilters}
          results={query.data ? rows.length : undefined}
          extraActive={Number(Boolean(q.trim())) + Number(module !== undefined)}
          onClear={clearAll}
        />
      </div>

      {query.isError ? (
        <LoadState error onRetry={() => void query.refetch()} />
      ) : !query.data ? (
        <LoadState />
      ) : rows.length === 0 ? (
        <LoadState empty={pl.review.empty} />
      ) : (
        <div
          className="table"
          style={{ ["--cols" as string]: COLUMNS, ["--row-h" as string]: "80px" }}
        >
          <div className="table__head">
            <span>{pl.review.columns.risk}</span>
            <span>{pl.review.columns.material}</span>
            <span>{pl.review.columns.kind}</span>
            <span>{pl.review.columns.source}</span>
            <span className="table__cell--right">{pl.review.columns.detected}</span>
            <span />
          </div>
          {rows.slice(0, limit).map((finding) => (
            <ReviewRow key={finding.id} finding={finding} />
          ))}
          {rows.length > limit && (
            <div className="table__more">
              <button
                type="button"
                className="btn btn--outline btn--md"
                onClick={() => setLimit((n) => n + PAGE)}
              >
                {pl.review.showMore(Math.min(PAGE, rows.length - limit))}
              </button>
            </div>
          )}
          {truncated && rows.length <= limit && (
            <div className="table__more">
              {pl.review.truncated(query.data.items.length, query.data.total)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
