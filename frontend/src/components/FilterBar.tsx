import { useState, type ReactNode } from "react";
import type { Platform, RiskLevel } from "@/api/types";
import { Dropdown } from "@/components/Dropdown";
import { Icon, type IconName } from "@/components/Icon";
import { pl } from "@/i18n/pl";
import { PLATFORMS, RISK_LEVELS } from "@/lib/enums";
import {
  DEFAULT_FILTERS,
  PERIODS,
  STATUS_FILTERS,
  activeFilterCount,
  type ResultFilters,
} from "@/lib/filters";
import { formatDate } from "@/lib/format";

interface FilterBarProps {
  filters: ResultFilters;
  onChange: (next: ResultFilters) => void;
  /** Rows matching every filter (hidden while unknown). */
  results?: number;
  /** "12 wyników" by default; the aggregator counts entities. */
  resultsLabel?: (n: number) => string;
  /** Other active filters of the page (search, module tab) that "Wyczyść filtry" also resets. */
  extraActive?: number;
  /** Reset everything; defaults to resetting the bar only. */
  onClear?: () => void;
}

function Trigger({ icon, label, value }: { icon?: IconName; label: string; value: string }) {
  return (
    <>
      {icon && <Icon name={icon} size={16} />}
      <span className="filter-btn__label">{label}</span>
      <span className="filter-btn__value">{value}</span>
      <Icon name="chevron" size={14} />
    </>
  );
}

function Option({
  selected,
  onSelect,
  children,
  role = "menuitemradio",
}: {
  selected: boolean;
  onSelect: () => void;
  children: ReactNode;
  role?: "menuitemradio" | "menuitemcheckbox";
}) {
  return (
    <button
      type="button"
      role={role}
      aria-checked={selected}
      className="menu__item"
      onClick={onSelect}
    >
      <span className="menu__check">{selected && <Icon name="check" size={14} />}</span>
      <span className="menu__text">{children}</span>
    </button>
  );
}

function periodValue(filters: ResultFilters): string {
  if (filters.period !== "custom") return pl.filters.periods[filters.period];
  const { from, to } = filters;
  if (from && to) return pl.filters.range(formatDate(from), formatDate(to));
  if (from) return pl.filters.since(formatDate(from));
  if (to) return pl.filters.until(formatDate(to));
  return pl.filters.periods.custom;
}

function sourceValue(platforms: Platform[]): string {
  const [first] = platforms;
  return first ? pl.filters.sources(pl.platforms[first], platforms.length - 1) : pl.filters.any;
}

function RangeForm({
  filters,
  onApply,
}: {
  filters: ResultFilters;
  onApply: (from: string | undefined, to: string | undefined) => void;
}) {
  const [from, setFrom] = useState(filters.from ?? "");
  const [to, setTo] = useState(filters.to ?? "");
  const invalid = Boolean(from && to && from > to);
  return (
    <form
      className="range-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!invalid) onApply(from || undefined, to || undefined);
      }}
    >
      <label className="range-form__field">
        <span>{pl.filters.from}</span>
        <input
          type="date"
          value={from}
          max={to || undefined}
          onChange={(e) => setFrom(e.target.value)}
        />
      </label>
      <label className="range-form__field">
        <span>{pl.filters.to}</span>
        <input
          type="date"
          value={to}
          min={from || undefined}
          onChange={(e) => setTo(e.target.value)}
        />
      </label>
      <button
        type="submit"
        className="btn btn--primary btn--sm"
        disabled={invalid || (!from && !to)}
      >
        {pl.filters.apply}
      </button>
    </form>
  );
}

