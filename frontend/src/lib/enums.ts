import type { ModuleId, Platform, RiskLevel, Status, Viewport } from "@/api/types";

/** Runtime lists of contract literals (order = display order). */
export const MODULES: ModuleId[] = [
  "m1_third_party_ad",
  "m2_risk_disclosure",
  "m3_shadow_advisory",
];
export const PLATFORMS: Platform[] = [
  "web",
  "facebook",
  "instagram",
  "tiktok",
  "youtube",
  "bing",
  "sample",
];
export const RISK_LEVELS: RiskLevel[] = ["high", "medium", "low"];
export const STATUSES: Status[] = ["new", "in_review", "confirmed", "dismissed"];
export const VIEWPORTS: Viewport[] = ["desktop", "tablet", "phone"];

/** Narrow an untrusted string to one of `allowed`, else undefined. */
export function oneOf<T extends string>(
  allowed: readonly T[],
  value: string | null | undefined,
): T | undefined {
  return value !== null && value !== undefined && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : undefined;
}

/** Keyboard shortcut per status on the findings list ("new" is the default, no key). */
export const STATUS_KEYS: Partial<Record<Status, string>> = {
  in_review: "A",
  confirmed: "P",
  dismissed: "O",
};
