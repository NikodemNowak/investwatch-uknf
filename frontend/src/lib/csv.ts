import type { FindingWithPost } from "@/api/types";
import { pl } from "@/i18n/pl";
import { describeFinding, subjectOf } from "@/lib/problems";

const BOM = "\u{FEFF}";

/** Quote a CSV field when it holds the separator, a quote or a line break. */
export function csvField(value: string | number | null | undefined, separator = ";"): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /["\r\n]/.test(text) || text.includes(separator) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** The review list as `;`-separated CSV with a BOM, so Excel (PL) keeps the diacritics. */
export function findingsCsv(items: readonly FindingWithPost[]): string {
  const rows = items.map((item) => [
    pl.risk[item.risk_level],
    item.score.toFixed(3).replace(".", ","),
    pl.modules[item.module],
    subjectOf(item),
    describeFinding(item),
    item.post ? pl.platforms[item.post.platform] : "",
    item.post?.canonical_url ?? "",
    item.created_at,
    pl.statuses[item.status],
  ]);
  return `${BOM}${[pl.review.csvHeader, ...rows].map((row) => row.map((v) => csvField(v)).join(";")).join("\r\n")}\r\n`;
}

/** Offer a text file for download. */
export function downloadText(
  text: string,
  filename: string,
  type = "text/csv;charset=utf-8",
): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const pad = (n: number): string => String(n).padStart(2, "0");

/** Download name in the viewer's local time, like the server's reports ("…-20261121-2130.csv"). */
export function csvFilename(stem: string, now: Date = new Date()): string {
  const day = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  return `investwatch-${stem}-${day}-${pad(now.getHours())}${pad(now.getMinutes())}.csv`;
}
