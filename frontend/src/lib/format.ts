import { pl } from "@/i18n/pl";

const decimal = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2 });
const oneDecimal = new Intl.NumberFormat("pl-PL", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const time = new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit" });
const dayMonth = new Intl.DateTimeFormat("pl-PL", { day: "numeric", month: "long" });
const fullDate = new Intl.DateTimeFormat("pl-PL", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});
const shortDay = new Intl.DateTimeFormat("pl-PL", { day: "2-digit", month: "2-digit" });

/** Score in [0, 1] as "0,94"; truncated, so 0.999 never reads as a certain "1,00". */
export const formatScore = (value: number): string =>
  (Math.floor(value * 100 + 1e-9) / 100).toFixed(2).replace(".", ",");
/** Threshold in [0, 1] as "0,60" (rounded). */
export const formatThreshold = (value: number): string => value.toFixed(2).replace(".", ",");
/** Polish number formatting with up to 2 decimals. */
export const formatNumber = (value: number): string => decimal.format(value);
/** Seconds with one decimal: "1,4". */
export const formatSeconds = (ms: number): string => oneDecimal.format(Math.max(0, ms) / 1000);
/** Contrast ratio as "1,7 : 1" (spaced) or "1,7:1" (compact). */
export const formatContrast = (value: number, spaced = false): string => {
  const text = oneDecimal.format(Math.floor(value * 10) / 10);
  return spaced ? `${text} : 1` : `${text}:1`;
};
/** "08:10". */
export const formatTime = (iso: string): string => time.format(new Date(iso));

/** Whole calendar days between two instants, in the viewer's time zone. */
function calendarDays(iso: string, now: number): number {
  const a = new Date(iso);
  const b = new Date(now);
  const startA = new Date(a.getFullYear(), a.getMonth(), a.getDate()).getTime();
  const startB = new Date(b.getFullYear(), b.getMonth(), b.getDate()).getTime();
  return Math.round((startB - startA) / 86_400_000);
}

/** "21 listopada, 08:10". */
export const formatDayTime = (iso: string): string =>
  `${dayMonth.format(new Date(iso))}, ${formatTime(iso)}`;

/** "6 godz. temu", "wczoraj", "3 dni temu", then "14 listopada". */
export function formatAgo(iso: string, now: number = Date.now()): string {
  const minutes = Math.floor((now - Date.parse(iso)) / 60_000);
  if (minutes < 1) return pl.common.justNow;
  if (minutes < 60) return pl.common.minutesAgo(minutes);
  const days = calendarDays(iso, now);
  if (days <= 0 || minutes < 6 * 60) return pl.common.hoursAgo(Math.floor(minutes / 60));
  if (days === 1) return pl.common.yesterday;
  if (days < 7) return pl.common.daysAgo(days);
  return dayMonth.format(new Date(iso));
}

/** "dziś, 04:12", "wczoraj, 18:40", "14 listopada"; null as "nigdy". */
export function formatLastRun(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return pl.common.never;
  const days = calendarDays(iso, now);
  if (days === 0) return `${pl.common.today}, ${formatTime(iso)}`;
  if (days === 1) return `${pl.common.yesterday}, ${formatTime(iso)}`;
  return dayMonth.format(new Date(iso));
}

/** "dziś o 04:17" / "wczoraj o 18:40" / "14 listopada o 04:17". */
export function formatWhen(iso: string, now: number = Date.now()): string {
  const days = calendarDays(iso, now);
  const day =
    days === 0
      ? pl.common.today
      : days === 1
        ? pl.common.yesterday
        : dayMonth.format(new Date(iso));
  return `${day} o ${formatTime(iso)}`;
}

/** Time for history rows: "08:10" today, else "20.11, 08:10". */
export function formatHistoryTime(iso: string, now: number = Date.now()): string {
  return calendarDays(iso, now) === 0
    ? formatTime(iso)
    : `${shortDay.format(new Date(iso))}, ${formatTime(iso)}`;
}

/** Calendar date "2026-11-21" as "21.11.2026" (no time-zone shift). */
export function formatDate(isoDate: string): string {
  const [y, m, d] = isoDate.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return isoDate;
  return fullDate.format(new Date(y, m - 1, d));
}

/** "21.11.2026" for an instant, in the viewer's time zone (pairs with `formatTime`). */
export const formatLocalDate = (iso: string): string => fullDate.format(new Date(iso));

/** True when `iso` falls on the viewer's current calendar day. */
export const isToday = (iso: string, now: number = Date.now()): boolean =>
  calendarDays(iso, now) === 0;

const regions = new Intl.DisplayNames(["pl"], { type: "region" });
/** ISO country code as a Polish name ("CY" → "Cypr"); falls back to the code. */
export const formatCountry = (code: string): string => {
  try {
    return regions.of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
};

/** Host of a URL without "www.", or the input when it does not parse. */
export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** URL without scheme, "www.", query and hash, for display: "primefx24.example/pl/promo". */
export function displayUrl(url: string): string {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname === "/" ? "" : parsed.pathname.replace(/\/$/, "");
    return `${parsed.hostname.replace(/^www\./, "")}${path}`;
  } catch {
    return url;
  }
}
