/** Polish plural form: [one, few (2–4, not 12–14), many]. */
export function plural(n: number, forms: readonly [string, string, string]): string {
  const abs = Math.abs(n);
  if (abs === 1) return forms[0];
  const last = abs % 10;
  const lastTwo = abs % 100;
  if (last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14)) return forms[1];
  return forms[2];
}

/** Integer with a (non-breaking) space every three digits, also for 4-digit numbers. */
export function formatInt(n: number): string {
  const sign = n < 0 ? "-" : "";
  return sign + String(Math.round(Math.abs(n))).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
}

/** "3 problemy", "1 284 materiały": number with its plural noun. */
export function count(n: number, forms: readonly [string, string, string]): string {
  return `${formatInt(n)} ${plural(n, forms)}`;
}