/** Filters of the result lists: period, source, risk and status, with "Wyczyść filtry". */
export function FilterBar({
  filters,
  onChange,
  results,
  resultsLabel = pl.filters.results,
  extraActive = 0,
  onClear,
}: FilterBarProps) {
  const set = (patch: Partial<ResultFilters>) => onChange({ ...filters, ...patch });
  const active = activeFilterCount(filters) + extraActive;
  const cls = (on: boolean) => (on ? "filter-btn filter-btn--active" : "filter-btn");
  const togglePlatform = (platform: Platform) =>
    set({
      platforms: filters.platforms.includes(platform)
        ? filters.platforms.filter((p) => p !== platform)
        : PLATFORMS.filter((p) => p === platform || filters.platforms.includes(p)),
    });

  return (
    <div className="filters" role="group" aria-label={pl.filters.label}>
      <Dropdown
        buttonClassName={cls(filters.period !== "all")}
        testId="filter-period"
        label={<Trigger icon="calendar" label={pl.filters.period} value={periodValue(filters)} />}
      >
        {(close) => (
          <div className="menu" role="menu" aria-label={pl.filters.period}>
            {PERIODS.filter((p) => p !== "custom").map((period) => (
              <Option
                key={period}
                selected={filters.period === period}
                onSelect={() => {
                  set({ period, from: undefined, to: undefined });
                  close();
                }}
              >
                {pl.filters.periods[period]}
              </Option>
            ))}
            <div className="menu__sep" />
            <div className="menu__title">{pl.filters.periods.custom}</div>
            <RangeForm
              filters={filters}
              onApply={(from, to) => {
                set({ period: "custom", from, to });
                close();
              }}
            />
          </div>
        )}
      </Dropdown>

      <Dropdown
        buttonClassName={cls(filters.platforms.length > 0)}
        testId="filter-source"
        label={<Trigger label={pl.filters.source} value={sourceValue(filters.platforms)} />}
      >
        {() => (
          <div className="menu" role="menu" aria-label={pl.filters.source}>
            <Option
              selected={filters.platforms.length === 0}
              onSelect={() => set({ platforms: [] })}
            >
              {pl.filters.anySource}
            </Option>
            <div className="menu__sep" />
            {PLATFORMS.map((platform) => (
              <Option
                key={platform}
                role="menuitemcheckbox"
                selected={filters.platforms.includes(platform)}
                onSelect={() => togglePlatform(platform)}
              >
                {pl.platforms[platform]}
              </Option>
            ))}
          </div>
        )}
      </Dropdown>

      <Dropdown
        buttonClassName={cls(filters.risk !== undefined)}
        testId="filter-risk"
        label={
          <Trigger
            label={pl.filters.risk}
            value={filters.risk ? pl.risk[filters.risk] : pl.filters.any}
          />
        }
      >
        {(close) => (
          <div className="menu" role="menu" aria-label={pl.filters.risk}>
            {([undefined, ...RISK_LEVELS] as (RiskLevel | undefined)[]).map((risk) => (
              <Option
                key={risk ?? "any"}
                selected={filters.risk === risk}
                onSelect={() => {
                  set({ risk });
                  close();
                }}
              >
                {risk ? (
                  <span className={`menu__risk menu__risk--${risk}`}>
                    <span className="dot" />
                    {pl.risk[risk]}
                  </span>
                ) : (
                  pl.filters.any
                )}
              </Option>
            ))}
          </div>
        )}
      </Dropdown>

      <Dropdown
        buttonClassName={cls(filters.status !== "open")}
        testId="filter-status"
        label={<Trigger label={pl.filters.status} value={pl.filters.statuses[filters.status]} />}
      >
        {(close) => (
          <div className="menu" role="menu" aria-label={pl.filters.status}>
            {STATUS_FILTERS.map((status) => (
              <Option
                key={status}
                selected={filters.status === status}
                onSelect={() => {
                  set({ status });
                  close();
                }}
              >
                {pl.filters.statuses[status]}
                {pl.filters.statusHints[status] && (
                  <span className="menu__hint">{pl.filters.statusHints[status]}</span>
                )}
              </Option>
            ))}
          </div>
        )}
      </Dropdown>

      <div className="filters__end">
        {results !== undefined && (
          <span className="filters__count" data-testid="results-count">
            {resultsLabel(results)}
          </span>
        )}
        <button
          type="button"
          className="link-button"
          disabled={active === 0}
          onClick={() => (onClear ? onClear() : onChange(DEFAULT_FILTERS))}
        >
          {pl.filters.clear}
        </button>
      </div>
    </div>
  );
}
