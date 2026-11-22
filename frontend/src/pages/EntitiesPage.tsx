import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { ModuleId } from "@/api/types";
import { EntityRow } from "@/components/EntityRow";
import { FilterBar } from "@/components/FilterBar";
import { Icon } from "@/components/Icon";
import { LoadState } from "@/components/LoadState";
import { useDebounced } from "@/hooks/useDebounced";
import { useEntities } from "@/hooks/useEntities";
import { pl } from "@/i18n/pl";
import { MODULES, oneOf } from "@/lib/enums";
import {
  DEFAULT_FILTERS,
  filtersQuery,
  readFilters,
  writeFilters,
  type ResultFilters,
} from "@/lib/filters";
import { formatInt } from "@/lib/plural";

const COLUMNS = "minmax(0, 1fr) 150px 48px 48px 48px 104px 110px";
const PAGE = 50;

/** "Agregator wyników": one object per firm or advertiser over its M1/M2/M3 findings. */
export function EntitiesPage() {
  const [params, setParams] = useSearchParams();
  const filters = readFilters(params);
  const module = oneOf(MODULES, params.get("rodzaj"));
  const [q, setQ] = useState(params.get("q") ?? "");
  const search = useDebounced(q.trim(), 250);
  const [limit, setLimit] = useState(PAGE);
  const query = useEntities({ ...filtersQuery(filters), q: search || undefined });

  const update = (next: URLSearchParams) => {
    setParams(next, { replace: true });
    setLimit(PAGE);
  };
  const setFilters = (next: ResultFilters) => update(writeFilters(params, next));
  const setModule = (id: ModuleId | undefined) => {
    const next = new URLSearchParams(params);
    if (id) next.set("rodzaj", id);
    else next.delete("rodzaj");
    update(next);
  };
  const clearAll = () => {
    setQ("");
    const next = writeFilters(params, DEFAULT_FILTERS);
    next.delete("rodzaj");
    update(next);
  };

  const all = query.data?.items ?? [];
  const rows = module ? all.filter((e) => e.modules[module] > 0) : all;
  const moduleCount = (id: ModuleId | undefined) =>
    id ? all.filter((e) => e.modules[id] > 0).length : all.length;
  const stat = (n: number) => (query.data ? formatInt(n) : "–");

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="title">{pl.entities.title}</h1>
          <p className="lead lead--wide">{pl.entities.lead}</p>
        </div>
      </div>

      <div className="stats stats--4">
        <div className="stat">
          <div className="stat__label">{pl.entities.stats.entities}</div>
          <div className="stat__value">{stat(rows.length)}</div>
        </div>
        <div className="stat">
          <div className="stat__label">{pl.entities.stats.inRegister}</div>
          <div className="stat__value">
            {stat(rows.filter((e) => e.knf_register === "knf").length)}
          </div>
        </div>
        <div className="stat">
          <div className="stat__label">{pl.entities.stats.warning}</div>
          <div className="stat__value">{stat(rows.filter((e) => e.knf_warning).length)}</div>
        </div>
        <div className="stat">
          <div className="stat__label">{pl.entities.stats.multi}</div>
          <div className="stat__value">
            {stat(rows.filter((e) => MODULES.filter((m) => e.modules[m] > 0).length > 1).length)}
          </div>
        </div>
      </div>

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
                onClick={() => setModule(id)}
              >
                {id ? pl.moduleTabs[id] : pl.review.all}
                <span className="seg__count">{query.data ? formatInt(moduleCount(id)) : "–"}</span>
              </button>
            ))}
          </div>
          <label className="search">
            <Icon name="search" size={16} />
            <span className="sr-only">{pl.entities.search}</span>
            <input
              type="search"
              placeholder={pl.entities.searchPlaceholder}
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
          resultsLabel={pl.entities.count}
          extraActive={Number(Boolean(q.trim())) + Number(module !== undefined)}
          onClear={clearAll}
        />
      </div>

      {query.isError ? (
        <LoadState error onRetry={() => void query.refetch()} />
      ) : !query.data ? (
        <LoadState />
      ) : rows.length === 0 ? (
        <LoadState empty={pl.entities.empty} />
      ) : (
        <div className="stack-12">
          <div
            className="table"
            style={{ ["--cols" as string]: COLUMNS, ["--row-h" as string]: "80px" }}
          >
            <div className="table__head">
              <span>{pl.entities.columns.entity}</span>
              <span>{pl.entities.columns.risk}</span>
              {MODULES.map((m) => (
                <span key={m} className="num-cell" title={pl.moduleTabs[m]}>
                  {pl.entities.moduleShort[m]}
                </span>
              ))}
              <span className="num-cell">{pl.entities.columns.occurrences}</span>
              <span className="table__cell--right">{pl.entities.columns.latest}</span>
            </div>
            {rows.slice(0, limit).map((entity) => (
              <EntityRow key={entity.key} entity={entity} />
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
          </div>
          <p className="note">
            {pl.entities.moduleLegend}
            {query.data.truncated && ` ${pl.entities.truncated}`}
          </p>
        </div>
      )}
    </div>
  );
}
