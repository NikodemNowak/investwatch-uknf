import type {
  DateString,
  FindingPage,
  FindingQuery,
  FindingWithPost,
  Platform,
  RiskLevel,
  Status,
} from "@/api/types";
import { PLATFORMS, RISK_LEVELS, oneOf } from "@/lib/enums";

export const DEFAULT_PAGE_SIZE = 20;

/** A one-or-many query value as a list (undefined and `[]` both mean "any"). */
export function asList<T>(value: T | T[] | undefined): T[] {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

const allows = <T>(value: T | T[] | undefined, actual: T | undefined): boolean => {
  const list = asList(value);
  return list.length === 0 || (actual !== undefined && list.includes(actual));
};

/** True when a finding satisfies every set field of the query (pagination ignored). */
export function matchesQuery(item: FindingWithPost, query: FindingQuery): boolean {
  if (query.module && item.module !== query.module) return false;
  if (!allows(query.risk_level, item.risk_level)) return false;
  if (!allows(query.status, item.status)) return false;
  if (!allows(query.platform, item.post?.platform)) return false;
  const day = item.created_at.slice(0, 10);
  if (query.from && day < query.from) return false;
  if (query.to && day > query.to) return false;
  if (query.q) {
    const needle = query.q.trim().toLocaleLowerCase("pl");
    if (needle) {
      const haystack = [
        item.firm?.name,
        item.advertiser,
        item.post?.author,
        item.post?.url,
        item.explanation,
        ...item.quotes,
      ]
        .filter((part): part is string => typeof part === "string")
        .join("\n")
        .toLocaleLowerCase("pl");
      if (!haystack.includes(needle)) return false;
    }
  }
  return true;
}

/** Filter, sort (newest first, then highest score) and paginate, as `GET /api/findings` does. */
export function queryFindings(items: FindingWithPost[], query: FindingQuery): FindingPage {
  const page = Math.max(1, query.page ?? 1);
  const pageSize = Math.max(1, query.page_size ?? DEFAULT_PAGE_SIZE);
  const matched = items
    .filter((item) => matchesQuery(item, query))
    .sort((a, b) =>
      query.sort === "score"
        ? b.score - a.score || b.created_at.localeCompare(a.created_at)
        : b.created_at.localeCompare(a.created_at) || b.score - a.score,
    );
  const start = (page - 1) * pageSize;
  return {
    items: matched.slice(start, start + pageSize),
    total: matched.length,
    page,
    page_size: pageSize,
  };
}

/** Drop empty values so the query maps 1:1 to URL search params and cache keys. */
export function compactQuery<T extends object>(query: T): Partial<T> {
  const out: Partial<T> = {};
  for (const [key, value] of Object.entries(query)) {
    const empty = Array.isArray(value) && value.length === 0;
    if (value !== undefined && value !== null && value !== "" && !empty) {
      (out as Record<string, unknown>)[key] = value;
    }
  }
  return out;
}

/* ---------- filter bar state, kept in the URL ---------- */

export type PeriodPreset = "all" | "today" | "7d" | "30d" | "custom";
/** `open` = new + in review (the default triage queue); `all` = every status. */
export type StatusFilter = "open" | Status | "all";

/** What the filter bar selects; module tabs and search live beside it. */
export interface ResultFilters {
  period: PeriodPreset;
  /** Custom range bounds (ISO dates), used when `period` is `custom`. */
  from?: DateString;
  to?: DateString;
  platforms: Platform[];
  risk?: RiskLevel;
  status: StatusFilter;
}

export const PERIODS: PeriodPreset[] = ["all", "today", "7d", "30d", "custom"];
export const STATUS_FILTERS: StatusFilter[] = [
  "open",
  "new",
  "in_review",
  "confirmed",
  "dismissed",
  "all",
];
export const DEFAULT_FILTERS: ResultFilters = { period: "all", platforms: [], status: "open" };

/** URL spellings (Polish, like the other params of the page). */
const PERIOD_PARAM: Record<PeriodPreset, string> = {
  all: "",
  today: "dzis",
  "7d": "7-dni",
  "30d": "30-dni",
  custom: "zakres",
};
const STATUS_PARAM: Record<StatusFilter, string> = {
  open: "",
  new: "nowe",
  in_review: "w-trakcie",
  confirmed: "potwierdzone",
  dismissed: "odrzucone",
  all: "wszystkie",
};
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

function fromParam<T extends string>(
  table: Record<T, string>,
  value: string | null,
): T | undefined {
  if (!value) return undefined;
  return (Object.keys(table) as T[]).find((key) => table[key] === value);
}

/** Read the filter bar state from URL params (unknown values fall back to the defaults). */
export function readFilters(params: URLSearchParams): ResultFilters {
  const from = params.get("od") ?? undefined;
  const to = params.get("do") ?? undefined;
  const platforms = (params.get("zrodlo") ?? "")
    .split(",")
    .map((value) => oneOf(PLATFORMS, value))
    .filter((value): value is Platform => value !== undefined);
  return {
    period: fromParam(PERIOD_PARAM, params.get("okres")) ?? "all",
    from: from && ISO_DAY.test(from) ? from : undefined,
    to: to && ISO_DAY.test(to) ? to : undefined,
    platforms: PLATFORMS.filter((p) => platforms.includes(p)),
    risk: oneOf(RISK_LEVELS, params.get("ryzyko")),
    status: fromParam(STATUS_PARAM, params.get("status")) ?? "open",
  };
}

/** Write the filter bar state into a copy of `params` (defaults are left out). */
export function writeFilters(params: URLSearchParams, filters: ResultFilters): URLSearchParams {
  const next = new URLSearchParams(params);
  const set = (key: string, value: string | undefined) => {
    if (value) next.set(key, value);
    else next.delete(key);
  };
  set("okres", PERIOD_PARAM[filters.period]);
  set("od", filters.period === "custom" ? filters.from : undefined);
  set("do", filters.period === "custom" ? filters.to : undefined);
  set("zrodlo", filters.platforms.join(","));
  set("ryzyko", filters.risk);
  set("status", STATUS_PARAM[filters.status]);
  return next;
}

/** Number of filter bar fields that differ from the defaults. */
export function activeFilterCount(filters: ResultFilters): number {
  return (
    Number(filters.period !== "all") +
    Number(filters.platforms.length > 0) +
    Number(filters.risk !== undefined) +
    Number(filters.status !== "open")
  );
}

const isoDay = (date: Date): DateString => {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
};

/** The inclusive date range of a period, as ISO dates (`today` is the viewer's local day). */
export function periodRange(
  filters: Pick<ResultFilters, "period" | "from" | "to">,
  today: Date = new Date(),
): { from?: DateString; to?: DateString } {
  const daysBack = (n: number) => isoDay(new Date(today.getTime() - n * 86_400_000));
  switch (filters.period) {
    case "today":
      return { from: isoDay(today), to: isoDay(today) };
    case "7d":
      return { from: daysBack(6), to: isoDay(today) };
    case "30d":
      return { from: daysBack(29), to: isoDay(today) };
    case "custom":
      return { from: filters.from, to: filters.to };
    default:
      return {};
  }
}

/** Statuses a status filter stands for (empty: any). */
export function statusesOf(filter: StatusFilter): Status[] {
  if (filter === "all") return [];
  return filter === "open" ? ["new", "in_review"] : [filter];
}

/** Query params of `GET /api/findings` / `GET /api/entities` for the filter bar state. */
export function filtersQuery(
  filters: ResultFilters,
  { withRisk = true, today = new Date() }: { withRisk?: boolean; today?: Date } = {},
): FindingQuery {
  const range = periodRange(filters, today);
  return compactQuery({
    from: range.from,
    to: range.to,
    platform: filters.platforms,
    status: statusesOf(filters.status),
    risk_level: withRisk ? filters.risk : undefined,
  });
}
