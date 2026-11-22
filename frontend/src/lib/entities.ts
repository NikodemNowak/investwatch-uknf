import type {
  EntityDetail,
  RegisteredFirm,
  EntityKind,
  EntitySummary,
  FindingWithPost,
  ModuleId,
  Platform,
  RegisterState,
  RiskLevel,
} from "@/api/types";
import { MODULES } from "@/lib/enums";

/** Mirror of `backend/src/investwatch/entities/aggregate.py` for mock mode. */

/** Path of an entity's card in the UI. */
export const entityPath = (key: string): string => `/podmioty/${encodeURIComponent(key)}`;

export const RISK_RANK: Record<RiskLevel, number> = { high: 3, medium: 2, low: 1 };

/** Key form of a publisher name: lower case, no leading `@`, single spaces. */
export function normalizeName(name: string): string {
  return name.trim().replace(/^@+/, "").toLocaleLowerCase("pl").replace(/\s+/g, " ").trim();
}

function domainOf(url: string | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

/** A real name, not empty and not a placeholder such as "(wklejony tekst)". */
function known(name: string): boolean {
  const text = name.trim();
  return Boolean(normalizeName(text)) && !(text.startsWith("(") && text.endsWith(")"));
}

function publisherOf(f: FindingWithPost): string {
  for (const candidate of [f.advertiser, f.post?.author, domainOf(f.post?.url)]) {
    if (candidate && known(candidate)) return candidate.trim();
  }
  return "";
}

/** Firm name without case and punctuation: "Finax, o.c.p., a.s." equals "Finax o.c.p., a.s.". */
export function firmNameKey(name: string): string {
  return name
    .toLocaleLowerCase("pl")
    .replace(/[^\p{L}\p{N}\s_]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** One key per firm (smallest id among records with the same name) and publishers of firms. */
interface FirmIndex {
  of: (firm: RegisteredFirm) => RegisteredFirm;
  byPublisher: Map<string, RegisteredFirm>;
}

function firmIndex(findings: FindingWithPost[]): FirmIndex {
  const canonical = new Map<string, RegisteredFirm>();
  for (const f of findings) {
    if (!f.firm) continue;
    const key = firmNameKey(f.firm.name);
    const current = canonical.get(key);
    if (!current || f.firm.id < current.id) canonical.set(key, f.firm);
  }
  const of = (firm: RegisteredFirm) => canonical.get(firmNameKey(firm.name)) ?? firm;
  const byPublisher = new Map<string, RegisteredFirm>();
  for (const f of [...findings].sort((a, b) => a.id.localeCompare(b.id))) {
    if (!f.firm || f.firm_match?.on !== "author") continue;
    const publisher = normalizeName(publisherOf(f));
    if (publisher && !byPublisher.has(publisher)) byPublisher.set(publisher, of(f.firm));
  }
  return { of, byPublisher };
}

/**
 * Entities a finding belongs to: its firm (keyed by the registered firm id), and the publisher
 * of an M1 ad or of unmatched material, unless that publisher is known to publish for a firm.
 */
export function entityRefs(
  f: FindingWithPost,
  firms: FirmIndex = firmIndex([f]),
): { key: string; kind: EntityKind; name: string }[] {
  const refs: { key: string; kind: EntityKind; name: string }[] = [];
  if (f.firm) {
    const firm = firms.of(f.firm);
    refs.push({ key: `firm:${firm.id}`, kind: "firm", name: firm.name });
  }
  const publisher = publisherOf(f);
  if (publisher && (!f.firm || f.module === "m1_third_party_ad")) {
    const norm = normalizeName(publisher);
    const owner = f.firm ? undefined : firms.byPublisher.get(norm);
    if (owner) {
      refs.push({ key: `firm:${owner.id}`, kind: "firm", name: owner.name });
    } else if (!f.firm || norm !== normalizeName(f.firm.name)) {
      refs.push({ key: `name:${norm}`, kind: "advertiser", name: publisher });
    }
  }
  return refs;
}

const maxBy = <T>(items: T[], score: (item: T) => string | number): T =>
  items.reduce((best, item) => (score(item) > score(best) ? item : best));

function merge(
  key: string,
  kind: EntityKind,
  name: string,
  findings: FindingWithPost[],
  fictional: (firmId: string) => boolean,
): EntitySummary {
  const firm = kind === "firm" ? (findings.find((f) => f.firm)?.firm ?? null) : null;
  const register: RegisterState = firm ? (fictional(firm.id) ? "fictional" : "knf") : "absent";
  const latest = maxBy(findings, (f) => f.created_at);
  const platforms: Platform[] = [];
  const first: string[] = [];
  const last: string[] = [];
  let occurrences = 0;
  for (const f of findings) {
    const group = f.occurrences ?? [];
    occurrences += Math.max(1, group.length);
    for (const p of [f.post?.platform, ...group.map((o) => o.platform)]) {
      if (p && !platforms.includes(p)) platforms.push(p);
    }
    first.push(f.first_seen_at ?? f.post?.first_seen_at ?? f.created_at);
    last.push(f.last_seen_at ?? f.post?.last_seen_at ?? f.created_at);
  }
  const modules = Object.fromEntries(
    MODULES.map((m) => [m, findings.filter((f) => f.module === m).length]),
  ) as Record<ModuleId, number>;
  return {
    key,
    kind,
    name,
    firm,
    knf_register: register,
    knf_warning: findings.find((f) => f.knf_warning)?.knf_warning ?? null,
    modules,
    total: findings.length,
    open: findings.filter((f) => f.status === "new" || f.status === "in_review").length,
    confirmed: findings.filter((f) => f.status === "confirmed").length,
    dismissed: findings.filter((f) => f.status === "dismissed").length,
    highest_risk: maxBy(findings, (f) => RISK_RANK[f.risk_level]).risk_level,
    max_score: Math.max(...findings.map((f) => f.score)),
    occurrences,
    platforms,
    first_seen_at: first.reduce((a, b) => (b < a ? b : a)),
    last_seen_at: last.reduce((a, b) => (b > a ? b : a)),
    latest_finding_id: latest.id,
    latest_at: latest.created_at,
  };
}

function groups(findings: FindingWithPost[]) {
  const out = new Map<string, { kind: EntityKind; name: string; items: FindingWithPost[] }>();
  const firms = firmIndex(findings);
  for (const f of findings) {
    for (const ref of entityRefs(f, firms)) {
      const group = out.get(ref.key) ?? { kind: ref.kind, name: ref.name, items: [] };
      group.items.push(f);
      out.set(ref.key, group);
    }
  }
  return out;
}

/** One summary per entity, most serious first (risk, open findings, total, newest). */
export function aggregateEntities(
  findings: FindingWithPost[],
  fictional: (firmId: string) => boolean = () => false,
): EntitySummary[] {
  return [...groups(findings)]
    .map(([key, g]) => merge(key, g.kind, g.name, g.items, fictional))
    .sort(
      (a, b) =>
        RISK_RANK[b.highest_risk] - RISK_RANK[a.highest_risk] ||
        b.open - a.open ||
        b.total - a.total ||
        b.latest_at.localeCompare(a.latest_at),
    );
}

/** The entity `key` with its findings, newest first; null when none belongs to it. */
export function entityDetail(
  findings: FindingWithPost[],
  key: string,
  fictional: (firmId: string) => boolean = () => false,
): EntityDetail | null {
  const group = groups(findings).get(key);
  if (!group) return null;
  return {
    ...merge(key, group.kind, group.name, group.items, fictional),
    findings: [...group.items].sort((a, b) => b.created_at.localeCompare(a.created_at)),
  };
}

/** Search over the entity name and its firm's aliases, domains and handles. */
export function entityMatches(entity: EntitySummary, query: string | undefined): boolean {
  const needle = normalizeName(query ?? "");
  if (!needle) return true;
  const names = [
    entity.name,
    ...(entity.firm
      ? [...entity.firm.aliases, ...entity.firm.domains, ...entity.firm.handles]
      : []),
  ];
  return names.some((n) => normalizeName(n).includes(needle));
}
